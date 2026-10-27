export const normalizeSearch=value=>String(value||'').trim().toUpperCase();
export function matchesSearch(v,value,extra=''){
 const q=normalizeSearch(value),vin=normalizeSearch(v.vin);
 if(!q)return true;
 if(/^[A-Z0-9]{4}$/.test(q))return vin.endsWith(q);
 if(/^[A-Z0-9]{17}$/.test(q))return vin===q;
 return [v.vin,v.reference,v.model,v.brand,v.color,v.plate,v.smart_key,v.state,v.received_at,v.assignment?.scheduled,extra].join(' ').toUpperCase().includes(q);
}
let lastKey='',lastTime=-1000;
export function bindSearch(form,run){
 if(!form)return;const input=form.querySelector('input[type=search]');let composing=false;
 input.addEventListener('compositionstart',()=>composing=true);input.addEventListener('compositionend',()=>composing=false);
 input.addEventListener('keydown',e=>{if(e.key==='Enter'&&(composing||e.isComposing||e.keyCode===229))e.preventDefault();});
 form.addEventListener('submit',e=>{e.preventDefault();if(composing)return;const value=normalizeSearch(input.value),key=form.id+'|'+value,now=performance.now();if(lastKey===key&&now-lastTime<350)return;lastKey=key;lastTime=now;input.value=value;run(value);});
}
