# 안정화 및 실제 서버/브라우저 검증 — 2026-10-18

## 기준과 보호 범위

- 작업 폴더: `C:\Users\CCS\ScooterWarehouse-development\stability-smoke-20261018`.
- 기준 폴더: `C:\Users\CCS\ScooterWarehouse-development\closing-inventory-20261016`.
- 시작/종료 HEAD 모두 `1b5df64e3c6cc5c7def05db42ea01cc6d369d09c`, 브랜치 `closing-inventory`. 이 커밋은 문서 커밋이므로 기준 폴더의 미커밋/미추적 소스 30개도 보존하여 옮겼다. 커밋만으로 현재 구현 전체를 재현할 수 없다.
- 원격 main 조회 결과 `0087e51151d61a6b1d2962f8db028bea85d6519c`. 이번 작업에서 commit/push/tag/배포하지 않았다. 작업 복제본 origin은 로컬 기준 폴더다.
- 운영 폴더에서 수정/서버 실행/DB 열기/사진 접근을 하지 않았다. 운영 8765 및 기존 미리보기 18768을 재시작하거나 변경하지 않았다.
- 테스트는 새 임시 SQLite DB와 합성 사진, 무작위 loopback 포트만 사용했다. DATABASE_URL/TEST_DATABASE_URL 기존 설정 유무만 확인했고 비밀 값을 출력하지 않았다. 테스트 자식 프로세스만 종료했다.

## 확인된 문제와 수정

1. 초기화가 기본 옵션을 만든 뒤 demo가 모든 마스터 존재를 이유로 실행을 거절했다. 차량/차종 등 실제 데모 충돌 기준으로 제한하고 새 DB의 init→demo를 실행 검증했다.
2. 서버 오류가 예외 원문/객체나 HTML 응답으로 화면에 전달될 수 있었다. 한국어 오류 계약, 요청 ID, 안전한 필드 오류, 제한된 회전 로그를 추가했다. 로그는 예외 종류와 파일명/행/함수만 남기며 SQL·본문·인증정보·예외 원문은 남기지 않는다.
3. 저장 후 목록 조회 실패가 숨겨지거나 응답 유실 후 새 요청으로 다시 저장될 수 있었다. 저장 및 최신 상태 확인까지 요청 번호를 보존하고 같은 입력은 같은 번호로 재시도한다. 다른 입력의 새 저장은 미확인 요청 해결 전 차단한다.
4. 오류 알림이 사라지거나 입력 화면을 방해했다. 별도 확인 대화상자, ESC/뒤로가기/포커스 복귀와 초안 보존, 작은 화면 스크롤을 구현했다.
5. 서버 준비 전에 브라우저를 열거나 다른 프로세스의 포트를 정상 기동으로 오인할 여지가 있었다. Windows 실행 보조 프로그램에서 포트를 먼저 확보하고 실행 인스턴스 ID를 확인한다. 의존성 부재 시 시작 스크립트가 자동 설치를 시도하지 않고 안내한다.
6. health 버전 불일치와 favicon 404를 수정했다. 기존 브라우저 테스트를 임시 DB/무작위 포트/실행 인스턴스 확인 방식으로 변경했다.

테스트 보조 코드 자체의 Windows venv 부모/자식 PID 오인, 로그 캡처 문제, 오래된 UI 기대값도 실행 중 확인하여 수정했다. 아래 결과는 수정 후 재실행 결과다.

## 실행 결과

환경: Windows 11 Home 10.0.26200, Python 3.12.10, Chrome 155.0.8059.80.

| 구분 | 실제 결과 |
|---|---|
| 수정 전 서버 회귀 | 135 passed, 1 warning, 131.08초 |
| 수정 후 전체 서버 회귀 | 140 passed, 1 warning, 131.36초 |
| 이후 추가한 사진 저장 실패 검사 | 별도 1 passed — 전체 141개를 한 번에 실행한 결과가 아님 |
| stability_browser.py | 실제 로그인/입고/VIN 수정·중복/권한/세션 만료/서버 재시작 및 저장 응답 유실 검사 통과, pageerror 0 |
| closing_browser.py | B2B/B2C 계획·부품·재고실사·실제 작업완료→출고대기→출고 UI 및 동일 출고 요청 재전송 검사 통과 |
| photo_ui_browser.py | 6방향·13부위·4000×3000 원본 표시·다운로드 해시·부분 재시도·초안/뒤로가기·터치 확대 검사 통과 |
| map_stability_browser.py | 창고 간 이동, 점유 자리 거절, 차량이 있는 구역 축소 실패 시 위치/입력/줌 보존 통과 |
| fold_smoke.py | 폭 360/412/768/884/1024와 높이 400의 브라우저 화면/초안 보존 통과 |
| test_startup.py | 실제 Windows Python 기동·임시 포트 점유 충돌·첫 서버 보존 통과(전체 서버 검사에 포함) |
| 정적 검사 | app.js/errors.js 문법, Node 로그인 오류 검사, git diff --check 통과 |

경고 1개는 기존 Starlette/httpx deprecation 경고다. 의도적으로 유발한 HTTP 오류/네트워크 차단은 console/network 결과에 남는다. 이를 미처리 JavaScript 오류와 구분했다.

