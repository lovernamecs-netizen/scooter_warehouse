// 보험증권 변환·연락처·CoolSMS 발송 통합 UI.
import {mountInsuranceSender} from './insurance-sender.js';
let documents = [];
let contacts = {};
let conflictPlates = [];
const cleanPlate = value => String(value || '').normalize('NFKC').replace(/[^0-9가-힣]/g, '');
const cleanPhone = value => String(value || '').replace(/\D/g, '');
const isPhone = value => /^01[016789]\d{7,8}$/.test(value);

export function clearInsuranceTool() {
  documents = [];
  contacts = {};
  conflictPlates = [];
}

function download(blob, filename) {
  const href = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = href;
  a.download = filename;
  a.click();
  setTimeout(() => URL.revokeObjectURL(href), 10000);
}

function jpegBytes(doc) {
  const bytes = atob(doc.jpeg_base64);
  const data = new Uint8Array(bytes.length);
  for (let i = 0; i < bytes.length; i++) data[i] = bytes.charCodeAt(i);
  return data;
}

// JPEG는 이미 압축되므로 ZIP에는 무손실 Store 방식만 사용.
function zipFile(items) {
  const encoder = new TextEncoder();
  const output = [];
  const central = [];
  let offset = 0;
  const table = new Uint32Array(256);
  for (let i = 0; i < 256; i++) {
    let c = i;
    for (let j = 0; j < 8; j++) c = c & 1 ? 0xedb88320 ^ (c >>> 1) : c >>> 1;
    table[i] = c >>> 0;
  }
  const crc32 = data => {
    let crc = 0xffffffff;
    for (const byte of data) crc = table[(crc ^ byte) & 255] ^ (crc >>> 8);
    return (crc ^ 0xffffffff) >>> 0;
  };
  for (const item of items) {
    const filename = encoder.encode(item.name);
    const bytes = item.bytes;
    const checksum = crc32(bytes);
    const local = new Uint8Array(30 + filename.length);
    const l = new DataView(local.buffer);
    l.setUint32(0, 0x04034b50, true);
    l.setUint16(4, 20, true);
    l.setUint16(6, 0x800, true); // UTF-8 filename
    l.setUint16(10, 0, true);
    l.setUint16(12, 0x21, true);
    l.setUint32(14, checksum, true);
    l.setUint32(18, bytes.length, true);
    l.setUint32(22, bytes.length, true);
    l.setUint16(26, filename.length, true);
    local.set(filename, 30);
    output.push(local, bytes);
    const dir = new Uint8Array(46 + filename.length);
    const d = new DataView(dir.buffer);
    d.setUint32(0, 0x02014b50, true);
    d.setUint16(4, 20, true);
    d.setUint16(6, 20, true);
    d.setUint16(8, 0x800, true);
    d.setUint16(14, 0x21, true);
    d.setUint32(16, checksum, true);
    d.setUint32(20, bytes.length, true);
    d.setUint32(24, bytes.length, true);
    d.setUint16(28, filename.length, true);
    d.setUint32(42, offset, true);
    dir.set(filename, 46);
    central.push(dir);
    offset += local.length + bytes.length;
  }
  const centralSize = central.reduce((sum, arr) => sum + arr.length, 0);
  const end = new Uint8Array(22);
  const e = new DataView(end.buffer);
  e.setUint32(0, 0x06054b50, true);
  e.setUint16(8, items.length, true);
  e.setUint16(10, items.length, true);
  e.setUint32(12, centralSize, true);
  e.setUint32(16, offset, true);
  return new Blob([...output, ...central, end], { type: 'application/zip' });
}

