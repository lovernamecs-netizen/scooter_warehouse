# 보험증권 고지문 · CoolSMS 통합 관리자

**목적:** 기존 Tkinter 프로그램의 PDF→JPG 변환, JPG 폴더/다중 JPG 불러오기, CSV/XLS/XLSX 연락처 매칭, 수동 전화번호 수정, 메시지 문구 저장, CoolSMS 계정 설정, 개별/전체 MMS 전송을 바이크 재고관리의 **관리·도구** 메뉴에 통합합니다.

## 기존 프로그램과 비교

| 원본 기능 | 이번 브랜치 |
|---|---|
| PDF 파일 다중 선택, 페이지별 JPG 변환 | 지원, 원본 PDF 자체 수정 없음 |
| 고정 좌표 흰색 가림(330,400,585,435) | 동일 좌표, 위치가 페이지 밖이면 보류 |
| PDF 차량번호 추출 | 한국 이륜차 지역식/신형식 확장, 수동 확인 |
| JPG 파일/폴더 선택 | Chrome 폴더 선택 및 파일 다중 선택 |
| 거래처 CSV/XLS/XLSX 매칭 | 지원, 동일 차량번호의 서로 다른 전화번호 충돌은 자동 매칭 제외 |
| 연락처 수동 수정 | 지원, UI에서 수정 |
| MMS 기본 고지문 | 기존 원문 그대로 기본값 적용 |
| 메시지 문구 편집 및 저장 | 지원, 서버 설정에 저장 |
| CoolSMS API Key/Secret, 등록 발신번호 설정 | 지원, Key/Secret은 OS 보안 저장소(keyring), 발신번호/문구는 별도 로컬 JSON |
| 개별 MMS 발송 | 지원, 사용자 최종 확인 후 유료 MMS 전송 |
| 여러 항목 선택 후 MMS 발송 | 지원, 목록의 체크박스로 다중 선택 후 발송 |
| 전체 목록 MMS 발송 | 지원, 1회 확인 후 순차 발송. 이미 접수·미확인 상태인 건은 재발송하지 않음 |
| MMS 성공/실패 상태 표시 | API 접수 상태와 실제 고객 수신 완료 구분 |
| 실패 원인 표시 | 자연어 설명 + 펼치면 오류 코드/원문 |

## 처리 단계
1. 관리·도구 → PDF 선택 또는 변환된 JPG 폴더/파일 불러오기.
2. PDF에 정해진 흰색 영역만 비식별 처리하여 RGB 컬러 JPG로 변환. 페이지 여백과 전체 비율, 문구 배치 그대로 유지. 암호화 PDF/다른 페이지 규격 보류.
3. 최종 전송 규격 199,000바이트 이하 및 최대 1500×1440픽셀을 모두 만족하도록 전체 페이지를 같은 비율로만 축소. 크기 초과 시 원본을 임의로 재구성하거나 컬러를 회색조로 바꾸지 않고 발송 금지. JPEG는 손실 압축이므로 완전히 동일한 픽셀 및 글자 선명도는 보장할 수 없음.
4. 차량번호 인식 결과와 변환한 JPG를 원본과 비교한 후 '원본 확인 완료'. 정확한 인식이 어려운 문서는 사용자가 수정. OCR 없음.
5. CSV/XLS/XLSX 연락처 입력 후 차량번호로 번호 매칭, 누락 시 수동 입력.
6. CoolSMS 계정 설정(등록 발신번호 + Key/Secret), 문구 편집 및 저장. 기본 문구의 {차량번호}는 차량번호로 치환.
7. 사용자 확인 후 개별 MMS 발송 또는 전체 목록 일괄 MMS 발송. 전송/접수 건당 CoolSMS 과금 발생 가능.
8. API 접수 완료/실패/접수 여부 확인 필요 상태를 구분. 통신사 최종 수신 완료는 별도 확인. 실패 사유는 사용자 언어로 표시하고, 세부 코드와 원문은 펼쳐서 확인.

