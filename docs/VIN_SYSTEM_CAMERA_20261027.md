# VIN 기본 카메라 복구 및 Git 배포 기준

## 원인
운영 소스에서 VIN은 WarehouseNative.scan()을 우선 호출했고 Android의 camera()는 VinCameraActivity(앱 자체 카메라)를 열었다. 일반 사진 촬영과 달리 웹 capturePhoto({rearRequired:true})도 시스템 카메라 경로에서 제외되어 있었다. 이번 등록증 OCR 제거 변경에는 이 경로 수정이 없었다.

## 수정
- Android VIN도 capture="environment" 파일 입력으로 시스템 카메라에 요청.
- 기존 APK의 onShowFileChooser → captureFilePhoto → ACTION_IMAGE_CAPTURE 연결 재사용.
- 기존 recognizeImage 사진 인식 및 결과 확인 흐름 유지. Android 브라우저는 기존 서버 인식 연결 유지.
- PC의 후면 카메라 제약과 촬영 취소 유지.
- app.js/camera.js 자원 버전 및 서비스워커 캐시 버전 갱신.
- APK 소스/서명/applicationId/버전은 변경하지 않음. 실제 설치 APK가 기존 파일 캡처 연결을 포함해야 함.
- Android의 후면 카메라 요청은 OS/카메라 앱이 처리하므로 삼성의 특정 렌즈 선택까지 웹에서 보장하지 않음.

## 이번 실행 검증
- tests/vin_rear_browser.py: 실제 Chromium, Android UA/앱 브리지 모의 환경, 일반 Android UA 환경에서 촬영/재촬영/취소, capture 속성, 사진 인식 결과 확인. 기존 scan/getUserMedia 호출 없음 확인. PC 촬영 제약 유지 확인.
- tests/system_camera_browser.py: Android 시스템 카메라 파일 입력/원본 바이트/취소 검사 통과.
- pytest: OCR 제거, 사진 저장, 업무 화면 관련 13개 통과.
- JS 문법 및 git diff 공백 검사 통과.
- 실제 갤럭시/Android 카메라 실행과 기기 전환은 미검증. APK 빌드는 수행하지 않음.

## 버전 관리
- 기존 운영 상태 기준 커밋: d2b628c (등록증 OCR 제거까지 포함).
- Git 브랜치 codex/vin-system-camera에서 개발. 비관리 임시 폴더 파일 복사 방식 사용 안 함.
- 운영에는 검증한 커밋을 fast-forward로 적용. 운영 미커밋 변경 발견 시 적용 중단하고 차이를 검토.
- DB·사진·환경 파일을 커밋/교체하지 않음. 이번 배포는 웹 자원·검사·문서 변경으로 서버 재시작이 필요하지 않음.
- 복구가 필요하면 배포 커밋을 별도 수정 브랜치에서 revert하고 검증 후 적용. reset --hard/일괄 파일 덮어쓰기 금지.
- GitHub push는 이번 작업에 포함하지 않음.

## 유지해야 할 동작
명시적 변경 지시 없이는 Android VIN 기본 카메라 경로, 기존 장착/재고 차감 규칙, 등록증 OCR 제거 상태를 되돌리지 않는다. 변경 범위에 맞는 회귀 검사를 실행하며 실기기 미검증 사항은 구분한다.
