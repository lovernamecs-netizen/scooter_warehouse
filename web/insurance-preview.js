/* 보험증권 UI 실제 모듈을 데이터·전송 모의로 검증하는 격리된 브라우저 데모.
 * fetch/API 인증 호출, 서버, DB, 전화회선, 외부 SMS 공급자를 전혀 사용하지 않습니다.
 */
import {renderInsuranceTool, clearInsuranceTool} from './insurance-tool.js';

const $ = selector => document.querySelector(selector);
const esc = input => String(input ?? '').replace(/[&<>"']/g, char =>
  ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[char]));
const DEFAULT_TEMPLATE = '[안내] {차량번호} 관련 고지문입니다.\n\n' +
  '※ 유상종합 요청 관련 필수 고지사항\n' +
  '- 신중하게 선택 부탁드립니다.\n' +
  '- 보험해지는 불가합니다.\n' +
  '- 고객 사유로 중도해지 시 남은 구독료의 20% 위약금이 발생합니다. (전계약)';
let settings;
let simulatedCount = 0;

function toast(message) {
  const notice = $('#preview-state');
  notice.textContent = '데모 안내: ' + String(message);
  const toastNode = $('#toast');
  if (toastNode) {
    toastNode.textContent = message;
    toastNode.style.display = 'block';
    clearTimeout(toast.id);
    toast.id = setTimeout(() => { toastNode.style.display = 'none'; }, 4300);
  }
}

// 가상 고지문. 보험증권 실제 양식이 아니며 개인·회사정보도 포함하지 않습니다.
function generateSyntheticJpeg(plate, accent) {
  const canvas = document.createElement('canvas');
  canvas.width = 680;
  canvas.height = 940;
  const ctx = canvas.getContext('2d');
  ctx.fillStyle = '#fff';
  ctx.fillRect(0, 0, canvas.width, canvas.height);
  ctx.fillStyle = accent;
  ctx.fillRect(58, 68, 565, 13);
  ctx.fillStyle = '#192d35';
  ctx.font = 'bold 27px Malgun Gothic, sans-serif';
  ctx.fillText('보험 고지문 · 가상 샘플', 58, 135);
  ctx.font = '15px Malgun Gothic, sans-serif';
  ctx.fillStyle = '#647780';
  ctx.fillText('실제 문서를 재현하지 않은 UI 확인용 가상 문서입니다.', 58, 169);
  ctx.strokeStyle = '#dbe3e7';
  ctx.beginPath(); ctx.moveTo(58, 192); ctx.lineTo(623, 192); ctx.stroke();
  ctx.fillStyle = '#2d4148';
  ctx.font = 'bold 17px Malgun Gothic, sans-serif';
  ctx.fillText('차량번호 : ' + plate, 58, 243);
  ctx.font = '15px Malgun Gothic, sans-serif';
  const lines = [
    '본 화면은 개발 브랜치 UI의 동작을 확인하기 위한 테스트입니다.',
    '실제 보험증권을 처리하거나 수신자에게 발송하지 않습니다.',
    '원본 색상·여백 유지, 흰색 가림, JPG 압축은',
    '별도의 실제 PDF 변환 테스트에서 검증해야 합니다.',
    '─────────────────────────────────────',
    '개별 발송 · 다중 선택 발송 · 일괄 발송을 테스트하세요.',
    '에러 코드 펼치기 및 연락처 수정 기능도 확인할 수 있습니다.'
  ];
  lines.forEach((line, i) => ctx.fillText(line, 58, 303 + i * 33));
  ctx.fillStyle = '#f2f5f6';
  ctx.fillRect(58, 570, 565, 110);
  ctx.fillStyle = '#39505b';
  ctx.font = '13px Malgun Gothic, sans-serif';
  ctx.fillText('가상 테스트 전용 — 여기는 지정된 흰색 가림 영역이 아닙니다.', 75, 601);
  ctx.fillText('원본 보험증권의 실제 가림 위치와 무관합니다.', 75, 626);
  ctx.fillStyle = '#657a83';
  ctx.font = '12px Malgun Gothic, sans-serif';
  ctx.fillText('SCOOTER WAREHOUSE · INSURANCE TOOL UI PREVIEW', 58, 872);
  ctx.fillText('합성 데이터 / 실제 보험증권 아님 / 발송되지 않음', 58, 898);
  const base64 = canvas.toDataURL('image/jpeg', .88).split(',')[1];
  const size = atob(base64).length;
  return {jpeg_base64: base64, size_bytes: size, width: canvas.width, height: canvas.height};
}

