# LibreSMS 선택 발송 — 2026-11-06

## 범위
CoolSMS를 기본값으로 유지하며 LibreSMS를 시험 옵션으로 추가한다. 운영 기준 커밋 fafc242에서 codex/libresms-option-20261106 브랜치로 개발했다. 운영 배포와 push는 하지 않았다.

업무폰 phone1/phone2 각각 이름, 사설 IPv4 주소:포트, 실제 SIM 발신번호, 사용 여부, 발송 간격을 암호화 저장한다. 사용자가 발송 기기를 선택한다. 대기 요청에는 선택한 기기의 설정을 보존한다. 다른 폰으로 자동 대체하거나 CoolSMS로 자동 전환하지 않는다. 발신번호는 설정값이며 API가 SIM 번호를 검증한 결과가 아니다.

## 동작과 안전
- 기존 고객정보 접근 권한을 부여받은 관리자만 설정/발송/대기열 조회 및 취소 가능.
- JPEG와 수신정보를 암호화 대기열에 저장하고 완료/취소 시 대기열 이미지 제거.
- 요청 ID 및 수신자·문구·문서 기반 중복 방지. 두 폰과 CoolSMS 간에도 동일 요청 중복 방지.
- 단일 서버 작업자가 순차 발송한다. 기기별 간격을 유지하되 두 폰에 동시 병렬 전송하지 않는다.
- 폰 1 오프라인은 폰 2의 대기 건 처리를 막지 않는다. HTTP 요청 중에는 최대 응답 시간 동안 순차 대기가 발생할 수 있다.
- 연결 확인 실패는 발송 전이므로 대기 유지. 실제 MMS 요청 후 오류/타임아웃은 결과 미확인으로 보존하고 자동 재발송하지 않는다.
- 서버 재시작 시 처리 중 요청은 미확인 처리. 백업 복구 시 이전 대기/처리 요청도 미확인 처리하고 발송 설정을 보류하여 이미 전송된 요청의 재발송 방지.
- HTTPS/HTTP 사설 IPv4와 지정 포트만 허용, URL 인증정보/리디렉션/환경 프록시 사용 금지.
- 새 insurance_dispatches 테이블 추가. 기존 차량·출고 Snapshot·Closing·사진에는 변경 없음.

## 실기기 설정과 한계
각 업무폰에 LibreSMS 앱을 준비하고 서버에서 접근 가능한 전용망 주소 및 SIM 번호를 각각 등록한다. 연결 확인은 /health만 호출하며 문자 발송하지 않는다. 두 기기의 실제 수신 시험 후에 업무 발송 여부를 판단해야 한다.

공식 HTTP 서버 소스에는 인증 검사가 없고 모든 인터페이스에 바인딩한다. 인터넷 포트 공개를 하지 않으며 LAN에도 서버만 접근하도록 네트워크를 제한해야 한다. Tailscale 주소 사용만으로 LAN 포트가 보호되는 것은 아니다.

공식 MMS 구현은 APN 조회 실패 시 AT&T 설정으로 대체한다. 국내 통신사/APN/갤럭시에서의 발송 성공은 미검증이다. success 응답은 수신자 도착 확인이 아니다. LibreSMS APK를 이 프로젝트에서 빌드하거나 배포하지 않았다.

공식 근거:
- https://github.com/fictus/LibreSMS
- https://raw.githubusercontent.com/fictus/LibreSMS/main/LibreSMS/Services/HttpGatewayServer.cs
- https://raw.githubusercontent.com/fictus/LibreSMS/main/LibreSMS/Services/SmsSenderService.cs

## 실행한 검증
- pytest tests/test_libresms.py tests/test_insurance_integration.py tests/test_photo_storage.py -q: 31 passed. 기존 Starlette/httpx 사용 중단 예정 경고 1건.
- tests/libresms_browser.py: 실제 격리 서버 + Chrome에서 두 기기 선택, 개별 설정, 연결 확인 UI, CoolSMS 기본값, 390px viewport 확인. LibreSMS API는 합성 응답으로 대체.
- tests/insurance_browser.py: 실제 PDF/연락처 처리, 199000바이트 이하 JPEG ZIP, 120페이지 처리, 초기화 후 재입력, 선택 발송 모의 응답, PC/모바일 viewport 회귀 통과.
- Node 구문 검사 및 git diff --check 통과.
- 실제 전화번호로 발송하지 않았으며 운영 데이터와 실사용 환경 설정은 변경하지 않음.

## 운영 업데이트/복구 절차
1. 배포 전 운영 Git 상태와 DB·사진·암호화 키 복구 수단을 확인하고 정상 백업을 별도로 보존한다.
2. 승인 후 단일 운영 서버를 정지하고 검증 커밋을 이력 보존 방식으로 적용한다. 환경/DB/사진/키를 개발 파일로 교체하지 않는다.
3. 시작 시 새 테이블만 추가된다. 기본값은 두 폰 모두 꺼짐. 기존 CoolSMS와 차량 업무를 점검한다.
4. 코드 롤백은 기준 커밋으로 되돌리는 별도 Git 이력 또는 기록된 배포 절차를 사용한다. 업무 DB를 과거 백업으로 무조건 덮어쓰지 않는다. 미처리 MMS가 있으면 먼저 발송을 중지하고 결과를 대조한다.
5. 백업 복구본의 미확인 MMS는 실제 폰/수신자 기록 대조 전 재전송하지 않는다.
