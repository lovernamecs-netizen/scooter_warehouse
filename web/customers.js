// Names remain in the current screen only. Persistent command recovery stores IDs.
export function mountCustomerEditor(root,{api,esc},selected=null){
 let chosen=selected,requestId=crypto.randomUUID(),timer=null,generation=0;
 root.innerHTML=`<label>업체 / 주문자 구분<select data-kind><option value="COMPANY">업체</option><option value="PERSON">개인 주문자</option></select></label><label>업체명 또는 주문자명 · 필수<input data-name autocomplete="off" maxlength="120" placeholder="이름 입력 또는 기존 고객 선택"></label><div data-results role="listbox" aria-label="기존 업체·주문자"></div><small data-status>새 이름은 등록 후 주문에 연결됩니다.</small>`;
 const input=root.querySelector('[data-name]'),kind=root.querySelector('[data-kind]'),results=root.querySelector('[data-results]'),status=root.querySelector('[data-status]');
 if(chosen){input.value=chosen.name;kind.value=chosen.kind;status.textContent='기존 고객 선택됨';}
 function showChoices(items){
  const groups=new Map();for(const c of items){const k=c.kind+'|'+c.name.normalize('NFKC').trim().toLocaleLowerCase();if(!groups.has(k))groups.set(k,[]);groups.get(k).push(c);}
  results.innerHTML=[...groups.values()].map(rows=>{const choices=rows.map(c=>`<button type="button" data-choice="${esc(c.id)}" role="option">${rows.length>1?'기록 '+esc(c.id.slice(0,8)):esc(c.name)+' · '+(c.kind==='COMPANY'?'업체':'개인')}</button>`).join('');return rows.length>1?`<details><summary>${esc(rows[0].name)} · 동일 이름 ${rows.length}개 기록</summary>${choices}</details>`:choices;}).join('');
  results.onclick=e=>{const b=e.target.closest('[data-choice]');if(!b)return;chosen=items.find(c=>c.id===b.dataset.choice);generation++;clearTimeout(timer);input.value=chosen.name;kind.value=chosen.kind;results.innerHTML='';status.textContent='기존 고객 선택됨';};
 }
 async function lookup(){const n=++generation;try{const data=await api('/customers/search',{method:'POST',body:JSON.stringify({query:input.value})});if(n!==generation||!root.isConnected)return;showChoices(data.items.filter(c=>c.kind===kind.value));}catch{if(n===generation)status.textContent='고객 검색 권한 또는 연결을 확인하세요.';}}
 input.oninput=()=>{chosen=null;generation++;requestId=crypto.randomUUID();status.textContent='새 고객으로 등록됩니다. 기존 업체는 목록에서 선택하세요.';clearTimeout(timer);timer=setTimeout(lookup,250);};
 kind.onchange=()=>{generation++;clearTimeout(timer);results.innerHTML='';chosen=null;requestId=crypto.randomUUID();status.textContent='새 고객으로 등록됩니다.';};
 root.readCustomer=()=>chosen;
 let saving=null;
 root.saveCustomer=()=>{if(saving)return saving;saving=(async()=>{if(chosen)return chosen.id;const name=input.value.trim();if(!name)throw Error('업체명 또는 주문자명을 입력하세요.');clearTimeout(timer);generation++;try{const result=await api('/customers',{method:'POST',body:JSON.stringify({name,kind:kind.value,request_id:requestId,prevent_duplicate:true})});chosen={id:result.id,name,kind:kind.value};results.innerHTML='';status.textContent='고객 등록됨';return chosen.id;}catch(error){await lookup();throw error;}})().finally(()=>{saving=null;});return saving;};
 root.customerDraft=()=>({name:input.value,kind:kind.value,...(chosen?{id:chosen.id}:{} )});
}

export async function showCustomerHistory({api,esc,modal,button},query=''){
 modal('업체·주문자 이력',`<form id="customer-search"><label>업체명 / 주문자명<input name="query" value="${esc(query)}" autocomplete="off" maxlength="120"></label><button type="submit">검색</button></form><div id="customer-results"></div><div id="customer-history"></div>`);
 const form=document.querySelector('#customer-search'),list=document.querySelector('#customer-results'),history=document.querySelector('#customer-history');let generation=0,historyGeneration=0;
 async function load(after='',append=false){const n=++generation;const result=await api('/customers/search',{method:'POST',body:JSON.stringify({query:form.elements.query.value,after})});if(n!==generation||!list.isConnected)return;const rows=result.items.map(c=>`<button type="button" data-customer="${esc(c.id)}">${esc(c.name)} · ${c.kind==='COMPANY'?'업체':'개인'} <small>${esc(c.id.slice(0,8))}</small></button>`).join('');list.querySelector('[data-next]')?.remove();if(append)list.insertAdjacentHTML('beforeend',rows);else list.innerHTML=rows||'<p>일치하는 고객이 없습니다.</p>';if(result.next)list.insertAdjacentHTML('beforeend',`<button type="button" data-next="${esc(result.next)}">더 보기</button>`);}
 async function details(id,after='',append=false){const sequence=++historyGeneration;const data=await api('/customers/'+encodeURIComponent(id)+'/history?after='+encodeURIComponent(after));if(!history.isConnected||sequence!==historyGeneration)return;const rows=data.items.map(row=>`<div class="line"><strong>${esc(row.day)} · ${esc(row.number)}</strong><span>${esc(row.model)} · ${esc(row.vin)}</span><span>${esc(row.name_at_dispatch)}</span></div>`).join('');history.querySelector('[data-history-next]')?.remove();if(append)history.insertAdjacentHTML('beforeend',rows);else history.innerHTML=`<h3>${esc(data.customer.name)} · 출고 이력</h3>`+(rows||'<p>연결된 출고 이력이 없습니다.</p>');if(data.next)history.insertAdjacentHTML('beforeend',`<button type="button" data-history-next="${esc(data.next)}" data-id="${esc(id)}">출고 더 보기</button>`);}
 const error=e=>{history.textContent=e.message;};
 form.onsubmit=e=>{e.preventDefault();historyGeneration++;history.innerHTML='';load().catch(error);};
 list.onclick=e=>{const b=e.target.closest('button');if(!b)return;if(b.dataset.next)load(b.dataset.next,true).catch(error);if(b.dataset.customer)details(b.dataset.customer).catch(error);};
 history.onclick=e=>{const b=e.target.closest('[data-history-next]');if(b)details(b.dataset.id,b.dataset.historyNext,true).catch(error);};
 await load();
}