function createSamples() {
  const images = [
    generateSyntheticJpeg('123가4567', '#007d79'),
    generateSyntheticJpeg('234나5678', '#6d91b2'),
    generateSyntheticJpeg('345다6789', '#b78350'),
  ];
  const base = {
    source: '보험증권_가상샘플.pdf',
    page: 1,
    manualPhone: false,
    candidates: [],
    warning: '',
    within_limit: true,
    send_status: undefined,
    send_error: null,
  };
  return {
    documents: [
      {
        ...base, ...images[0], source: '보험증권_가상샘플_A.pdf',
        plate: '123가4567', candidates: ['123가4567'],
        phone: '01000000000', review_required: false,
        reason: '샘플에서 차량번호 확인 완료',
      },
      {
        ...base, ...images[1], source: '보험증권_가상샘플_B.pdf',
        plate: '234나5678', candidates: ['234나5678'],
        phone: '01000000001', review_required: true,
        reason: '가상 데이터: 원본과 차량번호 확인이 필요합니다.',
      },
      {
        ...base, ...images[2], source: '보험증권_가상샘플_C.pdf',
        plate: '345다6789', candidates: ['345다6789'],
        phone: '01000000002', review_required: false,
        reason: '샘플에서 차량번호 확인 완료',
        send_status: 'failed',
        send_error: {
          title: '문자 발송 서비스의 잔액이 부족합니다.',
          action: '서비스 잔액을 확인한 후 충전하고 다시 시도하세요.',
          technical: {code: '1030', detail: '가상 API 오류: 잔액 부족'},
        }
      },
    ],
    contacts: {
      '123가4567': '01000000000',
      '234나5678': '01000000001',
      '345다6789': '01000000002',
    },
  };
}

function mockResult(kind) {
  if (kind === 'balance') {
    return {
      state: 'failed',
      title: '문자 발송 서비스의 잔액이 부족합니다.',
      action: '발송 서비스의 잔액을 확인하고 충전해 주세요.',
      technical: {code: '1030', detail: '가상 오류 · 잔액 부족'},
      delivery_confirmed: false,
    };
  }
  if (kind === 'uncertain') {
    return {
      state: 'unknown',
      title: '발송 접수 여부를 확인하지 못했습니다.',
      action: '중복 발송을 피하려면 CoolSMS 콘솔에서 접수 내역을 먼저 확인하세요.',
      technical: {code: 'TIMEOUT', detail: '가상 오류 · 네트워크 응답 시간 초과'},
      delivery_confirmed: false,
    };
  }
  return {
    state: 'accepted',
    title: '가상 MMS 발송 요청이 접수되었습니다.',
    action: '실제 문자는 발송되지 않았습니다.',
    group_id: 'MOCK-GROUP-' + String(++simulatedCount).padStart(3, '0'),
    delivery_confirmed: false,
    technical: {code: '', detail: '모의 서버가 접수한 가상 MMS'},
  };
}

async function mockApi(path, options = {}) {
  // 실제 네트워크 요청이 절대로 없는 mock controller.
  const method = options.method || 'GET';
  const payload = typeof options.body === 'string' ? JSON.parse(options.body) : {};
  if (path === '/insurance/mms/settings') {
    if (method === 'PUT') {
      settings = {
        ...settings,
        sender_phone: String(payload.sender_phone || settings.sender_phone),
        api_key_configured: true,
        api_secret_configured: true,
      };
    }
    return {...settings};
  }
  if (path === '/insurance/mms/template' && method === 'PUT') {
    settings.msg_template = String(payload.msg_template || '');
    return {...settings};
  }
  if (path === '/insurance/mms/send' && method === 'POST') {
    return mockResult($('#preview-response').value);
  }
  if (path === '/insurance/mms/explain') {
    const detail = String(payload.detail || '');
    const code = String(payload.code || '');
    return code === '1030' || detail.includes('잔액')
      ? mockResult('balance')
      : {state: 'failed', title: '문자 발송 오류가 발생했습니다.',
         action: '입력한 오류 코드를 실제 공급자 기록에서 확인하세요.',
         technical: {code: code || '미제공', detail: detail || '가상 오류'},
         delivery_confirmed: false};
  }
  if (path === '/insurance/convert' || path === '/insurance/contacts') {
    throw new Error('미리보기에서는 실제 보험증권·연락처 업로드가 비활성화되어 있습니다. 개발 서버에서 기능을 별도로 검증해야 합니다.');
  }
  throw new Error('지원하지 않는 미리보기 요청: ' + path);
}

function reset() {
  // 재렌더링 시 이벤트 핸들러가 중복 등록되지 않도록 새 DOM 컨테이너를 사용.
  clearInsuranceTool();
  simulatedCount = 0;
  settings = {
    sender_phone: '01000000000',
    msg_template: DEFAULT_TEMPLATE,
    api_key_configured: true,
    api_secret_configured: true,
  };
  const host = $('#preview-stage');
  host.replaceChildren();
  const root = document.createElement('div');
  host.append(root);
  renderInsuranceTool(root, {
    api: mockApi,
    toast,
    esc,
    role: 'admin',
    previewData: createSamples(),
  });
  // 미리보기는 실제 업로드를 전혀 하지 않는 것으로 분리.
  root.querySelectorAll('input[type=file]').forEach(input => {
    input.disabled = true;
    input.title = '샘플 미리보기에서 실제 파일을 선택할 수 없습니다.';
  });
  root.querySelectorAll('input[id="insurance-api-key"], input[id="insurance-api-secret"]').forEach(input => {
    input.disabled = true;
    input.title = '실제 API 자격 증명은 이 페이지에 입력하지 마세요.';
  });
  $('#preview-state').textContent = '준비 완료 · 가상 보험증권 3건 · 실제 발송 0건';
}

$('#preview-reset').addEventListener('click', reset);
$('#preview-popout').addEventListener('click', () => {
  window.open('/insurance-preview.html', 'insurancePreview',
    'popup=yes,width=1340,height=860,resizable=yes,scrollbars=yes');
});
reset();