export function renderInsuranceTool(container, {api, toast, esc, role}) {
  if (!container) return;
  container.innerHTML =
    '<section class="panel insurance-card">' +
      '<div class="panel-head"><div><h2>보험증권 · 이미지 준비</h2><p class="muted">PDF 원본은 수정하지 않습니다. 지정된 흰색 가림 영역만 적용하고 RGB 컬러로 JPG를 생성합니다.</p></div></div>' +
      '<div class="insurance-actions">' +
        '<label class="insurance-upload">보험증권 PDF 선택 (다중)<input data-insurance="pdf" type="file" accept=".pdf,application/pdf" multiple></label>' +
        '<label class="insurance-upload secondary">JPG 폴더 선택<input data-insurance="jpg" type="file" accept="image/jpeg,.jpg,.jpeg" webkitdirectory multiple></label>' +
        '<label class="insurance-upload secondary">JPG 파일 선택<input data-insurance="jpg" type="file" accept="image/jpeg,.jpg,.jpeg" multiple></label>' +
        '<label class="insurance-upload secondary">거래처 연락처 CSV/XLS/XLSX<input data-insurance="contacts" type="file" accept=".csv,.xls,.xlsx"></label>' +
        '<button type="button" data-insurance="zip" class="primary">검증된 JPG 일괄 ZIP</button>' +
        '<button type="button" data-insurance="clear">목록 초기화</button>' +
      '</div>' +
      '<p class="notice">문서의 원본 색상·여백·배치를 그대로 유지하고 지정된 흰색 영역만 처리합니다. JPG는 199KB 이하에서만 발송하며, 수신자·차량번호 확인 후 CoolSMS로 전송합니다.</p>' +
      '<p id="insurance-progress" role="status" class="muted"></p>' +
      '<div id="insurance-summary" class="insurance-summary"></div>' +
      '<div class="table-wrap"><table class="insurance-table"><thead><tr><th>보험증권</th><th>차량번호 · 원본 확인</th><th>연락처</th><th>용량 · 상태</th><th>미리보기 / 저장</th><th>MMS 개별 발송 · 결과</th></tr></thead><tbody id="insurance-rows"></tbody></table></div>' +
    '</section>' +
    '<div id="insurance-send-mount"></div>' +
    '<section class="panel insurance-card">' +
      '<h2>MMS 발송 실패 사유 확인</h2>' +
      '<p class="muted">CoolSMS에서 실패했을 때 오류 원인과 필요한 조치를 자연어로 안내합니다. 표의 발송 결과에서도 상세 코드를 펼쳐 볼 수 있습니다.</p>' +
      '<div class="insurance-error-fields"><div><label>오류 코드</label><input id="insurance-error-code" placeholder="예: 1030" maxlength="50"></div>' +
      '<div><label>오류 내용</label><input id="insurance-error-detail" placeholder="예: 잔액이 부족합니다." maxlength="250"></div>' +
      '<button type="button" data-insurance="diagnose">오류 설명 확인</button></div>' +
      '<div id="insurance-error-result" aria-live="polite"></div>' +
    '</section>';
  const el = selector => container.querySelector(selector);
  const summary = () => {
    const ready = documents.filter(d => d.within_limit && d.plate && !d.review_required).length;
    const matched = documents.filter(d => isPhone(d.phone || contacts[d.plate])).length;
    const flagged = documents.filter(d => !d.within_limit || !d.plate || d.review_required).length;
    el('#insurance-summary').textContent =
      '총 ' + documents.length + '페이지  ·  JPG 준비 완료 ' + ready +
      '건  ·  연락처 매칭 ' + matched + '건  ·  확인 필요 ' + flagged + '건' +
      (conflictPlates.length ? '  ·  연락처 중복 충돌 ' + conflictPlates.length + '건' : '');
  };
  const refresh = () => {
    const rows = el('#insurance-rows');
    rows.innerHTML = '';
    documents.forEach((doc, index) => {
      const tr = document.createElement('tr');
      const phone = doc.phone || contacts[doc.plate] || '';
      const state = !doc.within_limit ? '용량 초과 · 발송 보류' :
        (!doc.plate || doc.review_required) ? '차량번호 확인 필요' :
        !isPhone(phone) ? '연락처 미지정' : '이미지·연락처 확인';
      tr.innerHTML =
        '<td><strong>' + esc(doc.source) + '</strong><br><small>' + doc.page + '페이지</small></td>' +
        '<td><input class="insurance-plate" data-insurance-plate="' + index + '" aria-label="차량번호 수정" value="' + esc(doc.plate) + '">' +
        '<small>' + esc(doc.reason || 'PDF 차량번호 항목에서 추출') + '</small>' +
        (doc.review_required ? '<button type="button" data-insurance="confirm" data-index="' + index + '">원본 확인 완료</button>' : '') + '</td>' +
        '<td><input data-insurance-phone="' + index + '" aria-label="연락처 수정" value="' + esc(phone) + '" placeholder="01012345678"></td>' +
        '<td><strong>' + Math.ceil(doc.size_bytes / 1024) + 'KB</strong><br><small>' + esc(state) + '</small>' +
        (!doc.within_limit ? '<small class="insurance-warning">' + esc(doc.warning) + '</small>' : '') + '</td>' +
        '<td><button type="button" data-insurance="preview" data-index="' + index + '">미리보기</button> ' +
        '<button type="button" data-insurance="download" data-index="' + index + '">JPG 저장</button></td>';
      rows.appendChild(tr);
    });
    if (!documents.length) rows.innerHTML = '<tr><td colspan="5"><div class="empty">PDF를 선택하면 여기에 페이지별 결과가 표시됩니다.</div></td></tr>';
    summary();
  };
  const fileName = (doc, index) => (doc.plate || ('확인필요_' + (index + 1))) + '_' +
    String(index + 1).padStart(3, '0') + '.jpg';

  container.addEventListener('change', async event => {
    const target = event.target;
    const kind = target.dataset.insurance;
    if (kind === 'pdf') {
      const files = Array.from(target.files || []);
      target.value = '';
      for (let i = 0; i < files.length; i++) {
        const file = files[i];
        el('#insurance-progress').textContent = (i + 1) + '/' + files.length + ' · ' + file.name + ' 처리 중';
        if (!file.name.toLowerCase().endsWith('.pdf')) {
          toast('PDF만 선택해 주세요: ' + file.name);
          continue;
        }
        try {
          const form = new FormData();
          form.append('file', file);
          const result = await api('/insurance/convert', {method: 'POST', body: form});
          for (const page of result.pages) {
            documents.push({...page, source: file.name, phone: '', manualPhone: false, review_required: true,
              reason: page.reason || '자동 추출한 차량번호입니다. 원본을 대조하고 확인 완료를 눌러 주세요.'});
          }
          refresh();
        } catch (error) {
          toast(file.name + ': ' + error.message);
          el('#insurance-progress').textContent = error.message;
        }
      }
      el('#insurance-progress').textContent = 'PDF 변환 작업 종료 · 원본과 결과를 확인해 주세요.';
    } else if (kind === 'contacts') {
      const file = target.files?.[0];
      target.value = '';
      if (!file) return;
      const form = new FormData();
      form.append('file', file);
      try {
        const result = await api('/insurance/contacts', {method: 'POST', body: form});
        contacts = result.contacts;
        conflictPlates = result.conflicts;
        for (const doc of documents) if (!doc.manualPhone) doc.phone = contacts[doc.plate] || '';
        refresh();
        toast('연락처 ' + result.count + '건을 불러왔습니다. 충돌 ' + result.conflicts.length + '건은 자동 매칭하지 않습니다.');
      } catch (error) {
        toast(error.message);
      }
    } else if (target.dataset.insurancePlate !== undefined) {
      const doc = documents[Number(target.dataset.insurancePlate)];
      doc.plate = cleanPlate(target.value);
      if (!doc.manualPhone) doc.phone = contacts[doc.plate] || '';
      doc.review_required = true; // 수동 변경 후 원본 재확인 필수
      doc.reason = '직접 수정한 차량번호입니다. 보험증권 원본과 확인하세요.';
      refresh();
    } else if (target.dataset.insurancePhone !== undefined) {
      const doc = documents[Number(target.dataset.insurancePhone)];
      doc.phone = cleanPhone(target.value);
      doc.manualPhone = !!doc.phone;
      refresh();
    }
  });
  container.addEventListener('click', async event => {
    const b = event.target.closest('[data-insurance]');
    if (!b || b.disabled) return;
    const action = b.dataset.insurance;
    const index = Number(b.dataset.index);
    const doc = documents[index];
    if (action === 'confirm') {
      if (!doc?.plate) return toast('차량번호를 입력해 주세요.');
      doc.review_required = false;
      doc.reason = '사용자가 원본 확인을 완료했습니다.';
      refresh();
    } else if (action === 'download') {
      if (!doc) return;
      download(new Blob([jpegBytes(doc)], {type: 'image/jpeg'}), fileName(doc, index));
    } else if (action === 'preview') {
      if (!doc) return;
      const viewer = document.createElement('dialog');
      viewer.className = 'insurance-preview';
      viewer.innerHTML = '<div class="insurance-preview-head"><strong>' + esc(doc.source) + ' · ' +
        doc.page + '페이지</strong><button type="button">닫기</button></div>' +
        '<p>원본 PDF와 작은 글씨·색상·가림 영역을 비교해 주세요. 화면 미리보기는 전송 품질을 보증하지 않습니다.</p>' +
        '<img alt="변환된 보험증권 미리보기" src="data:image/jpeg;base64,' + doc.jpeg_base64 + '">';
      document.body.appendChild(viewer);
      viewer.querySelector('button').onclick = () => viewer.close();
      viewer.addEventListener('close', () => viewer.remove());
      viewer.showModal();
    } else if (action === 'zip') {
      const eligible = documents.map((d, index) => ({doc: d, index}))
        .filter(({doc}) => doc.within_limit && doc.plate && !doc.review_required);
      if (!eligible.length) return toast('검증 완료된 199KB 이하 JPG가 없습니다.');
      const items = eligible.map(({doc, index}) => ({name: fileName(doc, index), bytes: jpegBytes(doc)}));
      download(zipFile(items), '보험증권_변환결과.zip');
      toast(items.length + '개 JPG를 ZIP으로 저장했습니다. 확인 필요 항목은 제외했습니다.');
    } else if (action === 'clear') {
      if (!window.confirm('보험증권과 연락처 임시 목록을 초기화하시겠습니까?')) return;
      clearInsuranceTool();
      refresh();
      el('#insurance-progress').textContent = '목록을 초기화했습니다.';
      el('#insurance-error-result').textContent = '';
    } else if (action === 'diagnose') {
      const code = el('#insurance-error-code').value;
      const detail = el('#insurance-error-detail').value;
      if (!code.trim() && !detail.trim()) return toast('오류 코드 또는 오류 문구를 입력해 주세요.');
      try {
        const result = await api('/insurance/mms/explain', {
          method: 'POST', body: JSON.stringify({code, detail})
        });
        const output = el('#insurance-error-result');
        output.innerHTML = '';
        const panel = document.createElement('div');
        panel.className = 'notice warn';
        const title = document.createElement('strong');
        title.textContent = result.title;
        const help = document.createElement('p');
        help.textContent = result.action;
        const details = document.createElement('details');
        const summary = document.createElement('summary');
        summary.textContent = '개발자용 오류 코드 보기';
        const pre = document.createElement('pre');
        pre.textContent = '코드: ' + result.technical.code + '\n원문: ' + result.technical.detail;
        details.append(summary, pre);
        panel.append(title, help, details);
        output.appendChild(panel);
      } catch (error) {
        toast(error.message);
      }
    }
  });
  refresh();
}
