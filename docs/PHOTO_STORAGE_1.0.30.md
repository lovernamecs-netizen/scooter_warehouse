# ScooterWarehouse 1.0.30 — 사진 저장·Android 촬영

작성일: 2026-10-15 (한국 시간). 1.0.29 전체 작업공간과 누적 업데이트의 대상 파일을 대조한 후 기존 소스를 수정했습니다. 운영 DB에는 접근하거나 변경하지 않았습니다.

## 설치 순서

1. PC 서버를 종료하고 직원들의 입력도 중지합니다. 기존 프로그램 폴더 전체를 별도 드라이브에 복사해 두세요.
2. 제공한 UPDATE.zip을 **전부 압축 해제**합니다. ZIP 안에서 CMD를 바로 실행하지 마세요.
3. `APPLY_UPDATE.cmd` 실행 → 기존 `warehouse.db`가 있는 프로그램 폴더 지정 → `UPDATE` 입력.
4. 새 사진 처리 패키지(Pillow, pillow-heif)를 설치한 후 지원 소스 해시를 확인하고 코드를 교체합니다. 설치에 실패하면 메시지를 확인하고 재시도하세요. 임의로 DB를 만들거나 교체하지 않습니다.
5. 기존 PC 서버를 다시 실행합니다. PC 브라우저 Ctrl+F5, 휴대폰 앱은 닫았다 다시 여세요.
6. 관리자 → 관리 설정 → **사진 저장·백업**에서 원본 저장 폴더와 백업 폴더를 지정합니다. 예: `D:\ScooterWarehouse\Data\Vehicles`. 경로는 휴대폰이 아니라 PC 서버의 경로입니다.
7. 먼저 시험 차량으로 촬영·다운로드·백업·새 폴더 복구를 확인하세요.

기본 원본 경로는 DB 파일 옆 `Data\Vehicles`, 백업 경로는 DB 파일 옆 `Backups`입니다. 관리자 경로 변경은 이후 사진부터 적용되며, 기존 사진은 이전 경로에서 계속 읽습니다. 기존 폴더를 임의로 삭제·이동하면 안 됩니다. 자동 백업은 기본 꺼짐이며 관리자가 켜야 합니다. 서버가 실행 중일 때 하루 한 번 실행하고 실패 내역을 표시합니다. 여러 서버 프로세스를 동시에 실행하지 마세요.

## Android APK 설치 대상

APK 이름: `ScooterWarehouse-1.0.30-photos-test.apk`.
앱 표시: **스쿠터 창고 · 사진관리**, 패키지: `com.hakom.warehouse.photos`, versionCode 30.

1.0.28의 `com.hakom.warehouse.updated` 서명 키는 현재 작업공간에서 찾지 못했습니다. 따라서 그 앱 위에 덮어쓰기 설치하는 APK가 아닙니다. 기존 앱을 지우지 않고 **별도 앱**으로 설치합니다. 같은 PC 서버 HTTPS 주소와 기존 계정으로 로그인하면 기존 차량 데이터를 조회합니다. 서버 DB를 새로 만들 필요가 없습니다.

보관되어 있던 1.0.7 서명 백업의 키로 서명한 **검증용 debug APK**입니다. 서명 인증서 SHA-256: `addab3d71137b5c95413cebaeed12d607cc5675d9dac7d2ed6875d775583216b`. 향후 이 사진관리 앱의 업데이트는 같은 패키지와 키를 사용해야 합니다. 개인 서명 키는 배포 ZIP에 넣지 않았습니다. Play Store 배포용 release APK가 아닙니다.

유효한 HTTPS 서버가 필요합니다. 기존 Tailscale/HTTPS 연결 주소를 그대로 사용하세요. 이 업데이트는 네트워크 구성이나 인증서를 자동 변경하지 않습니다.

## 촬영과 대기열

중고차 → 입고 기록을 한 번 저장 → 파손 검수 → 이미지 위 부위 아이콘 → 촬영.
APK에서는 Android `ACTION_IMAGE_CAPTURE` + `EXTRA_OUTPUT` + FileProvider로 시스템 카메라 앱을 엽니다. 특정 삼성 패키지를 강제 지정하지 않습니다. 원본 URI에 카메라가 기록한 파일을 그대로 전송합니다. 기존 VIN OCR과 다른 사진의 공통 웹 카메라는 유지합니다.

