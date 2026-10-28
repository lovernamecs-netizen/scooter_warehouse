const uiScale=()=>Number(document.documentElement.style.zoom)||1;
// Map coordinates are independent of viewport zoom and scroll.
let busy=false, cancelDrag=null, menu=null;
export const isMapBusy=()=>busy||gestureBusy||!!menu;
const closeMenu=()=>{menu?.remove();menu=null};
document.addEventListener('pointerdown',e=>{if(menu&&!menu.contains(e.target))closeMenu()},true);
document.addEventListener('keydown',e=>{if(e.key==='Escape'){closeMenu();cancelDrag?.()} });
window.addEventListener('blur',()=>{closeMenu();cancelDrag?.()});
window.addEventListener('resize',closeMenu);
export function bindMapEditor({state,editing,zoom,onZoom,send,refresh,render,zoneEdit,slotAction,vehicleMove,objectsEdit,restructure,enableEdit,toast}){
 closeMenu();
 const canvas=document.querySelector('.map-canvas');if(!canvas)return;
 const viewport=canvas.closest('.map-viewport');
 bindMapNavigation(viewport,onZoom);
 const admin=state.user.role==='admin';
 let step=Number(localStorage.getItem('warehouseSnap'))||20;
 if(![10,20,40].includes(step))step=20;
 const select=document.querySelector('#map-snap');
 const paint=()=>{canvas.style.backgroundSize=`${step}px ${step}px`;if(select)select.value=String(step)};paint();
 if(select)select.onchange=()=>{step=Number(select.value);localStorage.setItem('warehouseSnap',String(step));paint()};
 viewport.addEventListener('wheel',closeMenu,{passive:true});
 function popup(e,actions,title){
  e.preventDefault();e.stopPropagation();closeMenu();
  menu=document.createElement('div');menu.className='map-context';menu.setAttribute('role','menu');menu.setAttribute('aria-label',title);
  const h=document.createElement('strong');h.textContent=title;menu.append(h);
  for(const [label,action] of actions){const b=document.createElement('button');b.textContent=label;b.setAttribute('role','menuitem');b.onclick=()=>{closeMenu();action()};menu.append(b)}
  document.body.append(menu);
  menu.style.left=Math.max(8,Math.min(e.clientX/uiScale(),innerWidth/uiScale()-menu.offsetWidth-8))+'px';
  menu.style.top=Math.max(8,Math.min(e.clientY/uiScale(),innerHeight/uiScale()-menu.offsetHeight-8))+'px';
  menu.querySelector('button').focus({preventScroll:true});
 }
 function wire(el,handle,data,save,edit){
  if(!admin)return;
  el.oncontextmenu=e=>{if(!busy)popup(e,[['설정 수정…',edit],...(data.rows&&restructure?[['구역 분할…',()=>restructure('split',data.id)],['구역 병합…',()=>restructure('merge',data.id)]]:[]),...(!editing?[['배치 편집 시작',enableEdit]]:[['위치 직접 입력…',edit]])],data.name||data.label||'영역')};
  if(!editing)return;
  handle.classList.add('map-drag-handle');handle.title='드래그하여 격자에 맞춰 이동 · Esc 취소 · 오른쪽 클릭 설정';
  handle.onpointerdown=e=>{
   if(e.button!==0||e.target.closest('button,input,select')||busy)return;
   e.preventDefault();closeMenu();busy=true;
   const zoom=(Number(viewport.dataset.mapZoom)||1)*uiScale();
   const start={x:data.x,y:data.y},origin=canvas.getBoundingClientRect();
   const grab={x:(e.clientX-origin.left)/zoom-start.x,y:(e.clientY-origin.top)/zoom-start.y};
   let pos={...start},moved=false;
   const initial={x:e.clientX,y:e.clientY};handle.setPointerCapture(e.pointerId);
   const mark=document.createElement('div');mark.className='map-drag-position';el.append(mark);
   el.classList.add('map-dragging');
   function restore(){el.style.left=start.x+'px';el.style.top=start.y+'px'}
   function cleanup(){handle.onpointermove=null;handle.onpointerup=null;handle.onpointercancel=null;handle.onlostpointercapture=null;cancelDrag=null;mark.remove();el.classList.remove('map-dragging');if(handle.hasPointerCapture(e.pointerId))handle.releasePointerCapture(e.pointerId)}
   cancelDrag=()=>{cleanup();restore();busy=false};
   handle.onpointercancel=cancelDrag;handle.onlostpointercapture=cancelDrag;
   handle.onpointermove=ev=>{
    if(Math.hypot(ev.clientX-initial.x,ev.clientY-initial.y)<4&&!moved)return;
    moved=true;const rect=canvas.getBoundingClientRect();
    pos={x:Math.max(0,Math.min(10000,Math.round(((ev.clientX-rect.left)/zoom-grab.x)/step)*step)),y:Math.max(0,Math.min(10000,Math.round(((ev.clientY-rect.top)/zoom-grab.y)/step)*step))};
    el.style.left=pos.x+'px';el.style.top=pos.y+'px';mark.textContent=`X ${pos.x} · Y ${pos.y}`;
   };
   handle.onpointerup=async()=>{
    cleanup();if(!moved||(pos.x===start.x&&pos.y===start.y)){restore();busy=false;return}
    try{await save(pos);toast('배치 위치 저장 완료')}
    catch(error){restore();toast('위치 저장 실패: '+error.message);try{await refresh()}catch{}}
    finally{busy=false;render()}
   };
  };
 }
 canvas.querySelectorAll('.slot').forEach(el=>{
  if(!['admin','worker'].includes(state.user.role))return;
  el.oncontextmenu=e=>{
   const z=state.layout.zones.find(z=>z.id===el.dataset.zone),sl=z.slots.find(sl=>sl.id===el.dataset.slot);
   const actions=[];
   if(sl.stay_id&&el.dataset.vehicle&&vehicleMove)actions.push(['차량 이동…',()=>vehicleMove(el.dataset.vehicle)]);
   if(sl.enabled&&!sl.stay_id){actions.push(['여기에 신규 차량 등록…',()=>slotAction('map-register',sl.id)],['기존 차량을 여기로 이동…',()=>slotAction('map-place',sl.id)])}
   if(admin)actions.push(['구역 설정 수정…',()=>zoneEdit(z.id)]);
   if(actions.length)popup(e,actions,z.name+' · '+sl.label);else e.stopPropagation();
  };
 });
 canvas.querySelectorAll('.zone').forEach(el=>{const z=state.layout.zones.find(z=>z.id===el.dataset.zoneId);if(!z)return;
  wire(el,el.querySelector('.zone-title'),z,pos=>send('zone',{id:z.id,version:z.version,warehouse_id:z.warehouse_id,name:z.name,kind:z.kind,rows:z.rows,cols:z.cols,model_ids:z.model_ids,active:z.active,...pos}),()=>zoneEdit(z.id));
 });
 canvas.querySelectorAll('.map-object').forEach(el=>{const index=Number(el.dataset.objectIndex),o=state.layout.objects[index];
  wire(el,el,o,pos=>send('map_objects',{revision:state.revision,objects:state.layout.objects.map((obj,i)=>i===index?{...obj,...pos}:obj)}),objectsEdit);
 });
}

