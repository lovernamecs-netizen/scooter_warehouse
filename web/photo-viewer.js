// Authenticated originals are loaded only on demand; no thumbnail is promoted to an original.
export function photoName(label, id, blob) {
  const ext={'image/jpeg':'jpg','image/png':'png','image/webp':'webp','image/heic':'heic','image/heif':'heif'}[blob.type.split(';')[0]]||'original';
  return `${label}-${id.slice(0,8)}.${ext}`;
}

let pendingPhotoBack=0;
export const isPhotoBack=()=>pendingPhotoBack>0||!!document.querySelector('dialog[data-photo-overlay][open]');
// Window popstate listeners share a target. The parent explicitly yields to overlays.
export function dialogBack(dialog, dismiss, canClose=()=>true) {
  const previous=document.activeElement, marker=crypto.randomUUID();
  let closed=false,awaitingBack=false;
  history.pushState({...history.state,photoOverlay:marker},'');
  const pop=e=>{e.stopImmediatePropagation();if(awaitingBack){pendingPhotoBack--;awaitingBack=false;}if(!closed&&!canClose()){history.pushState({...history.state,photoOverlay:marker},'');return;}window.removeEventListener('popstate',pop,true);if(!closed)finish(false);};
  const cancel=e=>{e.preventDefault();finish(true);};
  function finish(back=true){
    if(closed||!canClose())return;closed=true;
    dialog.removeEventListener('cancel',cancel);
    dialog.removeEventListener('photo-back',cancel);
    dismiss();if(previous?.isConnected)previous.focus({preventScroll:true});
    if(back&&history.state?.photoOverlay===marker){awaitingBack=true;pendingPhotoBack++;history.back();}
    else window.removeEventListener('popstate',pop,true);
  }
  window.addEventListener('popstate',pop,true);
  dialog.addEventListener('cancel',cancel);dialog.addEventListener('photo-back',cancel);
  dialog.dataset.photoOverlay='true';
  return ()=>finish(true);
}

