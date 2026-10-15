# Git 등록 검토 — 2026-10-15

## 결과
- 대상: C:\새 폴더\창고관리\scooter_warehouse (실사용 폴더)
- 원격: https://github.com/lovernamecs-netizen/scooter_warehouse
- GitHub connector 조회: Private, admin/push/pull 권한, size=0, default_branch=main, branch 목록 없음. 신규 저장소를 만들지 않았다. 전체 refs/태그 조회는 아직 하지 않아 태그 없음으로 단정하지 않는다.
- 로컬과 상위 경로에 Git 저장소 없음(git rev-parse 확인). 기존 인덱스/추적 이력도 없음. GitHub Desktop 내장 Git은 있으나 PATH에는 없음.
- 서버/웹/Android 1.0.30 표시. 과거 1.0.11 업데이트 잔여물과 1.0.7 APK 등 혼재. 공식 배포본과 전체 바이트 일치 미검증: v1.0.30 태그 보류.

## 등록 후보 115개
전체 상대경로: GIT_CANDIDATES.txt. 루트에 server/web/android/windows 등이 바로 위치한다.

| 구분 | 파일 수 |
|---|---:|
| server | 19 |
| web | 19 |
| android | 17 |
| windows | 4 |
| tests | 24 |
| verification | 2 |
| docs | 17 |
| deploy | 3 |
| .github | 1 |
| 루트 파일 | 9 |
| 합계 | 115 |

루트 9개: .env.example, .gitignore, AGENTS.md, README.md, TEST_REPORT_1.0.10.txt, TEST_REPORT_1.0.11.txt, compose.yaml, requirements-dev.txt, requirements.txt.
과거 테스트/릴리스 기록은 역사 자료로 유지하며 현재 검증 성공으로 취급하지 않는다.

## 제외 및 변경
- 기존 제외에 운영 사진/큐/로그/내보내기/인증서/환경/빌드 산출물/업데이트 백업 제외 추가.
- 실제 검사에서 제외 4,303개: .venv, DB/WAL/SHM, update_backups, pycache, EXE/APK, 구형 payload 및 updater 자료 등.
- 구형 루트 apply_update.py, APPLY_UPDATE.cmd, manifest.json, payload/, SHA256SUMS.txt, READ_ME_한국어.txt, 먼저읽기.txt는 보존하고 등록 제외. 현 버전 업데이트 방법으로 오인하지 않도록 함.
- web/pcx-inspection.png는 직접 열어 차량 검수 삽화임을 확인했고 예외 포함. Gradle wrapper JAR도 빌드 도구로 포함.
- 수정: .gitignore, README.md. 신규: AGENTS.md, docs/HANDOFF.md, docs/GIT_CANDIDATES.txt, 본 문서.
- 기능 소스·의존성·운영 DB·사진 변경 없음. 서버 중단/재시작 없음.

## 보안 검사
별도 임시 bare Git 저장소를 사용하여 운영 폴더의 .gitignore 적용 목록을 git ls-files --others --exclude-standard로 산출했다. 운영 폴더에는 .git을 생성하거나 staging하지 않았다. 임시 Git 생성은 샌드박스 권한 오류 후 사용자 실행 승인을 받아 수행했다. 이 승인은 commit/push 승인이 아니다.

등록 후보 텍스트 전체에 개인키 헤더, GitHub/AWS/OpenAI 형태 토큰, 암호/토큰 문자열 대입, 자격정보 포함 URL, 한국 휴대전화/주민등록번호 형식 패턴을 검사했다. 바이너리 PNG/JAR는 텍스트 검사에서 제외했다. .env.example은 example 도메인과 CHANGE_TO 자리표시자만 포함.

14개 탐지 위치를 문맥 검토: CI 테스트 DB와 docs/DEPLOY.md의 테스트 URL, compose.yaml의 환경변수 참조, tests/verification의 임시 DB용 테스트 암호와 응답 mock 토큰이었다. 실제 인증정보로 확인된 항목은 없고 고확신 개인키/토큰/개인정보 패턴 탐지도 없었다. 비밀 값은 보고에 싣지 않는다.

제외 동작 확인: warehouse.db 및 -wal/-shm, update_backups, Data/Vehicles, .env, EXE, payload 제외. .env.example, 검수 PNG, Gradle wrapper JAR 포함.

한계: 정규식 검사는 비밀 부재를 보증하지 않는다. 운영 DB/백업 내용, 환경변수 값, 외부 사진 경로는 읽지 않았다. JAR의 공급망 무결성은 검증하지 않았다. gradle-wrapper.properties의 validateDistributionUrl=false는 후속 빌드 보안 검토 항목이며 이번에 변경하지 않았다. 실제 인덱스/원격 이력의 검사는 최초 초기화/원격 refs 재확인 뒤 필요하다.

## CI 및 승인 이후 계획
1. 사용자 승인 후 임시 개발 작업 폴더를 만들고 후보 115개를 복사/해시 대조. 운영 데이터는 옮기지 않는다.
2. 기존 원격 Private·브랜치·태그/refs를 재확인. 이력이 생겼으면 fetch하여 차이 검토; 자동 pull/merge 하지 않는다.
3. 임시 작업 폴더에서 Git 초기화/기존 이력 연결, origin 설정, 후보만 staging. 실제 git diff --cached --name-only와 후보 목록 대조 및 staged 내용 재검사. 예상 밖 파일/변경이 있으면 보고.
4. 승인 범위 내 main 최초 commit/push. 새 원격 이력이 있으면 보존한다. 태그는 순수 버전 입증 및 별도 확인 전 생성하지 않는다.
5. push 후 로컬/원격 commit 대조 및 Actions 결과 확인. 운영 폴더로 기능 파일을 옮기는 것은 이번 소스 등록과 별개다.

.github/workflows/check.yml은 모든 push(브랜치 제한 없음) 및 workflow_dispatch에 반응한다. PostgreSQL 17 서비스에서 tests/test_workflow.py만 실행하고, Android assembleDebug 결과 app-debug.apk와 Windows C# EXE를 Actions 아티팩트로 업로드한다. 운영 서버 자동 배포/릴리스 서명/전체 테스트는 없다. 태그 push도 트리거할 수 있으므로 중복 실행을 고려한다.

현재 실제 staged 파일: 없음. commit/push/tag: 미실행. 사용자 요청에 따라 원격 업로드 승인을 기다린다.
