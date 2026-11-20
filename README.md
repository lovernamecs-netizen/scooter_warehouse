# ScooterWarehouse

Windows PC 기반 스쿠터 창고 관리. BLACKJAM CRM과 별개입니다. 2026-10-15 조사에서 서버·웹 캐시·Android 버전 표시는 1.0.30입니다. 공식 배포본과 바이트 일치는 확인하지 않았습니다.

## 운영과 개발 분리
현재 폴더는 실사용 폴더입니다. 앞으로 개발·수정·업데이트는 별도 임시 작업 폴더에서 수행하고 테스트 완료 후 검증된 파일만 운영 폴더로 옮깁니다. 이전 버전 파일 백업, 변경 목록, 중단 필요 시간, 복구 절차를 준비합니다. DB·사진·환경·서명키·사진 큐를 덮어쓰지 않습니다.

## 구조
- server/: FastAPI/SQLAlchemy, 차량·지도·주문·출고·부품·중고차·사진·백업
- web/: PC/모바일 UI, Service Worker, 검수 삽화
- android/: Java WebView, VIN OCR, 시스템 카메라, 지속 사진 큐
- windows/: C# 실행기 및 실행/빌드/백업 CMD
- tests/, verification/: 서버 및 브라우저 검사
- deploy/, compose.yaml: 기존 PostgreSQL/컨테이너 구성. Windows 운영의 필수 조건이 아닙니다.
- docs/: 과거 기록과 현재 인수인계/등록 검토

## 개발 실행
아래는 운영 데이터가 없는 별도 개발 폴더에서만 실행합니다.
```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
$env:DATABASE_URL = 'sqlite:///development.db'
.\.venv\Scripts\python.exe -m server.cli init
.\.venv\Scripts\python.exe -m server.cli demo
.\.venv\Scripts\python.exe -m uvicorn server.app:app --host 127.0.0.1 --port 8766
```
init에서 관리자 암호를 직접 설정합니다. 개발 테스트에는 위처럼 별도 DB와 포트를 지정합니다.

운영 폴더를 다른 Windows PC로 옮겼다면 `windows/START_LOCAL_SERVER.cmd`를 실행합니다. 현재 PC의 Python 3.12 64비트를 자동으로 찾으며, 없으면 python.org 공식 설치 파일의 서명을 확인하고 설치 화면을 엽니다. 설치를 완료하면 필요한 패키지 설치와 서버 실행을 이어갑니다. 첫 설치에는 인터넷 연결이 필요합니다. 복사된 `.venv`가 작동하지 않거나 패키지가 부족하면 `.venv-local`에 실행 환경을 구성합니다. DB는 기존 `DATABASE_URL` 또는 `WAREHOUSE_DATA_DIR` 설정을 사용하고, 설정이 없으면 운영 폴더의 `warehouse.db`를 사용합니다. 기존 DB가 없으면 시작 오류를 안내합니다.

## 테스트·빌드
별도 개발 폴더에서 DATABASE_URL을 개발 DB로 설정하고 TEST_DATABASE_URL을 제거한 뒤 실행합니다.
```powershell
Remove-Item Env:TEST_DATABASE_URL -ErrorAction SilentlyContinue
.\.venv\Scripts\python.exe -m pytest -q tests/test_workflow.py tests/test_photo_storage.py
```
fixture는 임시 SQLite DB와 합성 사진을 사용합니다. 브라우저 검사는 기존 절대경로·서버 주소·Playwright 설치를 먼저 확인합니다.

Android: JDK 17, Android SDK 35, Gradle 8.9에서 `android\gradlew.bat -p android assembleDebug`. debug APK는 기존 앱 업데이트 호환성을 보장하지 않습니다. Windows: .NET Framework C# 컴파일러로 Launcher.cs를 빌드합니다. BUILD_LAUNCHER.cmd는 빌드 후 실행기까지 실행하므로 개발 PC에서만 사용합니다.

push/수동 실행 시 Actions는 PostgreSQL의 test_workflow.py, Android debug APK 빌드/아티팩트 업로드, Windows EXE 빌드/아티팩트 업로드를 수행합니다. 운영 배포나 릴리스 서명은 없습니다.

## 데이터와 검증 한계
Git은 데이터 백업이 아닙니다. DB/WAL/SHM·Data/Vehicles·별도 사진 경로·백업·큐를 보존합니다. 실행 중 SQLite를 파일 하나만 복사해 백업하지 않습니다. photo_backup 통합 백업은 SQLite 전용입니다.
현재 Python 3.12.10, Pillow 11.3.0, pillow-heif 0.22.0 및 사진 모듈 import를 확인했습니다. 서버 재시작, 기능 테스트, 빌드, 휴대폰 업데이트, Fold 실기기 검증은 실행하지 않았습니다. Tailscale 설치 흔적은 있으나 실제 HTTPS 연결은 미검증입니다. 과거 TEST_REPORT는 현재 테스트 결과가 아닙니다.

[인수인계](docs/HANDOFF.md) · [등록 검토](docs/GIT_REGISTRATION_REVIEW.md) · [전체 후보](docs/GIT_CANDIDATES.txt)