촬영 원본과 작업 JSON은 앱의 filesDir에 보관합니다. WorkManager의 네트워크 조건·지수 백오프 재시도를 사용하며, PC가 업로드 ID와 SHA-256이 일치하는 저장 완료 응답을 반환한 뒤에만 휴대폰 임시 원본을 삭제합니다. 서버가 응답하기 전에 앱이 중단되어도 같은 업로드 ID로 재시도합니다. 미리보기만 EXIF 방향을 적용해 축소합니다.

화면 상태: 촬영 중 → 전송 대기/PC 저장 중 → PC 저장 완료. 영구 오류는 저장 실패, 로그인 만료는 재로그인 안내입니다. 대기 사진 삭제에는 복구 불가 확인이 있습니다. 다른 계정이나 다른 서버로 대기 사진을 자동 전송하지 않습니다.

오프라인 촬영 범위는 **이미 저장된 차량의 파손 화면을 열어 둔 상태**입니다. 처음 등록하는 차량의 오프라인 등록, 서버에 한 번도 접속하지 않은 앱의 전체 오프라인 사용은 구현 범위가 아닙니다. 앱 종료·재부팅 후에는 보관된 대기 작업의 재전송을 WorkManager가 담당합니다. Android의 강제 중지와 배터리 제한에서는 다시 앱을 열어야 작업이 재개될 수 있습니다. 로그인이 만료되면 촬영 계정으로 다시 로그인해야 합니다. 앱 삭제/앱 데이터 삭제는 대기 원본을 지우므로 전송 완료 전에 하지 마세요.

원본 한 장은 25MB 이하, 입고 회차당 활성 사진 최대 100장입니다. JPEG/PNG/WebP/HEIC를 서버에서 실제 디코딩하여 검사합니다. 큰 사진을 제한에 맞춰 몰래 축소하지 않습니다. 범위를 넘거나 손상된 파일은 오류로 남기고 APK 원본을 보존합니다. 실기기 카메라가 선택하는 해상도/형식은 아직 확인하지 않았습니다.

## PC 파일·데이터 구조

`저장 루트 / 차량 내부 ID / 입고 회차 ID / Damage | Inspection | Product | Thumbnails | Metadata`

파일명은 부위 코드와 UUID입니다. DB의 `used_media:<stay>:<photo>`에는 내부 차량/입고 ID, 경로, 크기, 가로·세로, MIME/EXIF 방향, SHA-256, 시각, 작업자, 상태가 저장됩니다. `photo_upload:<UUID>`는 중복 업로드의 확인 원장입니다. 새 원본을 Base64로 DB에 저장하지 않습니다. 부위 메모는 입고 회차의 프로필에 연결되며, APK 메모는 촬영 당시 기준값과 비교해 충돌 시 409 오류로 알립니다.

원본은 임시 파일 기록·fsync·원자적 이름 변경 후 DB 트랜잭션으로 연결합니다. DB가 취소되면 `.journal`과 파일을 유지하고 관리자 오류 목록에 표시합니다. 동일 ID 재전송으로 원본 해시를 확인해 연결을 복구할 수 있습니다. 원본 누락/해시 오류도 관리 화면에서 확인할 수 있습니다. 고아 파일을 자동 삭제하거나 타 차량에 임의 연결하지 않습니다.

삭제/교체 사진은 메타데이터에서 숨기고 파일은 보존합니다. 백업에는 숨긴 사진도 포함합니다. 현재 버전에는 원본 영구 정리 기능이 없으므로 디스크 사용량을 확인하세요. 차량별 ZIP에는 활성 사진과 Metadata JSON을 넣습니다. 입고 회차 선택으로 과거 사진을 조회할 수 있습니다. 차량별 폴더 열기는 Windows PC 서버에서 실행됩니다.

파손 도해는 기존 PCX 형태 참고 이미지이며 실제 부품 도면이 아닙니다. 13개 부위 ID를 유지하고 이미지 기준 상대 좌표로 표시합니다. 반대편 좌측 카울은 동일 차체 영역의 구분 아이콘으로 표시하므로 실제 정비 도면 수준의 정확성을 주장하지 않습니다.

## 기존 사진 마이그레이션

