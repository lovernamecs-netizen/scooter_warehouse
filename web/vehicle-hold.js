// Holding selects a vehicle; the existing destination confirmation performs the move.
export function installVehicleHold({eligible,begin,cancelMove}){
 let pending=null,suppressUntil=0;const pointers=new Set();
 function clear(){if(pending){clearTimeout(pending.timer);pending.card.classList.remove('hold-to-move');pending=null;}}
 document.addEventListener('pointerdown',e=>{
  pointers.add(e.pointerId);clear();
  const card=e.target.closest('.map-viewport .slot[data-vehicle]');
  if(pointers.size!==1||e.button!==0||!card?.dataset.vehicle||!eligible())return;
  const hold={card,id:e.pointerId,x:e.clientX,y:e.clientY};pending=hold;card.classList.add('hold-to-move');
  hold.timer=setTimeout(()=>{if(pending!==hold||!card.isConnected||!eligible())return;clear();suppressUntil=Date.now()+30000;begin(card.dataset.vehicle);},2000);
 },true);
 document.addEventListener('pointermove',e=>{if(pending&&pending.id===e.pointerId&&Math.hypot(e.clientX-pending.x,e.clientY-pending.y)>10)clear();},true);
 const end=e=>{pointers.delete(e.pointerId);clear();if(suppressUntil>Date.now())suppressUntil=Date.now()+450;};
 document.addEventListener('pointerup',end,true);document.addEventListener('pointercancel',end,true);
 document.addEventListener('click',e=>{if(Date.now()<suppressUntil){e.preventDefault();e.stopImmediatePropagation();}},true);
 document.addEventListener('contextmenu',e=>{if(pending&&pending.card.contains(e.target)){e.preventDefault();e.stopImmediatePropagation();}},true);
 document.addEventListener('dragstart',clear,true);document.addEventListener('wheel',clear,true);
 document.addEventListener('scroll',e=>{if(e.target.matches?.('.map-viewport'))clear();},true);
 document.addEventListener('keydown',e=>{if(e.key==='Escape'){clear();cancelMove();}});
 window.addEventListener('blur',()=>{clear();pointers.clear();suppressUntil=0;});
 document.addEventListener('visibilitychange',()=>{if(document.hidden){clear();pointers.clear();suppressUntil=0;}});
}