// Local view gestures do not save or move warehouse data.
let gestureBusy=false,resetNavigation=null;
window.addEventListener('blur',()=>resetNavigation?.());
export function bindMapNavigation(viewport,onZoom){
 resetNavigation?.();
 const canvas=viewport.querySelector('.map-canvas'),spacer=canvas.parentElement;
 const points=new Map();let previous=null,panning=false,blocked=false,suppressUntil=0;
 resetNavigation=()=>{points.clear();previous=null;panning=false;blocked=false;gestureBusy=false;};
 const current=()=>Number(viewport.dataset.mapZoom)||1;
 function apply(value,x=viewport.clientWidth/2,y=viewport.clientHeight/2,fromX=x,fromY=y){
  const old=current(),next=Math.max(.3,Math.min(2.5,value));
  const wx=(viewport.scrollLeft+fromX)/old,wy=(viewport.scrollTop+fromY)/old;
  spacer.style.width=parseFloat(canvas.style.width)*next+'px';spacer.style.height=parseFloat(canvas.style.height)*next+'px';
  canvas.style.transform=`scale(${next})`;viewport.dataset.mapZoom=String(next);
  viewport.scrollLeft=wx*next-x;viewport.scrollTop=wy*next-y;
  const label=document.querySelector('#map-zoom-label');if(label)label.textContent=Math.round(next*100)+'%';
  onZoom(next);
 }
 viewport.zoomBy=delta=>{if(!busy&&!gestureBusy)apply(current()+delta)};
 viewport.addEventListener('wheel',e=>{
  e.preventDefault();closeMenu();if(busy||gestureBusy)return;
  const r=viewport.getBoundingClientRect(),units=e.deltaMode===1?16:e.deltaMode===2?viewport.clientHeight:1;
  apply(current()*Math.exp(-Math.max(-240,Math.min(240,e.deltaY*units))*.002),(e.clientX-r.left)/uiScale()-viewport.clientLeft,(e.clientY-r.top)/uiScale()-viewport.clientTop);
 },{passive:false});
 function geometry(){const a=[...points.values()],r=viewport.getBoundingClientRect();return a.length<2?null:{x:((a[0].x+a[1].x)/2-r.left)/uiScale()-viewport.clientLeft,y:((a[0].y+a[1].y)/2-r.top)/uiScale()-viewport.clientTop,d:Math.hypot(a[0].x-a[1].x,a[0].y-a[1].y)}}
 viewport.addEventListener('pointerdown',e=>{
  if(e.pointerType!=='touch')return;
  points.set(e.pointerId,{x:e.clientX,y:e.clientY});
  if(points.size>=2){cancelDrag?.();closeMenu();blocked=true;gestureBusy=true;previous=geometry();suppressUntil=Date.now()+500;e.preventDefault();e.stopImmediatePropagation();}
  else{panning=!e.target.closest('.map-drag-handle');gestureBusy=true;}
  if(blocked)viewport.setPointerCapture(e.pointerId);
 },true);
 viewport.addEventListener('pointermove',e=>{
  const old=points.get(e.pointerId);if(!old)return;
  points.set(e.pointerId,{x:e.clientX,y:e.clientY});
  if(points.size>=2){const g=geometry();if(previous&&previous.d>0)apply(current()*g.d/previous.d,g.x,g.y,previous.x,previous.y);previous=g;e.preventDefault();e.stopImmediatePropagation();suppressUntil=Date.now()+500;}
  else if(blocked){e.preventDefault();e.stopImmediatePropagation();}
  else if(panning){if(!viewport.hasPointerCapture(e.pointerId))viewport.setPointerCapture(e.pointerId);const dx=e.clientX-old.x,dy=e.clientY-old.y;viewport.scrollLeft-=dx/uiScale();viewport.scrollTop-=dy/uiScale();if(Math.abs(dx)+Math.abs(dy)>2)suppressUntil=Date.now()+500;e.preventDefault();}
 },true);
 function end(e){if(!points.has(e.pointerId))return;points.delete(e.pointerId);if(blocked){e.preventDefault();e.stopImmediatePropagation();suppressUntil=Date.now()+500;}previous=geometry();if(!points.size){panning=false;blocked=false;gestureBusy=false;}}
 viewport.addEventListener('pointerup',end,true);viewport.addEventListener('pointercancel',end,true);
 viewport.addEventListener('click',e=>{if(Date.now()<suppressUntil){e.preventDefault();e.stopImmediatePropagation();}},true);
 viewport.addEventListener('dragstart',e=>{if(points.size||blocked)e.preventDefault();},true);
}