### 실제 실행과 주입 검사의 구분

- 실제 Uvicorn + Chrome: 정상/오류 로그인, 입고·VIN, 출고, 지도, 사진, 재시작 후 데이터 보존.
- 브라우저 응답 주입: 422 배열/객체, 500/403/429, HTML 502, 빈 503의 표시와 입력 보존.
- 실제 저장 후 응답 차단, 저장 후 state 조회 차단, 서버 도달 전 요청 차단을 각각 실행했다. 같은 요청 재전송의 중복 방지를 확인했다.
- 서버 TestClient 고장 주입: 트랜잭션 중 RuntimeError 롤백, ENOSPC/EACCES 사진 저장 실패 시 메타데이터 미기록, 백업 오류, 검증 입력 비노출. 실제 디스크를 채우거나 운영 권한을 변경하지 않았다.

## 미검증 및 적용 한계

- 실제 Galaxy/Fold, 삼성/Android 카메라 앱, APK 빌드·서명·업데이트 설치·백그라운드 사진 큐·실제 키보드/제스처는 이번 작업에서 미검증이다. 브리지와 터치는 브라우저 모사다.
- PostgreSQL, 원격 GitHub Actions, 실제 CMD 더블클릭·기본 8765 기동·C# 실행기·Windows 오류 MessageBox는 미검증이다. Python 시작 보조 프로그램은 no-browser/no-dialog로 검사했다.
- 과거 사용자가 보았던 빨간 Python 오류의 정확한 사건은 원본 로그가 없어 동일 원인으로 재현했다고 말할 수 없다.
- 모든 지도 분할/병합/드래그 경로를 새 브라우저 검사로 확인한 것은 아니다. 전체 서버 회귀와 명시된 브라우저 경로를 구분한다.
- 삭제 요청된 출고 코드 붙여넣기 UI를 다시 추가하지 않았다. 기존 호환 API 검사와 현재 화면 검사는 별개다.
- 운영 설정/실데이터 정합성을 조사하지 않았다. 미래 기능 및 OCR을 추가하지 않았다.

## 재실행

아래 명령은 반드시 격리 작업 폴더에서 실행한다. 브라우저 스크립트는 자체 임시 DB/합성 사진을 생성하고 종료 후 정리한다. Chrome과 기존 Python 환경의 Playwright 등 테스트 의존성이 필요하다.

```powershell
Set-Location 'C:\Users\CCS\ScooterWarehouse-development\stability-smoke-20261018'
$testPython = 'C:\Users\CCS\ScooterWarehouse-development\initial-registration-20261015\.venv\Scripts\python.exe'
$env:PYTHONUTF8 = '1'
Remove-Item Env:TEST_DATABASE_URL -ErrorAction SilentlyContinue
& $testPython -X utf8 -B -m pytest -q tests
& $testPython -X utf8 -B tests/stability_browser.py
& $testPython -X utf8 -B tests/closing_browser.py
& $testPython -X utf8 -B tests/photo_ui_browser.py
& $testPython -X utf8 -B tests/map_stability_browser.py
& $testPython -X utf8 -B tests/fold_smoke.py
```

결과 위치: `C:\Users\CCS\ScooterWarehouse-development\stability-results`. 전체 서버 로그/XML, stability-browser.json, 브라우저 네트워크 JSON, 합성 데이터 화면 캡처가 있다. error-mobile.png는 viewport 검사 중 저장한 브라우저 캡처이며 실기기 사진이 아니다.

## 변경 묶음과 백업/복구 절차

`stability-review-20261018.zip`은 기준 작업 폴더 대비 이번 변경분과 SHA256 manifest만 담은 **검토용** 묶음이다. 기존 미커밋 기능 전체나 설치 프로그램이 아니다. DB/사진/.env/키/EXE/APK는 포함하지 않는다. 기존 1.0.30용 패치 설치기에 바로 넣지 않는다.

1. 별도 배포 승인 후 적용 대상의 기준 버전과 manifest의 before 해시를 비교한다. 차이가 있으면 덮어쓰기를 중단하고 차이를 검토한다. 특히 운영 폴더는 기준 개발 폴더와 같다고 가정하지 않는다.
2. 승인된 점검 시간에 서버를 정상 종료하고 변경 대상 소스와 현재 버전을 별도 백업한다. DB는 기존 일관성 있는 SQLite 백업 절차로 보존하고 WAL/SHM·사진·큐·설정은 임의 삭제하거나 ZIP 내용으로 대체하지 않는다.
3. 비교 완료한 runtime 파일(server/web/windows)만 적용한다. tests/docs/CI는 검토 및 재현용이다. 이번 변경에는 DB 스키마 변경이 없다.
4. 문제 발생 시 서버를 중지하고 백업한 소스 버전을 복구한다. 새 파일은 이번 적용에서 생성한 것이 확실하고 이후 변경이 없을 때만 목록 대조 후 제거한다. 운영 DB/사진을 테스트 데이터나 과거 백업으로 되돌리지 않는다.
5. 서버 시작/로그인/읽기 상태를 확인한 뒤 사용을 재개한다. 이 절차는 준비만 했으며 실제 적용/복구는 실행하지 않았다.
