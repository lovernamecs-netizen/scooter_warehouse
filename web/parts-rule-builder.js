// Live item IDs are the identity; display codes/names may change independently.
let active=null;
export const partsRulesDirty=()=>!!(active?.root.isConnected&&active.dirty());
export async function openPartsRules(H,url,onSaved){
 let data=await H.api(url),rules=structuredClone(data.rules),baseline=JSON.stringify(rules),tab='B2B',model='',setKey=Object.keys(rules.sets)[0]||'',selected='',query='',category='',saving=false,conflict=false,pending=null;
 const e=H.esc,b=(label,action,extra='')=>`<button type="button" data-rb="${action}" ${extra}>${label}</button>`;
 H.modal('기본품 · 세트 구성','<div id="parts-rule-builder"></div>');
 const root=document.querySelector('#parts-rule-builder'),dialog=root.closest('dialog');dialog.classList.add('parts-rules-dialog');
 const close=()=>{dialog.classList.remove('parts-rules-dialog');if(active?.root===root)active=null;dialog.removeEventListener('close',close)};dialog.addEventListener('close',close);
 active={root,dirty:()=>JSON.stringify(rules)!==baseline};
 const item=id=>data.items.find(x=>x.id===id),valid=id=>!!item(id)?.active,name=id=>item(id)?.name||'삭제된 품목',code=id=>item(id)?.code||id;
 const modelRule=()=>rules.models[model];
 const mapping=()=>model?modelRule():rules;
 const defaults=()=>mapping()?.defaults?.[tab]||rules.defaults[tab]||[];
 const effectiveMode=id=>tab==='B2B'&&id==='CUP'?(modelRule()?.bracket==='RBF'?'DELIVERY':'INSTALL'):mapping()?.default_purposes?.[tab]?.[id]||rules.default_purposes?.[tab]?.[id]||(modelRule()?.preinstalled_bracket||tab==='B2B'&&['SC','MITT'].includes(id)?'INSTALL':item(id)?.purpose)||'INSTALL';
 const editableDefaults=()=>!model||!!modelRule()?.defaults;
 function mutate(fn){if(saving||pending||conflict)return;fn();draw()}
 function chosen(){if(!valid(selected))throw Error('사용 중인 품목 카드를 먼저 선택하세요.');return selected}
 function note(message){root.querySelector('[data-rb-message]').textContent=message}
 function card(id,slot,mode=null,locked=false){return `<div class="rb-equipped ${valid(id)?'':'rb-invalid'}" title="${e(name(id))}"><button type="button" data-rb="remove" data-slot="${e(slot)}" data-id="${e(id)}" aria-label="${e(name(id))} 제외" class="rb-remove">×</button><strong>${e(code(id))}</strong>${!valid(id)?'<small>사용 중지 / 삭제됨</small>':''}${locked&&mode==='INSTALL'?'<small>입고 기본 · 차감 없음</small>':''}${mode?b(mode==='INSTALL'?'장착 ▾':'별도 전달 ▾','mode',`data-id="${e(id)}" data-slot="${e(slot)}" class="rb-mode ${mode==='DELIVERY'?'delivery':''}"`):''}</div>`}
 function zone(slot,label,html){return `<section class="rb-drop" data-zone="${e(slot)}"><div class="rb-zone-head"><span>${e(label)}</span>${b('＋ 추가','add',`data-slot="${e(slot)}"`)}</div><div class="rb-equipped-list">${html||'<p class="rb-empty">＋ 품목을 여기로 끌어 놓으세요</p>'}</div></section>`}
 function modelOptions(common){return `${common?'<option value="">공통 기본품</option>':'<option value="">차종 선택</option>'}${data.models.map(m=>`<option value="${e(m.id)}" ${model===m.id?'selected':''}>${e(m.name)}${m.active?'':' (중지)'}</option>`).join('')}`}
 function summary(ids){return ids.map(id=>`<p><strong>${e(name(id))}</strong><small>${e(code(id))}${valid(id)?'':' · 사용 중지 / 삭제'}</small></p>`).join('')||'<p>구성된 품목이 없습니다.</p>'}
 function library(){
 const list=data.items.filter(i=>i.active&&(!category||i.category_id===category)&&(i.code+' '+i.name).toLowerCase().includes(query.toLowerCase()));
 root.querySelector('[data-library]').innerHTML=list.map(i=>`<button type="button" class="rb-item ${selected===i.id?'selected':''}" data-rb="select" data-id="${e(i.id)}" data-tip="${e(i.name)}" title="${e(i.name)}" draggable="${!saving&&!pending&&!conflict}" aria-label="${e(i.code+' · '+i.name)}" aria-pressed="${selected===i.id}"><span>◇</span><strong>${e(i.code)}</strong></button>`).join('')||'<p>해당 품목이 없습니다.</p>';
 root.querySelector('[data-selection]').textContent=selected?'선택: '+code(selected)+' · '+name(selected):'카드를 끌어 놓거나 선택 후 ＋ 추가';
 }
 function draw(){
 let editor='',ids=[];
 if(tab!=='SETS'&&tab!=='MODEL'){
  ids=defaults();const r=modelRule();editor=`<div class="rb-subhead"><h3>${tab} 기본품</h3><select data-rb-field="model" aria-label="기본품 적용 범위">${modelOptions(true)}</select></div>${model?`<label><input type="checkbox" data-rb-field="override" ${r?.defaults?'checked':''} ${!r?'disabled':''}> 이 차종 기본품 별도 설정</label>${!r?'<p class="notice warn">차종 연결 탭에서 이 차종 규칙을 먼저 사용 설정하세요.</p>':''}`:''}${zone('base',model&&!editableDefaults()?'공통 기본품 상속 · 변경하려면 별도 설정 선택':'주문 기본 포함',ids.map(id=>card(id,id,effectiveMode(id))).join(''))}<p class="hint">각 1개씩 포함됩니다. B2B 컵홀더는 FORZA 별도 전달, 다른 차종 장착 규칙을 유지합니다.</p>`;
 }else if(tab==='SETS'){
  const r=rules.sets[setKey],m=modelRule();ids=r?[r.item_id,m?.[r.component]].filter(Boolean):[];
  editor=`<div class="rb-subhead"><h3>박스 · 짐대 세트</h3><select data-rb-field="set" aria-label="세트 선택">${Object.keys(rules.sets).map(k=>`<option ${k===setKey?'selected':''}>${e(k)}</option>`).join('')}</select>${b('세트 추가','new-set')}${r?b('세트 삭제','delete-set'):''}</div>${r?`<label>세트 이름<input data-rb-field="set-name" value="${e(setKey)}" maxlength="80"></label><label>연결 차종<select data-rb-field="model" aria-label="세트 차종">${modelOptions(false)}</select></label><label>구성품 종류<select data-rb-field="component"><option value="slide" ${r.component==='slide'?'selected':''}>슬라이드 짐대</option><option value="bracket" ${r.component==='bracket'?'selected':''}>탑박스 브라켓</option></select></label><div class="rb-slots">${zone('item','박스 · 모든 차종 공통',r.item_id?card(r.item_id,'item',r.modes?.item||'INSTALL'):'')}${zone('component','짐대 / 브라켓 · 선택 차종',m?.[r.component]?card(m[r.component],'component',r.modes?.component||'INSTALL',m.factory_rack&&r.component==='bracket'):'')}</div><p class="hint">박스 및 장착·전달 설정은 이 세트 전체에 적용됩니다. 짐대·브라켓 변경은 선택 차종에서 같은 종류를 쓰는 세트에 적용됩니다.</p>`:'<p>세트를 추가한 뒤 구성하세요.</p>'}`;
 }else{
  const r=modelRule();ids=r?['slide','bracket','screen_b2b','screen_b2c'].map(k=>r[k]).filter(Boolean):[];
  editor=`<div class="rb-subhead"><h3>차종 연결 · 기본 장착</h3><select data-rb-field="model" aria-label="규칙 차종">${modelOptions(false)}</select></div>${model?`<label><input type="checkbox" data-rb-field="enabled" ${r?'checked':''}> 이 차종 규칙 사용</label>${r?`<div class="rb-slots">${[['slide','슬라이드 짐대'],['bracket','탑박스 브라켓'],['screen_b2b','B2B 기본 쉴드'],['screen_b2c','B2C 선택 쉴드']].map(([k,l])=>zone(k,l,r[k]?card(r[k],k):'')).join('')}</div><label><input type="checkbox" data-rb-field="factory_rack" ${r.factory_rack?'checked':''}> 신차 입고 기본 짐대·브라켓</label><label>품목 없는 기본 짐대 표시명<input data-rb-field="factory_label" value="${e(r.factory_label||'')}"></label><label><input type="checkbox" data-rb-field="preinstalled_bracket" ${r.preinstalled_bracket?'checked':''}> RBZ 입고 기본 장착 · 작업 및 차감 제외</label>`:''}`:'<p>연결할 차종을 선택하세요.</p>'}`;
 }
 root.innerHTML=`<div class="rb-toolbar"><p>코드 카드를 끌어 놓아 구성하세요.</p><div>${b('최신 자료 다시 읽기','reload')}${b('구성 저장','save',`class="primary" ${conflict?'disabled':''}`)}</div></div><p data-rb-message role="status" class="rb-message">${conflict?'다른 사용자가 변경했습니다. 초안은 보존했습니다. 최신 자료를 다시 읽은 뒤 구성하세요.':pending?'저장 결과를 확인하지 못했습니다. 같은 요청으로 재시도하세요.':''}</p><fieldset class="rb-layout" ${saving||pending||conflict?'disabled':''}><aside class="rb-library"><h3>재고 품목 <small>${data.items.filter(i=>i.active).length}개</small></h3><input data-rb-search placeholder="코드 또는 품목명 검색" value="${e(query)}" aria-label="품목 검색"><select data-rb-category aria-label="품목 카테고리"><option value="">전체 품목</option>${(data.categories||[]).filter(c=>c.active).map(c=>`<option value="${e(c.id)}" ${category===c.id?'selected':''}>${e(c.name)}</option>`).join('')}</select><div data-library class="rb-cards"></div><p data-selection class="rb-selection"></p><p class="hint">마우스를 올리면 한글 이름이 보입니다. 터치: 카드 선택 → ＋ 추가</p></aside><section class="rb-workspace"><nav class="rb-tabs">${[['B2B','B2B 기본품'],['B2C','B2C 기본품'],['SETS','박스 · 짐대 세트'],['MODEL','차종 연결']].map(([k,l])=>b(l,'tab',`data-tab="${k}" class="${tab===k?'active':''}"`)).join('')}</nav>${editor}<div class="rb-summary"><h4>구성 품목</h4>${summary(ids)}</div></section></fieldset><p class="hint">저장한 규칙은 이후 주문 구성에 사용됩니다. 기존 주문·출고·마감은 자동 변경하지 않습니다.</p>`;
 library();H.mark?.();
 root.querySelectorAll('[data-zone]').forEach(z=>{z.ondragover=ev=>{if(saving||pending||conflict)return;ev.preventDefault();z.classList.add('over')};z.ondragleave=()=>z.classList.remove('over');z.ondrop=ev=>{ev.preventDefault();z.classList.remove('over');run(()=>add(ev.dataTransfer.getData('text/plain'),z.dataset.zone))}});
 }
 function compatible(id){const i=item(id);if(model&&i?.model_ids?.length&&!i.model_ids.includes(model))throw Error('선택 차종과 호환되지 않는 품목입니다.');if(!model&&i?.model_ids?.length)throw Error('차종 전용 품목은 해당 차종 별도 기본품으로 구성하세요.')}
 function baseTarget(){if(!editableDefaults())throw Error('이 차종 기본품 별도 설정을 먼저 선택하세요.');return mapping()}
 function add(id,slot){if(!valid(id))throw Error('사용 중인 품목을 선택하세요.');compatible(id);mutate(()=>{
  if(tab==='SETS'){const r=rules.sets[setKey];if(!r)throw Error('세트를 먼저 추가하세요.');if(slot==='item')r.item_id=id;else {if(!modelRule())throw Error('사용 중인 차종 규칙을 먼저 선택하세요.');modelRule()[r.component]=id}}
  else if(tab==='MODEL'){if(!modelRule())throw Error('차종 규칙 사용을 먼저 선택하세요.');modelRule()[slot]=id}
  else{const r=baseTarget();if(r.defaults[tab].includes(id))throw Error('이미 구성된 품목입니다.');r.defaults[tab].push(id);r.default_purposes||={};r.default_purposes[tab]||={};r.default_purposes[tab][id]=effectiveMode(id)}
 })}
 function run(fn){try{fn()}catch(err){note(err.message)}}
 root.ondragstart=ev=>{const card=ev.target.closest('[data-rb="select"]');if(!card||saving||pending||conflict){ev.preventDefault();return}ev.dataTransfer.setData('text/plain',card.dataset.id);ev.dataTransfer.effectAllowed='copy'};
 root.oninput=ev=>{if(ev.target.matches('[data-rb-search]')){query=ev.target.value;library();H.mark?.()}};
 root.onchange=ev=>run(()=>{const el=ev.target,k=el.dataset.rbField;if(el.matches('[data-rb-category]')){category=el.value;library();H.mark?.();return}if(!k)return;
  if(k==='model'){model=el.value;draw();return}if(k==='set'){setKey=el.value;draw();return}
  mutate(()=>{if(k==='override'){const r=modelRule();if(el.checked){r.defaults=structuredClone(rules.defaults);r.default_purposes=structuredClone(rules.default_purposes||{})}else{delete r.defaults;delete r.default_purposes}}
   else if(k==='enabled'){if(el.checked)rules.models[model]={};else delete rules.models[model]}
   else if(k==='set-name'){const name=el.value.trim();if(!name||name!==setKey&&rules.sets[name])throw Error('세트 이름을 확인하세요.');const r=rules.sets[setKey];delete rules.sets[setKey];rules.sets[name]=r;setKey=name}
   else if(k==='component')rules.sets[setKey].component=el.value;
   else if(modelRule())modelRule()[k]=el.type==='checkbox'?el.checked:el.value;
  })});
 root.onclick=async ev=>{const el=ev.target.closest('[data-rb]');if(!el)return;ev.preventDefault();if(saving)return;const k=el.dataset.rb;
  if(k==='save'){await save();return}
  if(k==='reload'){if((active.dirty()||pending)&&!confirm('작성한 구성을 버리고 최신 자료를 다시 읽을까요?'))return;try{data=await H.api(url);rules=structuredClone(data.rules);baseline=JSON.stringify(rules);conflict=false;pending=null;selected='';if(!rules.sets[setKey])setKey=Object.keys(rules.sets)[0]||'';draw()}catch(err){note(err.message)}return}
  if(pending||conflict)return;
  run(()=>{if(k==='select'){selected=el.dataset.id;library();H.mark?.()}else if(k==='tab'){tab=el.dataset.tab;draw()}else if(k==='add')add(chosen(),el.dataset.slot);
   else mutate(()=>{if(k==='remove'){if(tab==='SETS'){const r=rules.sets[setKey];if(el.dataset.slot==='item')r.item_id='';else if(modelRule())modelRule()[r.component]=''}else if(tab==='MODEL')modelRule()[el.dataset.slot]='';else{const r=baseTarget();r.defaults[tab]=r.defaults[tab].filter(id=>id!==el.dataset.id);if(r.default_purposes?.[tab])delete r.default_purposes[tab][el.dataset.id]}}
    else if(k==='mode'){if(tab==='SETS'){const r=rules.sets[setKey];r.modes||={};const part=el.dataset.slot;r.modes[part]=(r.modes[part]||'INSTALL')==='INSTALL'?'DELIVERY':'INSTALL'}else{if(tab==='B2B'&&el.dataset.id==='CUP')throw Error('B2B 컵홀더는 FORZA 전달, 그 외 장착 규칙입니다.');const r=baseTarget(),mode=effectiveMode(el.dataset.id);r.default_purposes||={};r.default_purposes[tab]||={};r.default_purposes[tab][el.dataset.id]=mode==='INSTALL'?'DELIVERY':'INSTALL'}}
    else if(k==='new-set'){let n=1;while(rules.sets['새 세트 '+n])n++;setKey='새 세트 '+n;rules.sets[setKey]={item_id:'',component:'bracket'}}
    else if(k==='delete-set'){delete rules.sets[setKey];setKey=Object.keys(rules.sets)[0]||''}
   })})};
 async function save(){if(conflict||saving)return;pending||={action:'rules',rules:structuredClone(rules),revision:data.revision,request_id:crypto.randomUUID()};saving=true;H.setBusy(true);draw();
  try{await H.api('/parts/command',{method:'POST',body:JSON.stringify(pending)});baseline=JSON.stringify(rules);pending=null;H.mark?.();dialog.close();await onSaved();H.toast('기본품·세트 구성을 저장했습니다.')}
  catch(err){const text=err.message||'저장 실패';if(/다른 작업|재고가 변경/.test(text)){conflict=true;pending=null}else if(!/연결|재시도|결과를 확인/.test(text))pending=null;draw();note(text+(conflict?' · 최신 자료를 다시 읽어 주세요.':''))}
  finally{saving=false;H.setBusy(false);if(root.isConnected&&dialog.open){const message=root.querySelector('[data-rb-message]').textContent;draw();note(message)}}
 }
 draw();
}