export function openOriginal({label,load,download,id='photo'}) {
  const dialog=document.createElement('dialog');dialog.className='original-viewer';
  dialog.setAttribute('aria-label',label+' 원본 사진 확대');
  dialog.innerHTML=`<header><strong></strong><button type="button" data-v="close" aria-label="원본 사진 닫기">닫기 ✕</button></header>
    <div class="original-toolbar"><button type="button" data-v="minus" aria-label="축소">−</button><button type="button" data-v="plus" aria-label="확대">＋</button><button type="button" data-v="fit">화면 맞춤</button><button type="button" data-v="actual" title="이미지 1픽셀 = CSS 1픽셀">100%</button><button type="button" data-v="download" disabled>원본 다운로드</button><button type="button" data-v="retry" hidden>다시 불러오기</button></div>
    <p class="original-status" role="status">원본을 불러오는 중…</p><div class="original-viewport" tabindex="0" aria-label="휠 또는 두 손가락으로 확대, 드래그로 이동"><img alt="" draggable="false" hidden></div>`;
  dialog.querySelector('strong').textContent=label+' · 원본';
  const stage=dialog.querySelector('.original-viewport'),img=stage.querySelector('img'),status=dialog.querySelector('.original-status');img.alt=label+' 원본';
  let blob=null,url=null,alive=true,loaded=false,attempt=0,w=0,h=0,scale=1,fit=1,x=0,y=0,fitted=true,lastTap=0;
  const points=new Map();let gesture=null,tapStart=null;
  const controller=new AbortController(),listen=(node,type,fn,options={})=>node.addEventListener(type,fn,{...options,signal:controller.signal});
  const clamp=(v,a,b)=>Math.min(b,Math.max(a,v));
  function bounds(){x=w*scale<=stage.clientWidth?(stage.clientWidth-w*scale)/2:clamp(x,stage.clientWidth-w*scale,0);y=h*scale<=stage.clientHeight?(stage.clientHeight-h*scale)/2:clamp(y,stage.clientHeight-h*scale,0);}
  function draw(){if(!loaded)return;bounds();img.style.transform=`translate(${x}px,${y}px) scale(${scale})`;status.textContent=`${w} × ${h} · ${Math.round(scale*100)}% · 100% = 이미지 1픽셀/CSS 1픽셀`;stage.dataset.scale=String(scale);}
  function fitImage(){if(!loaded)return;fit=Math.min(stage.clientWidth/w,stage.clientHeight/h,1);scale=fit;fitted=true;draw();}
  function zoom(next,cx=stage.clientWidth/2,cy=stage.clientHeight/2){if(!loaded)return;const before=scale;scale=clamp(next,fit,Math.max(8,fit));x=cx-(cx-x)*scale/before;y=cy-(cy-y)*scale/before;fitted=false;draw();}
  function local(e){const r=stage.getBoundingClientRect();const z=r.width/stage.offsetWidth||1;return {x:(e.clientX-r.left)/z,y:(e.clientY-r.top)/z};}
  function snapshot(){const ps=[...points.values()];if(!ps.length){gesture=null;return;}const a=ps[0],b=ps[1];gesture={x,y,scale,cx:b?(a.x+b.x)/2:a.x,cy:b?(a.y+b.y)/2:a.y,d:b?Math.hypot(b.x-a.x,b.y-a.y):0};}
  const close=dialogBack(dialog,()=>{alive=false;attempt++;observer.disconnect();controller.abort();img.src='';if(url)URL.revokeObjectURL(url);dialog.close();dialog.remove();});
  listen(dialog,'click',async e=>{const action=e.target.closest('[data-v]')?.dataset.v;
    if(action==='close')close();if(action==='fit')fitImage();if(action==='actual')zoom(1);if(action==='plus')zoom(scale*1.4);if(action==='minus')zoom(scale/1.4);if(action==='retry')await fetchOriginal();
    if(action==='download'&&blob)download(blob,photoName(label,id,blob));
  });
  listen(stage,'wheel',e=>{e.preventDefault();e.stopPropagation();const p=local(e);zoom(scale*Math.exp(-e.deltaY*.002),p.x,p.y);},{passive:false});
  listen(stage,'pointerdown',e=>{if(!loaded||e.button>0)return;e.preventDefault();stage.setPointerCapture(e.pointerId);points.set(e.pointerId,local(e));tapStart=points.size===1?{...local(e),time:Date.now(),type:e.pointerType}:null;snapshot();});
  listen(stage,'pointermove',e=>{if(!points.has(e.pointerId))return;e.preventDefault();points.set(e.pointerId,local(e));const ps=[...points.values()],a=ps[0],b=ps[1];if(!gesture)return;
    if(tapStart&&Math.hypot(a.x-tapStart.x,a.y-tapStart.y)>8)tapStart=null;
    if(b&&gesture.d){const cx=(a.x+b.x)/2,cy=(a.y+b.y)/2;scale=clamp(gesture.scale*Math.hypot(b.x-a.x,b.y-a.y)/gesture.d,fit,8);x=cx-(gesture.cx-gesture.x)*scale/gesture.scale;y=cy-(gesture.cy-gesture.y)*scale/gesture.scale;}
    else{x=gesture.x+a.x-gesture.cx;y=gesture.y+a.y-gesture.cy;}fitted=false;draw();
  });
  const up=e=>{if(!points.has(e.pointerId))return;const tap=tapStart;points.delete(e.pointerId);snapshot();tapStart=null;
    if(e.type==='pointerup'&&tap?.type==='touch'&&Date.now()-tap.time<280){if(Date.now()-lastTap<350){scale>fit*1.1?fitImage():zoom(Math.max(1,fit*2),tap.x,tap.y);lastTap=0;}else lastTap=Date.now();}
  };
  listen(stage,'pointerup',up);listen(stage,'pointercancel',up);
  listen(stage,'dblclick',e=>{e.preventDefault();const p=local(e);scale>fit*1.1?fitImage():zoom(Math.max(1,fit*2),p.x,p.y);});
  listen(stage,'keydown',e=>{if(['+','=','-','0','1','ArrowLeft','ArrowRight','ArrowUp','ArrowDown'].includes(e.key)){e.preventDefault();e.stopPropagation();if(e.key==='0')fitImage();else if(e.key==='1')zoom(1);else if(e.key==='-')zoom(scale/1.4);else if(['+','='].includes(e.key))zoom(scale*1.4);else{x+=e.key==='ArrowLeft'?40:e.key==='ArrowRight'?-40:0;y+=e.key==='ArrowUp'?40:e.key==='ArrowDown'?-40:0;draw();}}});
  async function fetchOriginal(){const n=++attempt;loaded=false;img.hidden=true;blob=null;dialog.querySelector('[data-v=download]').disabled=true;dialog.querySelector('[data-v=retry]').hidden=true;status.textContent='원본을 불러오는 중…';
    try{const result=await load();if(!alive||n!==attempt)return;blob=result;dialog.querySelector('[data-v=download]').disabled=false;if(url)URL.revokeObjectURL(url);url=URL.createObjectURL(blob);img.src=url;
      try{await img.decode();}catch{throw Error('이 브라우저에서 원본 형식을 표시할 수 없습니다. 원본을 다운로드해 확인하세요.');}
      if(!alive||n!==attempt)return;w=img.naturalWidth;h=img.naturalHeight;loaded=true;img.hidden=false;fitImage();
    }catch(e){if(alive&&n===attempt){status.textContent=e.message||'원본 불러오기 실패';dialog.querySelector('[data-v=retry]').hidden=false;}}
  }
  const observer=new ResizeObserver(()=>{if(!loaded)return;fit=Math.min(stage.clientWidth/w,stage.clientHeight/h,1);if(fitted)fitImage();else{scale=Math.max(scale,fit);draw();}});
  document.body.append(dialog);dialog.showModal();observer.observe(stage);dialog.querySelector('[data-v=close]').focus();fetchOriginal();return close;
}