기존 Base64 사진은 업데이트 직후에도 읽을 수 있습니다. 운영 데이터를 자동 삭제하지 않습니다. 파일 변환을 수행하려면 서버를 종료하고 기존 프로그램 폴더에서:

```bat
set DATABASE_URL=sqlite:///warehouse.db
.venv\Scripts\python.exe -m server.photo_tools migrate > migration-report.json
```

먼저 DB와 현재 파일 사진을 통합 백업합니다. 기존 사진 목록을 읽고 원본 추출 → 실제 이미지 검증 → 파일 저장 → DB 연결 → 다운로드 바이트 검증 순서로 처리합니다. 실패 항목은 report의 failed에 기록됩니다. 원래 `used_media_data`/`used_photo` Base64는 남겨 둡니다. 다시 실행해도 같은 업로드 ID를 재사용합니다. 원래 이미지가 작은 경우 없는 고해상도를 복원하지 않습니다.

이전 프로그램으로 돌아가야 하면 업데이트 백업의 **이전 코드와 당시 DB를 함께** 복구해야 합니다. 새 버전에서 입력한 이후 데이터는 그 이전 백업에 없습니다. 원본 폴더를 보존하고 최신 통합 백업을 먼저 만드세요. 운영 DB에 이전 파일을 무작정 덮어쓰지 마세요.

## 백업과 복구

관리 설정에서 수동/매일 백업, 백업 위치, 보존 1~90개, 마지막 성공/실패를 확인합니다. DB 쓰기를 잠근 동안 SQLite 스냅샷과 참조 사진/미리보기/메타데이터를 ZIP으로 만들고 SHA-256 전체 검증 후 확정합니다. 백업 중 다른 저장 요청은 대기할 수 있습니다. 백업 ZIP은 암호화되지 않으므로 접근 권한이 제한된 별도 드라이브에 보관하세요. 기존 암호화 SWH 백업 명령에도 파일 원본을 포함하도록 보완했습니다.

복구 화면: 백업 선택 → 무결성 검사·미리보기 → 새 복구 폴더 입력 → 확인. 현재 운영 DB를 덮어쓰지 않고 새 폴더로 복구하며, 복구 DB 안의 사진 경로를 새 위치로 바꿉니다. 로그인 세션은 삭제합니다.

CLI 예:
```bat
.venv\Scripts\python.exe -m server.photo_tools backup
.venv\Scripts\python.exe -m server.photo_tools verify --file "D:\Backups\ScooterWarehouse-날짜.zip"
.venv\Scripts\python.exe -m server.photo_tools restore --file "D:\Backups\ScooterWarehouse-날짜.zip"
.venv\Scripts\python.exe -m server.photo_tools restore --file "D:\Backups\ScooterWarehouse-날짜.zip" --destination "D:\ScooterWarehouse-Restored" --confirm
```

복구 결과를 운영에 연결하려면 기존 서버를 종료하고 복구한 DB를 명시해 실행합니다. 기존 `START_LOCAL_SERVER.cmd`는 DB 경로를 덮어쓰므로 아래 명령으로 직접 실행하거나 해당 BAT의 DATABASE_URL을 복구 경로로 설정하세요.
```bat
set DATABASE_URL=sqlite:///D:/ScooterWarehouse-Restored/warehouse.db
.venv\Scripts\python.exe -m uvicorn server.app:app --host 127.0.0.1 --port 8765
```

사진 경로는 복구 폴더 안의 `photos`로 이미 바뀌어 있습니다. 새 복구 폴더 이름을 사후에 바꾸면 경로가 깨집니다. 복구본에는 자동 백업이 꺼져 있으므로 경로를 확인한 뒤 다시 설정하세요. Windows 권한·드라이브 연결·실제 서버 중지/재기동은 현장에서 검증해야 합니다.

## 기술 근거

- Android 공식 시스템 카메라 인텐트: https://developer.android.com/guide/components/intents-common#Camera
- Android FileProvider: https://developer.android.com/reference/androidx/core/content/FileProvider
- WorkManager 지속 작업: https://developer.android.com/develop/background-work/background-tasks/persistent-work
- WorkManager 작업 조건과 재시도: https://developer.android.com/develop/background-work/background-tasks/persistent-work/getting-started/define-work

실제 기능 검증 결과와 미검증 항목은 동봉 TEST_RESULTS.md를 보세요.