## 기술 및 운영 조건
- 서버: FastAPI. 모듈: server/insurance_documents.py, insurance_settings.py, insurance_coolsms.py, insurance_mms.py.
- UI: web/insurance-tool.js, insurance-sender.js, insurance-tool.css. 기존 웹페이지/스타일의 카드와 표 구성 사용.
- 영구 저장: 발신번호/문구는 APPDATA/ScooterWarehouse/insurance-mms.json (또는 INSURANCE_CONFIG_DIR). 이 파일에 API Key/Secret은 저장하지 않음. 키는 Windows 자격 증명 저장소 등 OS 보안 저장소로 관리. 서버 실행 계정에 접근 권한 필요.
- 업무용 PDF/JPG/엑셀은 서버 영구 저장하지 않음. PDF 변환은 메모리 처리. MMS 발송 시 공급자 SDK와 호환되도록 임시 디렉터리에 JPG를 생성하고 SDK 처리 후 삭제. MMS 발송 자체는 제3자 SOLAPI/CoolSMS로 이미지/문구/수신번호를 전송함.
- 개인정보가 포함된 보험증권·연락처·API 자격증명을 Git에 커밋하지 않음. 원본 독립 Tkinter 프로그램의 config.json은 자동 이관하지 않으며 API 자격증명은 관리자 화면에 다시 입력해야 함.
- MMS 이미지 첨부 제한 및 원본 서식에서 가림 좌표가 유효한지 실제 보험사 샘플로 검수한 뒤 운영 적용.
- 사용자의 브라우저가 Chrome일 때 폴더 선택 webkitdirectory 사용 가능.
- 레거시 Python CoolSMS sdk.api.message 인터페이스가 설치되어 있을 경우 기존 API 호출 형식으로 전송. 설치되어 있지 않으면 공식 SOLAPI Python SDK를 사용. 2026년에는 레거시 SDK 유지보수가 종료되어 신규 환경에서는 공식 SDK 권장.
- 전송 요청을 받은 뒤 네트워크가 끊기면 실제 접수 여부가 불명확할 수 있음. 그런 건은 자동 재시도를 차단하고 CoolSMS 콘솔에서 확인하도록 안내. 동일 요청 ID의 프로세스 내 24시간 중복 요청 방지는 구현되지만 서버 재시작 시 지속되지 않음.
- 창고 재고·입출고 DB, 차량사진 저장소, Android 앱/키/서명은 수정하지 않음.

## 검증
- 신규 서버 유닛 테스트: tests/test_insurance_tools.py, tests/test_insurance_coolsms.py (가짜 고객번호·합성 문서·모의 SDK 전송만 사용).
- JavaScript syntax 검사: web/app.js, web/insurance-tool.js, web/insurance-sender.js.
- GitHub Actions CI의 보험증권 전용 잡과 기존 창고 전체 잡 결과는 각각 확인.
- 실제 MMS 발송은 CI에서 절대 실행하지 않음. 실제 보험증권을 이용한 품질·가림·수신 테스트와 Windows 배포, 브라우저 UX, 고객 대상 과금 테스트는 별도로 필요한 수동 검증.
- 기존 독립 프로그램, main 브랜치, 운영 DB는 유지. Draft PR 병합 전 운영 환경을 백업하고 확인할 것.

## 브라우저 미리보기 (실제 MMS 발송 없음)

새 브랜치의 실제 UI 모듈을 가상 문서 3건과 가상 CoolSMS 응답으로 실행하는 별도 HTML 페이지가 있습니다.

- 파일: web/insurance-preview.html, web/insurance-preview.js
- 기능: 차량번호/연락처 수정, 가상 JPEG 미리보기, 샘플 선택·전체 발송, 모의 접수/실패/응답 불확실 상태 표시, 메시지 문구·계정 설정 화면 확인
- 실제 PDF·연락처 업로드는 미리보기에서 비활성화. 가상 API가 브라우저 메모리 안에서만 동작하며 실제 서버·통신사에 접속하지 않습니다.
- 관리·도구 화면의 '샘플 UI 미리보기 새 창' 버튼으로 별도 창 열기 가능.
- 운영 시스템·운영 데이터·고객 자료·기존 프로그램 main에 영향을 주지 않음.

백엔드 서버나 데이터베이스 없이 브라우저 UI만 보고 싶다면, 새 브랜치를 개발용 폴더에 체크아웃한 후 Windows PowerShell에서 다음 명령을 실행합니다.

~~~powershell
py -3.12 -m http.server 8899 --bind 127.0.0.1 --directory web
~~~

그다음 Chrome에서 http://127.0.0.1:8899/insurance-preview.html 을 엽니다. 화면 상단의 '미리보기 새 창 열기'를 누르면 별도의 Chrome 창이 열립니다. 실행 중인 서버가 필요하므로 GitHub 파일 화면에서 코드를 보는 것만으로는 인터랙션이 실행되지 않습니다.

**한계:** 이것은 UI 검증 화면입니다. PDF 변환·원본 서식·실제 MMS 서비스·브라우저 파일 업로드·실제 수신 상태의 종단간 검증을 대신하지 않습니다.

## 실행
개발용 작업 폴더에서 Python 3.12로 의존성을 설치합니다.

- python -m pip install -r requirements-dev.txt
- python -m pytest -q tests/test_insurance_tools.py tests/test_insurance_coolsms.py

서버를 Windows 사용자 계정으로 실행하고 관리자 계정에서 CoolSMS 발신번호 및 API Key/Secret을 설정한 뒤 합성 문서로 동작 확인합니다. 실제 고객에게 발송하는 시험은 반드시 발송 대상과 요금에 대한 사용자 승인 후 별도로 시행하세요.
