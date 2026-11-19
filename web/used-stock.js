import {openOriginal,photoName,dialogBack} from './photo-viewer.js';
import {capturePhoto,fileBase64,previewBase64,ocrBase64,cameraIcon,recognizeVin} from './camera.js';
import {vinCandidates,validVin} from './vin.js';
export function createUsedStock({api,send,modal,button,esc,field,toast,download,detail,user,today,vehicle,render,masters,formSafety}){
  let data=null,step=1,timer=null,index=0,pending=[],urls=[],cardUrls=[],formBaseline='',selectedPart='front',jobs=[],busy=false,hydration=0,suppressClickUntil=0;
  const accept='image/jpeg,image/png,image/webp,image/heic,image/heif,.heic,.heif';
  const stayQuery=()=>'?stay_id='+encodeURIComponent(data.stay_id||'');
  const $=s=>document.querySelector(s), editable=()=>!data.vehicle.id||data.editable;
  const views={front:'전면',left:'좌측면',rear:'후면',right:'우측면',cockpit:'콕핏',dashboard:'계기판'};
  const intake={whole:'차량 전체 사진 (메인)',plate:'차량 번호판 사진',vin:'차대번호',front:'전면',rear:'후면',left:'좌측면',right:'우측면',cockpit:'콕핏',other:'기타'};
  const wear={pad_front:'앞 패드',pad_rear:'뒤 패드',tire_front:'앞 타이어',tire_rear:'뒤 타이어'};
  const parts={front:'전면 카울',headlight:'헤드라이트',shield:'윈드스크린',mirror:'미러',handle:'핸들',floor:'발판',seat:'시트',rear:'후면 카울',left:'좌측 카울',right:'우측 카울',exhaust:'머플러',front_fender:'앞 펜더',rear_fender:'뒤 펜더'};
  const stop=()=>{clearInterval(timer);timer=null};
  $('#modal').addEventListener('close',stop);
  function release(){hydration++;urls.forEach(URL.revokeObjectURL);urls=[]}
  function objectURL(blob){const u=URL.createObjectURL(blob);urls.push(u);return u}
  const b=(label,act,extra='',style='')=>button(label,'used-'+act,extra,style);
  const attr=(category,key)=>`data-category="${category}" data-key="${key}"`;
  const list=(category,key)=>[...(data.media||[]),...pending].filter(x=>x.category===category&&(!key||x.key===key));
  function text(label,name,value,extra=''){return `<label class="used-field ${extra}"><span>${label}</span><textarea name="${name}" rows="2" maxlength="4000">${esc(value||'')}</textarea></label>`}
  function options(kind,id){return `<option value="">선택</option>`+masters(kind).map(m=>`<option value="${m.id}" ${m.id===id?'selected':''}>${esc(m.name)}</option>`).join('')}
  function titleFor(category,key){return ({product:views,intake,wear,damage:parts}[category]?.[key])||key}
  function modelName(modelId){return masters('model').find(m=>m.id===modelId)?.name||data?.vehicle?.model||'차종 미선택'}
  function colorName(colorId){return masters('color').find(m=>m.id===colorId)?.name||data?.vehicle?.color||'색상 미선택'}

  function tile(category,key,label){
    const photos=list(category,key),photo=photos.at(-1),legacy=category==='product'&&data.photos?.[key];
    return `<div class="used-photo-tile photo-drop" data-drop="true" ${attr(category,key)} aria-label="${esc(label)} 사진 영역">
      <button type="button" class="photo-tile-open" data-act="${photo?'used-original':legacy?'used-legacy-view':'used-photos'}" ${attr(category,key)} ${photo?`data-id="${photo.id}"`:''} aria-label="${esc(label)} ${photo||legacy?'원본 확대':'사진 추가'}">
        ${photo?`<img data-media="${photo.id}" alt="${esc(label)}">`:legacy?`<img src="data:image/jpeg;base64,${legacy.jpeg}" alt="${esc(label)}">`:`<span class="photo-placeholder">${cameraIcon}</span>`}
        <strong>${esc(label)}</strong>
        <small>${photos.length?photos.length+'장'+(photo.id.startsWith('pending-')?' · PC 저장 대기':''):legacy?'이전 등록 사진':editable()?'사진을 놓거나 촬영':'사진 없음'}</small>
      </button>
      ${editable()?`<button type="button" class="photo-tile-add" data-act="used-photos" ${attr(category,key)}>${photo||legacy?'사진 교체 / 촬영':'사진 촬영 / 등록'}</button>`:''}
    </div>`;
  }

  async function hydrate(){const generation=hydration,vehicleId=data.vehicle.id,query=stayQuery();const nodes=[...document.querySelectorAll('[data-media]')];await Promise.allSettled(nodes.map(async img=>{if(img.dataset.loaded===img.dataset.media)return;const id=img.dataset.media,p=pending.find(p=>p.id===id);img.dataset.loaded=id;if(p){img.src=p.url;return}try{const blob=await api('/used/'+vehicleId+'/photos/'+id+query+'&preview=true',{blob:true});if(img.isConnected&&generation===hydration)img.src=objectURL(blob)}catch{delete img.dataset.loaded;img.alt='미리보기 표시 불가 · 클릭하여 원본 확인'}}))}
  async function hydrateUsedCards(){
    const imgs=[...document.querySelectorAll('img[data-used-thumb]')];
    await Promise.allSettled(imgs.map(async img=>{
      const thumb=img.dataset.usedThumb,vid=img.dataset.vehicleId,sid=img.dataset.stayId||'';
      if(!thumb||!vid||img.dataset.loadedThumb===thumb)return;
      img.dataset.loadedThumb=thumb;
      try{
        const blob=await api('/used/'+vid+'/photos/'+thumb+'?stay_id='+encodeURIComponent(sid)+'&preview=true',{blob:true});
        if(img.isConnected){const u=URL.createObjectURL(blob);cardUrls.push(u);img.src=u;}
      }catch{img.closest('.used-card-photo-box')?.classList.add('no-thumb');}
    }));
  }
  const cardObserver=new MutationObserver(()=>{if(document.querySelector('img[data-used-thumb]'))hydrateUsedCards();});
  cardObserver.observe(document.body,{childList:true,subtree:true});

  function original(id,label){stop();readForm();const local=pending.find(x=>x.id===id),vehicleId=data.vehicle.id,query=stayQuery();openOriginal({label,id,download,load:()=>local?.file||api('/used/'+vehicleId+'/photos/'+id+query,{blob:true})});}
  function legacyOriginal(key){stop();readForm();const photo=data.photos[key];openOriginal({label:views[key]||key,id:key,download,load:async()=>await (await fetch('data:image/jpeg;base64,'+photo.jpeg)).blob()});}
  function rememberDamage(){const box=document.querySelector('.damage-inline');if(box&&editable()){const key=box.dataset.key;data.profile.damage||={};data.profile.damage[key]={status:box.querySelector('#damage-status').value,note:box.querySelector('#damage-note').value};}}
  async function exclusive(work){if(busy){toast('사진 저장 중입니다. 완료 후 다시 시도하세요.');return;}busy=true;formSafety?.setBusy(true);const fieldset=$('#used-form fieldset');if(fieldset)fieldset.disabled=true;try{return await work()}finally{busy=false;formSafety?.setBusy(false);if(fieldset?.isConnected)fieldset.disabled=false;showPending();}}
  function showPending(){const box=$('#web-photo-jobs');if(!box)return;box.innerHTML=pending.map(p=>`<p><strong>${esc(titleFor(p.category,p.key))}</strong> · ${esc(p.file.name||'촬영 사진')} · ${esc(p.error||'PC 저장 대기')} <button type="button" data-act="used-original" data-id="${p.id}" ${attr(p.category,p.key)}>원본 확인</button>${p.error?'<button type="button" data-act="used-retry">재시도</button>':''}</p>`).join('');}
  const photoScreen=()=>$('#modal').open&&$('#modal').classList.contains('used-wizard');
  const fileDrag=e=>Array.from(e.dataTransfer?.types||[]).includes('Files');
  for(const type of ['dragenter','dragover','dragleave','drop'])document.addEventListener(type,e=>{
    if(!photoScreen()||!fileDrag(e))return;
    const target=e.target.closest('[data-drop]');
    if(type==='dragenter'||type==='dragover'){e.preventDefault();if(target&&editable()){target.classList.add('drag-over');e.dataTransfer.dropEffect=busy?'none':'copy';}else e.dataTransfer.dropEffect='none';}
    if(type==='dragleave'&&target&&!target.contains(e.relatedTarget))target.classList.remove('drag-over');
    if(type==='drop'){e.preventDefault();document.querySelectorAll('.drag-over').forEach(x=>x.classList.remove('drag-over'));suppressClickUntil=Date.now()+350;if(target&&editable()){const {category,key}=target.dataset;receiveFiles([...e.dataTransfer.files],category,key).catch(e=>toast(e.message));}else toast('이름이 표시된 사진 영역에 놓아 주세요.');}
  });
  document.addEventListener('dragend',()=>document.querySelectorAll('.drag-over').forEach(x=>x.classList.remove('drag-over')));
  document.addEventListener('click',e=>{if(photoScreen()&&Date.now()<suppressClickUntil&&e.target.closest('[data-drop]')){e.preventDefault();e.stopImmediatePropagation();}},true);
  $('#modal').addEventListener('cancel',e=>{if(busy){e.preventDefault();e.stopImmediatePropagation();toast('사진 저장 중입니다.');}},true);
  $('#modal').addEventListener('close',()=>{if(!$('#modal').open){release();pending.forEach(p=>URL.revokeObjectURL(p.url));pending=[];}});

  function readForm(){
    const f=$('#used-form');if(!f)return;
    const p=data.profile,v=data.vehicle;
    for(const e of f.elements){
      if(!e.name)continue;
      const val=e.type==='checkbox'?e.checked:e.value;
      if(e.dataset.vehicle)v[e.name]=e.type==='number'?Number(val):val;
      else p[e.name]=Object.hasOwn(wear,e.name)||e.name==='mileage'?(val===''?null:Number(val)):val;
    }
    p.equipment_checked=true;
    if(p.oil_changed&&!p.oil_date)p.oil_date=today();
    p.equipment_notes=tags(p.equipment_notes||'').join(', ');
  }
  function tags(s){return [...new Set(String(s).split(/[,\n]+/).map(x=>x.trim()).filter(Boolean))].slice(0,50)}
  function fresh(){return {vehicle:{kind:'USED',year:Number(today().slice(0,4)),vin:'',received_date:today(),model_id:'',color_id:'',plate:'',smart_key:'',notes:'',manufactured_month:'',ubis_installed:true},profile:{mileage:null,exterior:'',equipment_notes:'',oil_date:today(),oil_changed:false,equipment_checked:true,repairs_done:false,washed:false,damage:{}},media:[],photos:{},editable:true,missing:[],ready:false,registration:'입고 저장 시 자동 생성'}}
  async function open(id,start=1,prefill={}){if(busy)throw Error('사진 저장 중입니다.');stop();release();pending.forEach(p=>URL.revokeObjectURL(p.url));pending=[];data=id?await api('/used/'+id):fresh();if(!id)Object.assign(data.vehicle,prefill);data.profile={...fresh().profile,...data.profile};formBaseline=JSON.stringify([data.vehicle,data.profile]);step=1;paint()}

  function simpleSheet(){
    const v=data.vehicle,p=data.profile;
    const input=(l,k,type='text',extra='')=>field(l,k,v[k]??'',type,`data-vehicle="1" ${extra}`);
    const plateText=(v.plate||'').trim()||'번호판 미등록';
    const isUnreg=!v.plate||plateText.includes('미등록');
    const isNew=!v.id;
    return `
      <section class="used-simple-summary-header">
        <div class="used-simple-top-row">
          <div class="used-quick-badges">
            <span class="mono used-reg-pill">${esc(data.registration||'신규 입고')}</span>
            <span class="used-state-pill ${data.ready?'ready':'progress'}">${data.ready?'✓ 상품화 완료':'상품화 진행 중'}</span>
          </div>
          <div class="used-simple-meta">${esc(colorName(v.color_id))} · ${p.mileage==null?'주행거리 미등록':Number(p.mileage).toLocaleString()+' km'}</div>
        </div>
        <div class="used-simple-title-row">
          <div class="used-model-xl">${esc(modelName(v.model_id))}</div>
          <div class="used-plate-xl ${isUnreg?'unregistered':''}">${esc(plateText)}</div>
        </div>
        <div class="used-vin-readable mono">차대번호(VIN): ${esc(v.vin||'미등록')}</div>
      </section>

      <section class="used-intake-two-photos">
        <div class="used-photo-primary-col">
          ${tile('intake','whole','① 차량 전체 사진 (메인)')}
        </div>
        <div class="used-photo-secondary-col">
          ${tile('intake','plate','② 차량 번호판 사진 (두번째)')}
        </div>
      </section>

      <section class="used-three-checks-box">
        <div class="used-three-checks-grid">
          <label class="check used-big-check"><input type="checkbox" name="repairs_done" ${p.repairs_done?'checked':''}><span>정비 완료</span></label>
          <label class="check used-big-check"><input type="checkbox" name="washed" ${p.washed?'checked':''}><span>세차 완료</span></label>
          <label class="check used-big-check"><input type="checkbox" name="oil_changed" ${p.oil_changed?'checked':''}><span>엔진오일 교환</span></label>
        </div>
        ${editable()?b('✓ 상품화 완료 확정','complete','','primary used-complete-big-btn'):''}
      </section>

      <details class="used-options-Toggle" ${isNew?'open':''}>
        <summary>차량 상세 제원 · 브랜드 · 타이어/패드 잔량 · 차대 OCR 옵션 펼치기</summary>
        <div class="used-aligned-options-body">
          <div class="data-grid used-clean-grid">
            <label>브랜드<select id="used-brand"><option value="">전체 브랜드</option>${masters('brand').map(m=>`<option value="${m.id}" ${masters('model').find(x=>x.id===v.model_id)?.detail?.brand_id===m.id?'selected':''}>${esc(m.name)}</option>`).join('')}</select></label>
            <label>차량 이름 (차종)<select name="model_id" data-vehicle="1" required>${options('model',v.model_id)}</select></label>
            ${input('번호판 번호','plate')}
            <label>차량 색상<select name="color_id" data-vehicle="1" required>${options('color',v.color_id)}</select></label>
            ${field('주행거리 · km','mileage',p.mileage??'','number','min="0" max="3000000"')}
            ${field('엔진오일 교환일','oil_date',p.oil_date||today(),'date',`max="${today()}"`)}
            ${input('연식','year','number','min="1900" max="2100"')}
            ${input('제조년월','manufactured_month','month')}
            ${!v.id?input('입고일','received_date','date'):`<div><label>입고일</label><p>${esc((v.received_at||'').slice(0,10))}</p></div>`}
            ${input('스마트키 시리얼','smart_key')}
          </div>

          <div class="used-vin-ocr-bar">
            <div class="used-vin-input-wrap">${input('차대번호 (VIN 17자리)','vin','text','maxlength="17"')}</div>
            <div class="used-vin-ocr-actions">
              ${editable()?b('📷 차대 OCR 촬영','vin-camera','','ghost'):''}
            </div>
          </div>

          <div class="used-wear-compact-grid">
            ${Object.entries(wear).map(([k,l])=>field(l+' 잔량 · %',k,p[k]??80,'number','min="0" max="100"')).join('')}
          </div>

          <div class="data-grid used-clean-grid">
            ${text('외장 상태 메모','exterior',p.exterior,'span2')}
            ${text('장착품 메모 · 자유입력','equipment_notes',p.equipment_notes,'span2')}
          </div>
        </div>
      </details>
    `;
  }

  function paint(){
    const scroll=$('#modal .modal-body')?.scrollTop||0;stop();release();
    const body=`
      ${data.stays?.length>1?`<label class="used-stay-label">입고 회차<select id="used-stay">${data.stays.map(x=>`<option value="${x.id}" ${x.id===data.stay_id?'selected':''}>${esc(x.received_at.slice(0,10))} · ${x.closed_at?'출고 이력':'현재 입고'}</option>`).join('')}</select></label>`:''}
      <form id="used-form"><fieldset ${editable()?'':'disabled'}>${simpleSheet()}</fieldset></form>
      <div id="web-photo-jobs" aria-live="polite"></div>
      <div id="photo-jobs" aria-live="polite"></div>
    `;
    modal('중고차 상품화 점검',body,`<span class="used-footer-label">${esc(data.registration||'')}</span>${editable()?b('임시 저장','save'):''}${editable()?b('✓ 상품화 완료 확정','complete','','primary'):''}${button('닫기','close')}`);
    $('#modal').classList.add('used-product-modal','used-wizard');
    $('#used-form fieldset').disabled=false;
    if(!editable())$('#used-form').querySelectorAll('input,select,textarea').forEach(x=>x.disabled=true);

    const staySelect=$('#used-stay');if(staySelect)staySelect.onchange=()=>exclusive(async()=>{try{await saveIfDirty();data=await api('/used/'+data.vehicle.id+'?stay_id='+encodeURIComponent(staySelect.value));formBaseline=JSON.stringify([data.vehicle,data.profile]);paint()}catch(e){toast(e.message)}});
    const brand=$('#used-brand');if(brand)brand.onchange=()=>{const select=$('#used-form [name=model_id]');select.innerHTML='<option value="">선택</option>'+masters('model').filter(m=>!brand.value||m.detail?.brand_id===brand.value).map(m=>`<option value="${m.id}">${esc(m.name)}</option>`).join('')};
    const modelSel=$('#used-form [name=model_id]');if(modelSel)modelSel.addEventListener('change',()=>{const el=$('.used-model-xl');if(el)el.textContent=modelName(modelSel.value);});
    const plateInp=$('#used-form [name=plate]');if(plateInp)plateInp.addEventListener('input',()=>{const el=$('.used-plate-xl');if(el){const v=plateInp.value.trim()||'번호판 미등록';el.textContent=v;el.classList.toggle('unregistered',!plateInp.value.trim());}});
    const vinInp=$('#used-form [name=vin]');if(vinInp)vinInp.addEventListener('input',()=>{const el=$('.used-vin-readable');if(el)el.textContent='차대번호(VIN): '+(vinInp.value.trim()||'미등록');});
    hydrate();showJobs();showPending();formSafety?.opened();$('#modal .modal-body').scrollTop=scroll;
  }

  async function save(complete=false){if(!editable())return;readForm();const f=$('#used-form');if(f&&!f.reportValidity()){const opt=$('.used-options-Toggle');if(opt)opt.open=true;f.reportValidity();throw Error('필수 입력 항목(차종·색상)을 확인하세요.');}const v=data.vehicle,p=data.profile;
    if(!v.model_id||!v.color_id){const opt=$('.used-options-Toggle');if(opt)opt.open=true;throw Error('차종과 색상을 선택하세요.');}
    if(v.vin&&!validVin(v.vin.trim().toUpperCase())){const opt=$('.used-options-Toggle');if(opt)opt.open=true;throw Error('VIN은 영문·숫자 17자리입니다.');}v.vin=(v.vin||'').trim().toUpperCase();
    if(v.id&&vehicle(v.id)?.vin&&v.vin!==vehicle(v.id).vin){if(user().role!=='admin')throw Error('등록된 VIN 변경은 관리자만 가능합니다.');const reason=prompt('VIN 변경 사유');if(!reason?.trim())throw Error('VIN 변경을 취소했습니다.');v.reason=reason.trim();}
    if(v.id){await send('used_record',{vehicle_id:v.id,version:v.version,vehicle:{model_id:v.model_id,color_id:v.color_id,year:Number(v.year),manufactured_month:v.manufactured_month||'',plate:v.plate||'',smart_key:v.smart_key||'',vin:v.vin,reason:v.reason||''},profile:p,complete});}
    else {const result=await send('receive',{...v,kind:'USED',year:Number(v.year),used_profile:p});v.id=result.vehicle_id;}
    data=await api('/used/'+v.id);formBaseline=JSON.stringify([data.vehicle,data.profile]);formSafety?.mark();
    const failed=[];
    for(const photo of [...pending]){try{const body=new FormData();body.append('file',photo.file);body.append('upload_id',photo.id.replace('pending-',''));body.append('stay_id',photo.stay_id||data.stay_id);body.append('category',photo.category);body.append('key',photo.key);await api('/used/'+v.id+'/upload',{method:'POST',body});pending=pending.filter(p=>p!==photo);URL.revokeObjectURL(photo.url);}catch(e){photo.error=e.message;failed.push(photo);}}
    data=await api('/used/'+v.id+stayQuery());formBaseline=JSON.stringify([data.vehicle,data.profile]);render();if(failed.length)throw Error(`${failed.length}장 저장 실패. 원본은 이 화면에 보관 중입니다. 재시도하거나 원본을 보관하세요.`);
  }
  async function saveIfDirty(){readForm();if(editable()&&(!data.vehicle.id||pending.length||JSON.stringify([data.vehicle,data.profile])!==formBaseline))await save()}
  async function photoPanel(category,key){if(busy)return;readForm();rememberDamage();stop();const title=titleFor(category,key),items=list(category,key),inline=category==='damage'&&!!$('#damage-detail');const dlg=document.createElement(inline?'section':'dialog');dlg.className='used-photo-dialog'+(inline?' damage-inline':'')+(items.length<=1?' single-photo':'');dlg.dataset.key=key;dlg.dataset.category=category;dlg.dataset.drop='true';
    dlg.innerHTML=`<header><h3>${esc(title)}</h3><button type="button" data-p="close" aria-label="사진 패널 닫기">닫기 ✕</button></header><div class="photo-panel-body"><div class="used-photo-panel-grid">${items.map(p=>`<article><button type="button" class="photo-panel-open" data-p="original" data-id="${p.id}" aria-label="${esc(title)} 원본 확대"><img data-media="${p.id}" alt="${esc(title)}"></button><div><button type="button" data-p="download" data-id="${p.id}">원본 다운로드</button>${editable()?`<button type="button" class="danger" data-p="delete" data-id="${p.id}">삭제</button>`:''}</div>${p.error?`<p role="alert">${esc(p.error)}</p>`:''}</article>`).join('')||'<p class="empty">사진을 여기에 놓거나 아래에서 추가하세요.</p>'}</div></div><footer>${editable()?`<button type="button" data-p="camera">${cameraIcon} 촬영</button><button type="button" data-p="upload">${category==='product'&&items.length?'파일로 교체':'파일 업로드'}</button>`:''}<button type="button" data-p="close">완료</button></footer><input type="file" accept="${accept}" ${category==='product'?'':'multiple'} hidden><input type="file" data-camera accept="image/*" capture="environment" hidden>`;
    let dismiss=()=>{dlg.remove();paint();};let close=()=>{if(busy){toast('사진 저장 중입니다.');return;}dismiss();};
    document.body.append(dlg);dlg.showModal();const backClose=dialogBack(dlg,()=>{dlg.close();dlg.remove();paint();},()=>{if(busy){toast('사진 저장 중입니다.');return false;}return true;});close=()=>{if(busy){toast('사진 저장 중입니다.');return;}backClose();};dlg.addEventListener('cancel',e=>{if(busy){e.preventDefault();e.stopImmediatePropagation();}},true);
    const reload=async()=>{if(!dlg.isConnected)return;close();setTimeout(()=>photoPanel(category,key),60);};
    hydrate();
    const file=dlg.querySelector('input[type=file]'),camera=dlg.querySelector('[data-camera]');
    for(const input of [file,camera])input.onchange=async()=>{await receiveFiles([...input.files],category,key);input.value='';};
    dlg.onclick=async e=>{const action=e.target.closest('[data-p]'),id=action?.dataset.id;if(!action)return;try{
      if(action.dataset.p==='close'){close();return;}if(action.dataset.p==='original'){original(id,title);return;}if(busy){toast('사진 저장 중입니다.');return;}
      if(action.dataset.p==='upload'){file.click();return;}
      if(action.dataset.p==='camera'){const bridge=window.WarehouseNative;
        if(bridge?.capturePhoto){await exclusive(async()=>{await saveIfDirty();const metadata=JSON.stringify({vehicle_id:data.vehicle.id,stay_id:data.stay_id,category,key});bridge.capturePhoto(metadata);});return;}
        if(!bridge&&matchMedia('(pointer:coarse)').matches){camera.click();return;}
        const shot=await capturePhoto();if(shot)await receiveFiles([shot],category,key);return;
      }
      if(action.dataset.p==='download'){const p=pending.find(x=>x.id===id),blob=p?.file||await api('/used/'+data.vehicle.id+'/photos/'+id+stayQuery(),{blob:true});download(blob,photoName(title,id,blob));return;}
      if(action.dataset.p==='delete'&&confirm('이 사진을 삭제할까요?')){await exclusive(async()=>{const p=pending.find(x=>x.id===id);if(p){URL.revokeObjectURL(p.url);pending=pending.filter(x=>x!==p);}else{await saveIfDirty();await send('used_media',{vehicle_id:data.vehicle.id,version:data.vehicle.version,category,key,id,remove:true});data=await api('/used/'+data.vehicle.id+stayQuery());formBaseline=JSON.stringify([data.vehicle,data.profile]);}});await reload();}
    }catch(e){toast(e.message)}};
  }
  function validatePhoto(file){if(!file.size||file.size>25000000)throw Error('사진은 0바이트 초과, 25MB 이하로 선택하세요.');if(!['image/jpeg','image/png','image/webp','image/heic','image/heif'].includes(file.type)&&!/\.hei[cf]$/i.test(file.name))throw Error('JPG, PNG, WebP, HEIC 사진을 선택하세요.');}
  async function receiveFiles(files,category,key){if(!files.length)return;if(!editable())throw Error('사진 등록 권한이 없습니다.');if(busy){toast('사진 저장 중입니다. 완료 후 다시 놓아 주세요.');return;}
    try{files.forEach(validatePhoto);}catch(e){toast(e.message);return;}
    readForm();const panel=document.querySelector('.used-photo-dialog[data-drop]');
    await exclusive(async()=>{
      for(const file of files)pending.push({id:'pending-'+crypto.randomUUID(),file,url:URL.createObjectURL(file),category,key,stay_id:data.stay_id||null});
      try{if(data.vehicle.id)await save(data.ready&&JSON.stringify([data.vehicle,data.profile])===formBaseline);else toast('입고 저장 시 사진도 함께 전송됩니다.');}catch(e){toast(e.message);}
    });
    if(panel){panel.querySelector('[data-p=close]').click();setTimeout(()=>photoPanel(category,key),80);}else{paint();}showPending();
  }
  async function addPhoto(file,category,key){await receiveFiles([file],category,key);}
  async function vinCamera(){readForm();const file=await capturePhoto();if(!file)return;await addPhoto(file,'intake','vin');paint();try{const encoded=await ocrBase64(file);const result=await recognizeVin(api,encoded);const candidates=vinCandidates(result.raw||'',result.candidates||[]);const dlg=document.createElement('dialog');dlg.className='used-photo-dialog';dlg.innerHTML=`<header><h3>VIN 확인</h3></header><img class="used-vin-original" src="${objectURL(file)}" alt="VIN 촬영 원본"><input maxlength="17" value="${esc(candidates[0]||'')}" aria-label="차대번호"><div>${candidates.map(v=>`<button type="button" data-vin="${v}">${v}</button>`).join('')}</div><small>S / 5는 원본과 비교해 수정하세요.</small><footer><button type="button" data-v="cancel">취소</button><button type="button" data-v="confirm">확인</button></footer>`;document.body.append(dlg);dlg.showModal();const close=()=>{dlg.close();dlg.remove()};dlg.addEventListener('cancel',e=>{e.preventDefault();close()});dlg.onclick=e=>{const el=e.target.closest('button');if(!el)return;if(el.dataset.vin)dlg.querySelector('input').value=el.dataset.vin;if(el.dataset.v==='cancel')close();if(el.dataset.v==='confirm'){const value=dlg.querySelector('input').value.trim().toUpperCase();if(!validVin(value)){toast('17자리 VIN을 확인하세요.');return}data.vehicle.vin=value;close();paint();}}}catch(e){toast(e.message)}}
  async function handle(act,d){const a=act.replace('used-','');if(busy){toast('사진 저장 중입니다.');return;}if(a==='original'){original(d.id,titleFor(d.category,d.key));return;}if(a==='legacy-view'){legacyOriginal(d.key);return;}if(a==='retry'){await exclusive(async()=>{try{await save(data.ready)}catch(e){toast(e.message)}});return}if(a==='step'){step=1;paint();return;}if(a==='save'||a==='complete'){await exclusive(async()=>{try{await save(a==='complete');paint();toast(a==='complete'?'상품화 완료 확정되었습니다.':'저장했습니다.');}finally{showPending();}});return}if(a==='photos'){await photoPanel(d.category,d.key);return}if(a==='metadata'){download(new Blob([JSON.stringify(await api('/used/'+data.vehicle.id+'/metadata'+stayQuery()),null,2)],{type:'application/json'}),data.registration+'.json');return}if(a==='folder'){await api('/used/'+data.vehicle.id+'/open-folder',{method:'POST'});toast('PC 서버에서 폴더를 열었습니다.');return}if(a==='vin-camera'){await vinCamera();return}if(a==='zip'){await saveIfDirty();download(await api('/used/'+data.vehicle.id+'/download'+stayQuery()+'&category='+d.category,{blob:true}),(data.registration||'used')+'-'+d.category+'.zip');return}}
  function showJobs(){const box=$('#photo-jobs');if(!box)return;const labels={capturing:'촬영 중',pending:'전송 대기',uploading:'PC 저장 중',saved:'PC 저장 완료',failed:'저장 실패',login_required:'전송 대기 · 다시 로그인'};box.innerHTML=jobs.filter(j=>j.vehicle_id===data.vehicle.id&&j.stay_id===data.stay_id).map(j=>`<p><img src="${j.preview||''}" alt="촬영 완료" style="width:44px;height:44px;object-fit:cover"> ${esc(titleFor(j.category,j.key))} · ${esc(labels[j.status]||j.status)} ${j.status!=='saved'?`<button type="button" data-export-photo="${j.id}">원본 보관</button><button type="button" data-retry="${j.id}">재전송</button><button type="button" data-discard="${j.id}">대기 사진 삭제</button>`:''}<small>${esc(j.message||'')}</small></p>`).join('');box.onclick=e=>{const original=e.target.closest('[data-export-photo]')?.dataset.exportPhoto;if(original)window.WarehouseNative?.exportPhoto(original);const retry=e.target.closest('[data-retry]')?.dataset.retry;if(retry)window.WarehouseNative?.retryPhoto(retry);const id=e.target.closest('[data-discard]')?.dataset.discard;if(id)window.WarehouseNative?.discardPhoto(id)}}
  window.onPhotoJobs=next=>{const changed=JSON.stringify(jobs)!==JSON.stringify(next);jobs=next;showJobs();if(!busy&&changed&&data?.vehicle.id&&next.some(j=>j.status==='saved'&&j.vehicle_id===data.vehicle.id&&j.stay_id===data.stay_id)){readForm();const vehicleId=data.vehicle.id,stayId=data.stay_id;api('/used/'+vehicleId+stayQuery()).then(latest=>{if(busy||data.vehicle.id!==vehicleId||data.stay_id!==stayId||!$('#modal').open)return;readForm();const [oldVehicle,oldProfile]=JSON.parse(formBaseline),same=(a,b)=>JSON.stringify(a)===JSON.stringify(b);const patches={vehicle:{},profile:{}};let conflict=false;for(const [kind,base] of [['vehicle',oldVehicle],['profile',oldProfile]])for(const key of Object.keys(data[kind])){if(key==='version')continue;if(!same(data[kind][key],base[key])){if(!same(latest[kind][key],base[key])&&!same(latest[kind][key],data[kind][key]))conflict=true;patches[kind][key]=data[kind][key];}}data.media=latest.media;if(!conflict){formBaseline=JSON.stringify([latest.vehicle,latest.profile]);data.vehicle={...latest.vehicle,...patches.vehicle};data.profile={...latest.profile,...patches.profile};}hydrate()}).catch(()=>{})}};
  setInterval(()=>{if(window.WarehouseNative?.photoJobs&&data&&$('#modal').open)WarehouseNative.photoJobs(data.vehicle.id,data.stay_id)},2500);
  window.addEventListener('warehouse-photo-captured',()=>window.WarehouseNative?.photoJobs(data?.vehicle.id||'',data?.stay_id||''));
  return {open,handle,isBusy(){return busy;},isDirty(){return !!data&&$('#modal').classList.contains('used-wizard')&&(pending.length>0||(readForm(),JSON.stringify([data.vehicle,data.profile])!==formBaseline))}};
}
