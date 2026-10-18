> 2026-10-18 데이터 저장·백업 최신 변경: [DATA_SAFETY_20261018.md](DATA_SAFETY_20261018.md). 별도 임시 폴더 검증, 운영 데이터 이동·배포 미실행.

> 2026-10-18 안정화 최신 결과: [STABILITY_SMOKE_20261018.md](STABILITY_SMOKE_20261018.md). 격리 환경 검증 완료, 운영/원격 미적용.

> 최신 작업 인수인계: [CURRENT_HANDOFF_20261017.md](CURRENT_HANDOFF_20261017.md). 아래 내용은 2026-10-15 당시 조사 기록입니다.

# 인수인계 및 남은 작업 — 2026-10-15

첨부 ScooterWarehouse-Codex-Handoff.md는 요구사항/과거 기록으로 읽었다. 이번 사용자 요청은 조사·Git 등록 준비·문서 정리이며 기능 구현, commit/push/tag는 포함하지 않는다. 추가 사용자 지시: 앞으로 임시 작업 폴더에서 개발·수정·테스트를 마친 뒤 검증된 파일만 실사용 폴더에 반영한다.

## 현재 근거와 차이
- server/app.py, web/sw.js, android/app/build.gradle: 1.0.30. Android applicationId=com.hakom.warehouse.photos, versionCode=30.
- 로컬/상위 Git 저장소 없음. GitHub Desktop 내장 Git 사용 가능(PATH에는 없음). 원격 Private, admin/push/pull 권한, size=0, 브랜치 목록 비어 있음. 태그 API/전체 refs 확인은 아직 미완료.
- README는 1.0.9 설치본 설명이었으며 현재 소스 기준으로 갱신. 루트 apply_update.py/manifest.json/payload는 1.0.11 업데이트 잔여물로 등록 제외, 원본 보존. 이전 APK/EXE도 제외. 순수 1.0.30 배포본 일치 증거가 없어 v1.0.30 태그 보류.
- 현재 .venv의 Python 3.12.10, Pillow 11.3.0, pillow-heif 0.22.0 및 PIL/HEIF import 확인. 과거 PIL 누락은 현재 import로 재현되지 않으나 운영 서버 복구/재시작 성공은 미확인.
- 중고차 3단계, 파손 13부위, 상품 6방향(front/rear/left/right/cockpit/dashboard)은 server/used_stock.py와 web/used-stock.js에 구현. 구형 VIEWS의 perspective는 호환 코드에 남아 있음.
- 신규 웹 입고의 유비스 기본 true 구현. 저장된 초안/명시 입력에 따라 달라짐. 서버 기본과 UI 기본을 혼동하지 말 것.
- domain.py의 내부 ID/입고 회차, FIFO 후보, 출고 Snapshot/마감, parts.js의 캘린더, notifications.py의 사용자별 설정 및 관련 테스트 존재. 존재 확인은 회귀 성공을 뜻하지 않음.
- MainActivity: 시스템 카메라/FileProvider. PhotoQueue: 내부 영구 파일/AtomicFile/WorkManager. PhotoUploadWorker: HTTPS 업로드, id/hash 확인 후 원본 삭제, 재시도. 실제 폰 종료·재부팅·망 단절 동작은 미검증.
- photo_store.py: 원본과 1100px 썸네일 분리, EXIF/HEIF, UUID/hash, 차량/입고회차별 경로, journal, 원자 저장. photo_tools.py 및 test_photo_storage.py: Base64 보존 마이그레이션과 복구 검사 코드 존재.
- photo_backup.py: SQLite만 지원, hash 검증 후 새 폴더 복구. PostgreSQL 통합 백업 지원으로 표현하면 안 됨.

## 미완료 목록 (구현과 검증을 구분)
1. 등록: 승인 후 로컬 Git 초기화·실제 staging 대조, 원격 refs/태그 재확인, 최초 main commit/push. 순수 버전 입증 전 태그 생성 금지.
2. 의존성: 기존 .venv의 누락 탐지/설치 실패 차단/업데이트 복구/시작 오류 보존 개선 미완료. START_LOCAL_SERVER.cmd는 venv 최초 생성 시에만 설치하며, 현재 루트 updater는 구형이다.
3. 캐시: 버전 캐시 및 network-first는 구현. 입력 보존과 업데이트 안내/적용 흐름 개선, 구버전 화면 재발 검증은 남음. Ctrl+F5 해결 이력을 소스 롤백으로 해석하지 않는다.
4. APK: 배포명 스쿠터창고.apk 통일 미완료(CI는 app-debug.apk). 설치 앱 패키지/서명 및 기존 키 확인, versionCode 증가, 업데이트 설치/큐 보존 실기기 검증 필요. 새 키 서명/앱 삭제로 우회하지 않는다.
5. 사진: 원본 저장/큐/재시도/다운로드/백업 구현은 있음. Fold 촬영·HEIC·EXIF·원본 해상도·강제 종료·재부팅·통신 복구·계정 재로그인·디스크 부족 실기기 검증 필요.
6. 데이터: 임시 DB/합성 사진으로 마이그레이션 재시도, 입고 회차 보존, 중단 복구, SQLite 통합 백업/새 폴더 복구를 실행 검증할 것. PostgreSQL 지원은 별도 설계/검증 항목.
7. 업무 회귀: 지도 변경/동시 이동, VIN 중복/변경, FIFO 예외, 유비스, 출고대기 위치 해제/복귀, 관리자 출고, 과거 Snapshot 불변, 짐대 중복 차감·붙여넣기/자체 출고 중복 방지를 테스트할 것. 겨울/여름 토시의 기본 마스터 요구 충족 여부는 관리자 설정과 추가 대조 필요(운영 DB는 열지 않음).
8. UI: 기존 지도·카드·키보드·알림 구현 보존. VIN/색상 밀림, 줌/스크롤 유지, PC 밀도, Fold 접힘/펼침·키보드 및 알림 위치는 브라우저/실기기 확인 후 관찰된 문제만 수정. OS 푸시 구현 완료로 간주하지 않음.
9. 장기 리스/렌탈·반납·인수·사용기간·재상품화는 docs/leasing-extension.md의 설계와 입고 회차 모델을 바탕으로 별도 요구 시 진행. 전체 구현 완료 아님.

## 운영 보호
이번에 기능 소스, 의존성, DB, 사진, 서버 프로세스를 변경하지 않았다. 운영 테스트/마이그레이션/백업 작업도 실행하지 않았다. 검토된 소스만 임시 폴더로 옮겨 테스트하고, 향후 배포는 파일 목록·백업·복구 절차를 갖춰 진행한다. B2C OCR 연동 취소, 외부 API 가능성 가정 금지, 자동 상품 이미지 보정 금지, 실제 출고 VIN 촬영 강제 금지를 유지한다.
