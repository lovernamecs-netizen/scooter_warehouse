// Shared library metadata is paginated; image bytes are fetched only on selection.
let busy=false;
export const isLibraryBusy=()=>busy;
export function mountInsuranceLibrary(target,{api,toast,esc,getLocal,onLoad,refreshLocal,canUse=()=>true}){
 target.innerHTML='<section class="panel insurance-card"><div class="panel-head"><h2>공용 증권함</h2><span>관리자 전용</span></div>'+ 
 '<details><summary>서버 PC 저장 경로</summary><p id="library-path"></p><label>새 저장 경로<input id="library-path-input" autocomplete="off"></label><button data-library="path">경로 설정</button><p class="muted">새 파일부터 적용됩니다. 이전 경로의 증권도 계속 조회됩니다. 암호화 파일은 프로그램에서 내려받으세요.</p><div id="library-roots"></div></details>'+
 '<div class="insurance-actions"><button data-library="save-local">현재 검색 결과 공용 저장</button><label class="insurance-upload secondary">JPEG 폴더 공용 등록<input id="library-folder" type="file" accept=".jpg,.jpeg" webkitdirectory multiple></label><button data-library="cancel" disabled>등록 중단</button></div>'+
 '<form id="library-search" class="insurance-search"><label>차량번호·파일명<input id="library-query" type="search" enterkeyhint="search" maxlength="80" autocomplete="off"></label><button>검색</button><button type="button" data-library="reset">전체 보기</button></form>'+
 '<p id="library-progress" role="status"></p><div id="library-list"></div><div class="insurance-actions"><button data-library="first">처음</button><button data-library="next" disabled>다음 50건</button></div></section>';
 const el=s=>target.querySelector(s);let query='',next='',items=[],cancel=false,requestVersion=0;const urls=new Set();
 const report=text=>el('#library-progress').textContent=text;
 const freeze=()=>{target.querySelectorAll('input,button').forEach(x=>x.disabled=busy);el('[data-library=cancel]').disabled=!busy;refreshLocal();};
 async function settings(){const value=await api('/insurance/library/settings');el('#library-path').textContent=value.path||'저장 경로를 설정하세요.';el('#library-path-input').value=value.path||value.default_path;el('#library-roots').textContent=Object.values(value.roots).join(' · ');return value;}
 async function listing(cursor=''){
  const version=++requestVersion;
  try{
   const value=await api('/insurance/library?q='+encodeURIComponent(query)+'&cursor='+encodeURIComponent(cursor));if(version!==requestVersion)return;
   items=value.documents;next=value.next_cursor;
   el('#library-list').innerHTML=items.length?'<div class="table-wrap"><table><thead><tr><th>차량번호 / 증권</th><th>등록</th><th>작업</th></tr></thead><tbody>'+items.map(d=>'<tr><td><strong>'+esc(d.plate||'차량번호 미입력')+'</strong><br>'+esc(d.source)+(d.same_plate_count>1?'<small class="insurance-warning">같은 차량번호 증권 '+d.same_plate_count+'건 · 내용 확인 필요</small>':'')+(d.review_required?'<small>원본 확인 전</small>':'')+'</td><td>'+esc(new Date(d.created_at).toLocaleString('ko-KR'))+'<small>'+esc(d.actor)+'</small></td><td><button data-library="preview" data-id="'+d.id+'">미리보기</button><button data-library="download" data-id="'+d.id+'">다운로드</button><button data-library="load" data-id="'+d.id+'">발송 준비로 가져오기</button></td></tr>').join('')+'</tbody></table></div>':'<div class="empty">저장된 증권이 없거나 검색 결과가 없습니다.</div>';
   el('[data-library=next]').disabled=!next||busy;
  }catch(e){if(version===requestVersion)toast(e.message);}
 }
 async function uploadBatch(count,read){
  if(busy||!canUse())return;busy=true;cancel=false;freeze();let index=0,saved=0,duplicate=0,failed=0,different=0;const failures=[];
  try{
   const cfg=await api('/insurance/library/settings');if(!cfg.path)throw Error('서버 PC 저장 경로를 먼저 설정하세요.');
   async function work(){while(index<count&&!cancel){const i=index++;try{const data=await read(i);const result=await api('/insurance/library',{method:'POST',body:JSON.stringify(data)});if(result.duplicate){duplicate++;if(result.metadata_differs){different++;if(failures.length<3)failures.push('동일 파일의 기존 정보 유지: '+result.document.plate+' / '+result.document.source);}}else saved++;}catch(e){failed++;if(failures.length<3)failures.push(e.message);}report((saved+duplicate+failed)+'/'+count+' · 저장 '+saved+' · 동일 파일 '+duplicate+' · 실패 '+failed);}}
   await Promise.all(Array.from({length:Math.min(4,count)},work));
   report((cancel?'등록 중단 · ':'등록 완료 · ')+'저장 '+saved+' · 동일 파일 '+duplicate+' · 실패 '+failed+(different?' · 기존 이름/차량번호 유지 '+different+'건':'')+(failures.length?' · '+failures.join(' / '):''));
  }catch(e){report(e.message);}finally{busy=false;freeze();await listing();}
 }
 function blobBase64(blob){return new Promise((resolve,reject)=>{const reader=new FileReader();reader.onload=()=>resolve(String(reader.result).split(',')[1]);reader.onerror=()=>reject(Error('파일을 읽을 수 없습니다.'));reader.readAsDataURL(blob);});}
 el('#library-folder').onchange=async e=>{const files=Array.from(e.target.files||[]).filter(f=>/\.jpe?g$/i.test(f.name));e.target.value='';await uploadBatch(files.length,async i=>{const file=files[i];if(file.size>199000)throw Error(file.name+': 199,000바이트 초과');const plate=file.name.replace(/\.jpe?g$/i,'').replace(/_\d+$/,'');return {source:file.name,plate:/^(?:\d{1,3}[가-힣]\d{4,5}|[가-힣]{5,8}\d{4,5})$/.test(plate)?plate:'',page:1,review_required:true,jpeg_base64:await blobBase64(file)};});};
 el('#library-search').onsubmit=e=>{e.preventDefault();if(busy)return;query=el('#library-query').value.trim();listing();};
 el('#library-search').onkeydown=e=>{if(e.key==='Enter'&&(e.isComposing||e.keyCode===229))e.preventDefault();};
 target.onclick=async e=>{
  const button=e.target.closest('[data-library]');if(!button||button.disabled)return;const action=button.dataset.library;
  if(action==='cancel'){cancel=true;button.disabled=true;return;}if(busy||!canUse())return;
  try{
   if(action==='path'){busy=true;freeze();try{await api('/insurance/library/settings',{method:'PUT',body:JSON.stringify({path:el('#library-path-input').value})});await settings();report('저장 경로를 변경했습니다. 기존 증권은 보존됩니다.');}finally{busy=false;freeze();}return;}
   if(action==='save-local'){const docs=getLocal();if(!docs.length)return toast('저장할 증권이 없습니다.');await uploadBatch(docs.length,i=>Promise.resolve(docs[i]));return;}
   if(action==='reset'){query='';return listing();}if(action==='first')return listing();if(action==='next')return listing(next);
   const doc=items.find(d=>d.id===button.dataset.id);if(!doc)return;
   button.disabled=true;
   const blob=await api('/insurance/library/'+doc.id+'/image',{blob:true});
   if(!target.isConnected)return;
   if(action==='load'){onLoad({...doc,jpeg_base64:await blobBase64(blob),within_limit:true,phone:'',manualPhone:false,review_required:true});toast('발송 준비 목록에 가져왔습니다. 원본과 수신번호를 확인하세요.');return;}
   const url=URL.createObjectURL(blob);urls.add(url);const release=()=>{URL.revokeObjectURL(url);urls.delete(url);};
   if(action==='download'){const a=document.createElement('a');a.href=url;a.download=(doc.plate||doc.source.replace(/\.jpe?g$/i,''))+'_'+doc.id.slice(-6)+'.jpg';a.click();setTimeout(release,10000);}
   else{const dialog=document.createElement('dialog');dialog.className='insurance-preview';dialog.innerHTML='<div class="insurance-preview-head"><strong>'+esc(doc.source)+'</strong><button>닫기</button></div><img alt="공용 보험증권">';dialog.querySelector('img').src=url;dialog.querySelector('button').onclick=()=>dialog.close();dialog.onclose=()=>{release();dialog.remove();};document.body.appendChild(dialog);dialog.showModal();}
  }catch(error){toast(error.message);}finally{button.disabled=false;}
 };
 settings().catch(e=>report(e.message));listing();
}
