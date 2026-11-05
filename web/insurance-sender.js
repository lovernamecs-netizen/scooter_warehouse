let sending=false;
export const isInsuranceSending=()=>sending;
window.addEventListener("beforeunload",e=>{if(sending){e.preventDefault();e.returnValue="";}});
// CoolSMS 설정·문구·전송 UI. 비밀키는 브라우저 저장소에 보관하지 않습니다.
let currentTemplate = '';
let senderPhone = '';
let providerConfigured = false;
let settingsLoaded = false;

function encodeHumanError(esc, error) {
  return '<div class="notice warn"><strong>' + esc(error?.title || '발송에 실패했습니다.') +
    '</strong><p>' + esc(error?.action || '발송 내역을 먼저 확인해 주세요.') + '</p>' +
    '<details><summary>개발자용 오류 코드 보기</summary><pre>' +
    esc('코드: ' + (error?.technical?.code || '미제공') + '\n' +
        '원문: ' + (error?.technical?.detail || error?.message || '확인 불가')) +
    '</pre></details></div>';
}

export function mountInsuranceSender(target, {api, toast, esc, documents, jpegBytes, getPhone, refreshRows, role, getSelected, canSend=()=>true, getScope=()=>documents.map((_,i)=>i), scopeName=()=>'전체 목록'}) {
  if (!target) return {sendOne: async () => {}};
  target.innerHTML =
    '<section class="panel insurance-card insurance-send-card">' +
      '<div class="panel-head"><div><h2>CoolSMS · MMS 발송</h2>' +
      '<p class="muted">발송 전 수신번호와 보험증권을 확인하세요.</p></div>' +
      '<span class="badge blue">실제 MMS · 과금 발생</span></div>' +
      '<div class="insurance-send-grid">' +
        '<div class="insurance-message-pane">' +
          '<label for="insurance-message-template">MMS 전송 문구 편집</label>' +
          '<textarea id="insurance-message-template" rows="10" placeholder="{차량번호}를 입력하면 차량번호로 치환합니다."></textarea>' +
          '<div class="insurance-send-actions"><button type="button" data-mms="save-template">문구 저장</button>' +
          '<button type="button" data-mms="send-selected">선택 항목 MMS 발송</button>' +
          '<button type="button" data-mms="send-all" class="primary">전체 목록 일괄 MMS 발송</button></div>' +
          '<small>엑셀 연락처와 이미지가 준비된 건만 발송하며, 이미 접수된 건은 재발송하지 않습니다.</small>' +
          '<p id="insurance-send-progress" role="status"></p>' +
        '</div>' +
        '<div class="insurance-account-pane">' +
          '<div class="panel-head"><h3>CoolSMS 계정 설정</h3><span id="insurance-provider-status" class="badge">확인 중</span></div>' +
          '<label for="insurance-sender-phone">등록된 발신번호</label><input id="insurance-sender-phone" autocomplete="off" inputmode="tel" placeholder="01012345678">' +
          '<label for="insurance-api-key">API Key (빈 칸은 기존 설정 유지)</label><input id="insurance-api-key" autocomplete="off" spellcheck="false" type="password" placeholder="기존 Key 변경 시 입력">' +
          '<label for="insurance-api-secret">API Secret (빈 칸은 기존 설정 유지)</label><input id="insurance-api-secret" autocomplete="off" spellcheck="false" type="password" placeholder="기존 Secret 변경 시 입력">' +
          '<p class="muted">API Key와 Secret은 Windows 보안 저장소에 보관하며 브라우저에 재표시하지 않습니다.</p>' +
          '<button type="button" data-mms="save-account">계정 설정 저장</button>' +
        '</div>' +
      '</div>' +
      '<div id="insurance-send-feedback" role="status"></div>' +
    '</section>';
  const el = selector => target.querySelector(selector);
  const accountPane = el('.insurance-account-pane');
  if (role !== 'admin') {
    accountPane.innerHTML = '<div class="notice">CoolSMS 계정은 관리자만 설정할 수 있습니다.<p>개별·일괄 발송과 문구 편집은 사용할 수 있습니다.</p></div>';
  }
  const setProgress = value => {
    const node = el('#insurance-send-progress');
    if (node) node.textContent = value;
  };
  const feedback = html => { el('#insurance-send-feedback').innerHTML = html; };

  const loadConfig = async () => {
    try {
      const config = await api('/insurance/mms/settings');
      settingsLoaded = true;
      providerConfigured = !!(config.api_key_configured && config.api_secret_configured && config.sender_phone);
      currentTemplate = String(config.msg_template || '');
      senderPhone = String(config.sender_phone || '');
      el('#insurance-message-template').value = currentTemplate;
      const status = el('#insurance-provider-status');
      if (status) {
        status.textContent = providerConfigured ? '설정 완료' : '설정 필요';
        status.className = 'badge ' + (providerConfigured ? 'good' : 'warn');
      }
      if (role === 'admin') el('#insurance-sender-phone').value = senderPhone;
    } catch (e) {
      setProgress('계정 설정을 불러오지 못했습니다: ' + e.message);
    }
  };

  async function sendOne(index, {fromBatch = false} = {}) {
    const doc = documents[index];
    if (!doc || (sending&&!fromBatch)) return;
    if(!canSend())return toast('파일 처리가 끝난 뒤 발송하세요.');
    if (!settingsLoaded || !providerConfigured) {
      toast('CoolSMS 계정 설정을 먼저 완료해 주세요.');
      return;
    }
    const phone = getPhone(doc);
    if (!doc.within_limit || doc.review_required || !doc.plate || !/^01[016789]\d{7,8}$/.test(phone)) {
      toast('해당 고지문의 차량번호 검증, 이미지 용량, 수신 연락처를 확인해 주세요.');
      return;
    }
    if (doc.send_status === 'accepted' || doc.send_status === 'unknown' || doc.send_status === 'sending') {
      toast('이 건은 이미 접수되었거나 발송 결과 확인이 필요합니다.');
      return;
    }
    const text = el('#insurance-message-template').value.trim();
    if (!text) {
      toast('MMS 안내 문구를 입력해 주세요.');
      return;
    }
    if (!fromBatch && !window.confirm(doc.plate + ' / ' + phone + '에 MMS를 발송하시겠습니까?\nCoolSMS 요금이 발생할 수 있습니다.')) return;
    if(doc.send_status==='failed')doc.send_request_id=null;
    doc.send_request_id ||= crypto.randomUUID();
    sending=true;
    doc.send_status = 'sending';
    doc.send_error = null;
    refreshRows();
    setProgress(doc.plate + ' MMS 접수 요청 중…');
    try {
      const response = await api('/insurance/mms/send', {
        method: 'POST',
        body: JSON.stringify({
          request_id: doc.send_request_id,
          plate: doc.plate,
          phone,
          text,
          jpeg_base64: doc.jpeg_base64
        })
      });
      doc.send_status = response.state || 'unknown';
      doc.send_error = response.state === 'accepted' ? null : response;
      doc.send_group_id = response.group_id || '';
      if (response.state === 'accepted') {
        setProgress(doc.plate + ': MMS 접수 완료 (수신 완료는 아님).');
        if (!fromBatch) feedback('<div class="notice"><strong>' + esc(doc.plate) +
          ' MMS 발송 요청이 접수되었습니다.</strong><p>고객 단말의 최종 수신 상태는 CoolSMS 발송 내역에서 확인해 주세요.</p></div>');
      } else {
        setProgress(doc.plate + ': ' + response.title);
        if (!fromBatch) feedback(encodeHumanError(esc, response));
      }
    } catch (error) {
      // 통신 끊김은 발송이 되었을 수도 있으므로 자동 재시도를 막습니다.
      const uncertain = ![400,401,403,409,413,415,422].includes(error.status);
      doc.send_status = uncertain ? 'unknown' : 'failed';
      doc.send_error = {
        title: uncertain ? '발송 접수 여부가 확인되지 않았습니다.' : 'MMS 요청을 처리하지 못했습니다.',
        action: uncertain ?
          '중복 MMS가 전송되지 않도록 먼저 CoolSMS 콘솔에서 해당 발송 내역을 확인해 주세요.' :
          '발신번호, 계정 설정 및 파일 형식을 확인한 뒤 다시 시도하세요.',
        technical: {code: '', detail: error.message}
      };
      feedback(encodeHumanError(esc, doc.send_error));
      setProgress(doc.plate + ': ' + doc.send_error.title);
    }
    if(!fromBatch)sending=false;
    target.closest("#insurance-tool")?.querySelectorAll("input,textarea,button").forEach(x=>x.disabled=false);
    refreshRows();
  }

  async function sendAll(selectedOnly = false) {
    if(sending||!canSend())return;
    if (!settingsLoaded || !providerConfigured) return toast('CoolSMS 계정 설정이 필요합니다.');
    const scope=new Set(getScope());
    const requested = selectedOnly ? new Set(getSelected()) : scope;
    const eligible = documents.map((doc, index) => ({doc, index})).filter(({doc,index}) =>
      scope.has(index) && requested.has(index) &&
      doc.within_limit && doc.plate && !doc.review_required &&
      /^01[016789]\d{7,8}$/.test(getPhone(doc)) &&
      !['accepted', 'unknown', 'sending'].includes(doc.send_status)
    );
    if (!eligible.length) return toast('발송 가능한 항목이 없습니다. 차량번호·연락처·이미지와 기존 발송 상태를 확인하세요.');
    if (!window.confirm((selectedOnly ? '선택 항목 ' : scopeName()+' ') + '총 ' + eligible.length + '건을 CoolSMS로 실제 발송하시겠습니까?\n' +
      '유료 발송이며 전송 중에는 창을 닫지 마세요.')) return;
    sending=true;
    let accepted = 0, failed = 0, unknown = 0;
    const buttons = [...target.querySelectorAll('[data-mms="send-all"],[data-mms="send-selected"]')];
    buttons.forEach(button => button.disabled = true);
    try {
      for (let i = 0; i < eligible.length; i++) {
        setProgress((i + 1) + ' / ' + eligible.length + '건 발송 처리 중');
        await sendOne(eligible[i].index, {fromBatch: true});
        const state = eligible[i].doc.send_status;
        if (state === 'accepted') accepted++;
        else if (state === 'unknown') unknown++;
        else failed++;
      }
    } finally {
      sending=false;
      target.closest("#insurance-tool")?.querySelectorAll("input,textarea,button").forEach(x=>x.disabled=false);
      refreshRows();
      buttons.forEach(button => button.disabled = false);
      setProgress('일괄 발송 요청 종료 · 접수 ' + accepted + '건 / 실패 ' + failed +
        '건 / 접수 확인 필요 ' + unknown + '건');
      feedback('<div class="notice"><strong>일괄 MMS 처리 결과</strong><p>접수 ' + accepted +
        '건, 실패 ' + failed + '건, 확인 필요 ' + unknown +
        '건. 최종 수신 완료는 CoolSMS 발송 내역에서 확인해 주세요.</p></div>');
    }
  }

  target.addEventListener('click', async event => {
    const btn = event.target.closest('[data-mms]');
    if (!btn || btn.disabled) return;
    const action = btn.dataset.mms;
    if (action === 'send-all') {
      await sendAll();
    } else if (action === 'send-selected') {
      await sendAll(true);
    } else if (action === 'save-template') {
      const text = el('#insurance-message-template').value.trim();
      try {
        const response = await api('/insurance/mms/template', {
          method: 'PUT', body: JSON.stringify({msg_template: text})
        });
        currentTemplate = response.msg_template;
        toast('MMS 문구를 저장했습니다.');
      } catch (e) {
        feedback(encodeHumanError(esc, {title: '문구를 저장하지 못했습니다.',
          action: '입력값과 서버 상태를 확인해 주세요.', technical: {detail: e.message}}));
      }
    } else if (action === 'save-account') {
      if (role !== 'admin') return;
      const sender = el('#insurance-sender-phone').value;
      const key = el('#insurance-api-key').value;
      const secret = el('#insurance-api-secret').value;
      btn.disabled = true;
      try {
        await api('/insurance/mms/settings', {
          method: 'PUT',
          body: JSON.stringify({sender_phone: sender, api_key: key, api_secret: secret})
        });
        el('#insurance-api-key').value = '';
        el('#insurance-api-secret').value = '';
        await loadConfig();
        toast('CoolSMS 발신번호 및 계정 설정을 저장했습니다.');
      } catch (e) {
        feedback(encodeHumanError(esc, {title: 'CoolSMS 계정을 저장하지 못했습니다.',
          action: '발신번호와 Windows 보안 저장소 접근권한을 확인하세요.', technical: {detail: e.message}}));
      } finally {
        btn.disabled = false;
      }
    }
  });
  settingsLoaded=false;providerConfigured=false;
  loadConfig();

  return {sendOne};
}
