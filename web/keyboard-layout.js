// Keep forms inside the visual viewport, which excludes a docked on-screen keyboard.
const modal=document.querySelector('#modal'), root=document.documentElement;
const viewport=window.visualViewport;
const editable=el=>el instanceof Element && el.matches('textarea,select,[contenteditable="true"],input:not([type="hidden"]):not([type="checkbox"]):not([type="radio"]):not([type="button"]):not([type="submit"]):not([type="file"]):not([type="range"]):not([type="color"])');
const touch=()=>navigator.maxTouchPoints>0 || matchMedia('(pointer:coarse)').matches || /Android/i.test(navigator.userAgent);
let frame=0,timer=0;
function update(){
 frame=0;
 const enabled=touch() && (!viewport || viewport.scale<1.1);
 const height=viewport?.height||window.innerHeight, top=viewport?.offsetTop||0;
 root.style.setProperty('--form-visible-height',height+'px');
 root.style.setProperty('--form-visible-top',top+'px');
 root.classList.toggle('editing-field',enabled&&editable(document.activeElement));
 if(!modal)return;
 modal.classList.toggle('viewport-dialog',enabled&&modal.open);
 modal.classList.toggle('compact-form',enabled&&height<400);
 if(enabled&&modal.open){
  const header=modal.querySelector('.modal-head');
  if(header&&!header.querySelector('[data-keyboard-dismiss]')){
   const button=document.createElement('button');button.type='button';button.dataset.keyboardDismiss='true';button.className='keyboard-dismiss';button.textContent='키보드 닫기';
   header.insertBefore(button,header.lastElementChild);
  }
 }
 const el=document.activeElement;
 if(!enabled||!editable(el))return;
 const body=el.closest('.modal-body');
 if(body&&modal.open){
  const b=body.getBoundingClientRect(), r=el.getBoundingClientRect();
  const min=Math.max(b.top,top)+10, max=Math.min(b.bottom,top+height)-10;
  if(max>min){if(r.height>max-min || r.top<min)body.scrollTop+=r.top-min;else if(r.bottom>max)body.scrollTop+=r.bottom-max;}
 }else{
  const r=el.getBoundingClientRect();if(r.bottom>top+height-16||r.top<top+16)el.scrollIntoView({block:'center',behavior:'auto'});
 }
}
function schedule(){if(!frame)frame=requestAnimationFrame(update);}
function settle(){schedule();clearTimeout(timer);timer=setTimeout(schedule,180);}
window.addEventListener('resize',settle);
viewport?.addEventListener('resize',settle);viewport?.addEventListener('scroll',schedule);
document.addEventListener('focusin',settle);document.addEventListener('focusout',settle);
document.addEventListener('pointerdown',e=>{if(e.target.closest('[data-keyboard-dismiss]'))e.preventDefault();});
document.addEventListener('click',e=>{if(e.target.closest('[data-keyboard-dismiss]')){document.activeElement?.blur();settle();}});
if(modal)new MutationObserver(schedule).observe(modal,{attributes:true,attributeFilter:['open'],childList:true});
schedule();
