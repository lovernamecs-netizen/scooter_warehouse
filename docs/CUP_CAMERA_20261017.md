# B2B 컵홀더 및 Android 기본 카메라

작업 폴더: C:/Users/CCS/ScooterWarehouse-development/closing-inventory-20261016

B2B CUP 기본품은 FORZA(차종 ID 규칙의 RBF 브라켓 매핑)는 별도 전달, 그 외 차종은 장착이다. 문자열 차종명을 추측하지 않는다. 운영 FORZA ID가 기존 RBF 규칙으로 매핑되어 있어야 한다. 컵홀더 기본 제공 제외는 기존 제외+사유 기능을 유지한다. 별도 추가 전달 수량도 유지한다. B2C와 이미 확정된 주문/출고 Snapshot은 변경하지 않는다. 기존 주문은 자동 전환하지 않으며 계획 재검토 시 새 규칙을 적용한다. 완료된 전달/장착 작업을 자동 삭제하지 않는다.

web/camera.js는 Android에서 getUserMedia 축소 촬영 대신 image/* + capture=environment 입력을 사용한다. PC 촬영은 기존 동작을 유지한다. 신형 APK의 사진 큐 브리지는 이미 ACTION_IMAGE_CAPTURE와 EXTRA_OUTPUT 원본 저장 방식을 사용하며 그대로 보존한다. VIN 및 일반 파일 촬영 경로도 APK의 onShowFileChooser에서 동일한 기본 카메라 호출과 원본 URI 반환으로 연결했다. 카메라 권한 거부/취소/실행 실패 시 null 결과를 반환한다. 사진 큐와 서버 확인 전 원본 보존 정책은 변경하지 않는다.

삼성 카메라가 시스템 기본 촬영 앱이면 해당 앱이 처리한다. 특정 삼성 패키지를 강제로 지정하지 않는다. 호출 시 제공되는 초광각/줌/촬영 모드는 OS와 카메라 앱에 달려 있다. 전체 카메라 기능이 필요한 경우 기본 카메라 앱에서 촬영한 뒤 기존 사진 파일 선택으로 원본을 가져올 수 있다.
공식 참고: https://developer.android.com/guide/components/intents-common#Camera

## 검증
- 주문 서버 검사: 60 통과, 컵홀더 전달을 가정한 기존 정정 검사 1개 실패. FORZA 전달 사례로 갱신 후 해당 검사 1개 통과. PCX/NMAX/FORZA/XMAX/ADV/Zontes/Husky 기본 용도 및 출고 시 1개 차감 확인.
- Windows Chrome 주문/재고/지도 및 기존 사진 UI 검사 통과. 고해상도 원본/해시·확대·사진 큐 브리지 mock 회귀 포함.
- Android user-agent 브라우저 검사: 시스템 capture 입력 요청, 원본 바이트 유지, 취소 처리 통과. 실제 외부 앱 실행 검증은 아니다.
- Android :app:compileReleaseJavaWithJavac 성공. SDK 메타데이터/기존 deprecated API 경고가 있다.
- 실제 갤럭시 촬영·삼성 초광각·권한·프로세스 종료 복구·설치 서명 호환은 미검증. 서명 APK 생성/설치하지 않았다.

## 적용 범위
컵홀더 변경은 서버/웹 업데이트. Android 브라우저의 촬영 요청 변경은 웹 업데이트. 기존 APK에서 파일 선택만 열리는 경로를 기본 카메라로 연결하려면 새 APK가 필요하다. 통합 ZIP의 review/android는 변경 소스이며 설치 APK가 아니다. 기존 패키지/서명 확인 없이 삭제나 재서명하지 않는다.
운영 폴더/DB/사진, Git push/배포는 변경하지 않았다. 누적 패치는 기존 기준 main 0087e51151d61a6b1d2962f8db028bea85d6519c용이며 이전 ZIP과 중복 적용하지 않는다. CLOSING_INVENTORY_RELEASE.md의 백업/사전검사/복구 절차를 따른다.
