// Device-local presentation preference only. Never stores account or business data.
const root=document.documentElement, coarse=matchMedia('(pointer:coarse)'), wide=matchMedia('(min-width:720px)');
let scale=100, gesture=null, blocked=false, suppress=0;
const pointers=new Map();
const storageKey=()=>`warehouse-ui-scale-${wide.matches?'wide':'narrow'}`;
function apply(value,save=false){
 scale=Math.max(70,Math.min(130,Math.round(value/10)*10));
 root.style.zoom=coarse.matches?String(scale/100):'';
 root.style.setProperty('--ui-scale',coarse.matches?String(scale/100):'1');
 if(save)try{localStorage.setItem(storageKey(),String(scale));}catch{}
}
function load(){let value;try{value=Number(localStorage.getItem(storageKey()));}catch{}apply(value>=70&&value<=130?value:wide.matches?90:100);}
let feedbackTimer;
function showScale(){
 clearTimeout(feedbackTimer);document.querySelector('.ui-scale-feedback')?.remove();
 const box=document.createElement('div');box.className='ui-scale-feedback';
 box.setAttribute('role','status');box.setAttribute('aria-live','polite');
 box.setAttribute('popover','manual');box.textContent=scale+'%';
 document.body.append(box);
 if(box.showPopover)box.showPopover();
 feedbackTimer=setTimeout(()=>box.remove(),1200);
}
document.addEventListener('click',e=>{
 if(Date.now()<suppress){e.preventDefault();e.stopImmediatePropagation();}
},true);
function radius(touches){const a=Array.from(touches),x=a.reduce((n,t)=>n+t.clientX,0)/a.length,y=a.reduce((n,t)=>n+t.clientY,0)/a.length;return Math.sqrt(a.reduce((n,t)=>n+(t.clientX-x)**2+(t.clientY-y)**2,0)/a.length);}
// Let existing one/two-finger map/photo interactions run until a third finger arrives.
document.addEventListener('pointerdown',e=>{if(e.pointerType==='touch')pointers.set(e.pointerId,e.target);},true);
for(const type of ['pointerup','pointercancel'])document.addEventListener(type,e=>pointers.delete(e.pointerId),true);
document.addEventListener('pointermove',e=>{if(blocked&&e.pointerType==='touch'){e.preventDefault();e.stopImmediatePropagation();}},true);
document.addEventListener('touchstart',e=>{
 if(!coarse.matches||e.touches.length!==3||blocked)return;
 blocked=true;gesture={start:radius(e.touches),value:scale,done:false};
 for(const [id,target] of [...pointers])target.dispatchEvent(new PointerEvent('pointercancel',{bubbles:true,pointerId:id,pointerType:'touch'}));
 e.preventDefault();e.stopImmediatePropagation();
},{capture:true,passive:false});
document.addEventListener('touchmove',e=>{
 if(!blocked)return;e.preventDefault();e.stopImmediatePropagation();
 if(e.touches.length!==3||!gesture||gesture.done||gesture.start<20)return;
 const ratio=radius(e.touches)/gesture.start;
 if(ratio<.82||ratio>1.18){apply(gesture.value+(ratio>1?10:-10),true);showScale();gesture.done=true;}
},{capture:true,passive:false});
for(const type of ['touchend','touchcancel'])document.addEventListener(type,e=>{
 if(!blocked)return;e.preventDefault();e.stopImmediatePropagation();suppress=Date.now()+450;
 if(e.touches.length!==3)gesture=null;
 if(!e.touches.length){blocked=false;pointers.clear();}
},{capture:true,passive:false});
window.addEventListener('blur',()=>{blocked=false;gesture=null;pointers.clear();});
coarse.addEventListener('change',load);wide.addEventListener('change',load);load();
