export function sortWorkOrders(vehicles,today){
 const time=Date.parse(today+'T00:00:00Z');
 const day=v=>Date.parse((v.assignment?.scheduled||'')+'T00:00:00Z');
 const distance=v=>Number.isFinite(day(v))?Math.abs(day(v)-time):Infinity;
 return [...vehicles].sort((a,b)=>distance(a)-distance(b)||(day(a)||Infinity)-(day(b)||Infinity)||String(a.assignment?.number||a.id).localeCompare(String(b.assignment?.number||b.id),'en',{numeric:true}));
}
export function orderCustomerHTML(v,allowed,esc){
 if(!v.assignment)return '<span class="muted">—</span>';
 if(!allowed)return '<span class="muted">조회 권한 없음</span>';
 return `<span class="order-customer-name" data-customer-order="${esc(v.assignment.order_id)}">불러오는 중…</span>`;
}
export async function loadOrderCustomers(container,api){
 const elements=[...container.querySelectorAll('[data-customer-order]')];
 const ids=[...new Set(elements.map(e=>e.dataset.customerOrder))];
 for(let i=0;i<ids.length;i+=200){
  const batch=ids.slice(i,i+200),nodes=elements.filter(e=>batch.includes(e.dataset.customerOrder));
  if(!nodes.some(e=>e.isConnected))return;
  try{
   const rows=await api('/customers/orders',{method:'POST',body:JSON.stringify({order_ids:batch})});
   for(const node of nodes)if(node.isConnected){const value=rows[node.dataset.customerOrder];node.textContent=value?value.name:'미등록 · 기존 주문';node.classList.toggle('unregistered',!value);}
  }catch{for(const node of nodes)if(node.isConnected)node.textContent='고객정보 조회 불가';}
 }
}

export function orderChannelBadge(v){
 const channel=v.assignment?.parts_order?.channel;
 if(!v.assignment)return '';
 if(channel!=='B2B'&&channel!=='B2C')return '<span class="order-channel-badge unknown" aria-label="주문 구분 미등록">구분 미등록</span>';
 return `<span class="order-channel-badge ${channel.toLowerCase()}" aria-label="${channel} 주문">${channel}</span>`;
}
