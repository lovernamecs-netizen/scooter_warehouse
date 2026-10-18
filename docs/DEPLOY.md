# 서버 배포·백업·복구

이 패키지에는 호스팅 계정이나 실제 도메인이 포함되어 있지 않습니다. Google·회사 API를 사용하지 않는 자체 서버입니다. 아래 명령은 선택한 서버 운영자가 실행하는 절차입니다. 외부 배포는 이번 작업에서 수행하지 않았습니다.

## 외부 서버 설치

전제: Docker Engine/Compose가 준비된 Linux 서버, 서버 IP로 연결한 DNS 도메인, 80/443 접근 가능. DB 포트는 외부에 공개하지 않습니다.

1. 프로젝트 폴더를 서버에 복사합니다. 운영 DB·비밀번호·서명키를 코드 저장소에 올리지 않습니다.
2. `.env.example`을 `.env`로 복사하고 도메인, DB 비밀번호, 백업 암호를 서로 다른 실제 값으로 지정합니다. DB 비밀번호는 URL-safe 값(예: 무작위 hex)을 사용합니다.
3. 서버에서 아래 명령을 실행합니다.

```sh
mkdir -p backups
sudo chown 10001:10001 backups
chmod 700 backups
chmod 600 .env
docker compose up -d --build
docker compose exec app python -m server.cli init
docker compose exec app python -m server.cli demo
```

`init`에서 관리자 비밀번호를 대화형으로 입력합니다. `demo`는 빈 마스터 DB에 예시 설정만 추가하므로 불필요하면 생략하고 직접 설정합니다. 실제 차량은 생성하지 않습니다.

Caddy가 설정한 도메인에 HTTPS를 제공하도록 구성했습니다. 인증서 발급 실패 시 DNS/포트/서버 시간을 확인합니다. 서버를 먼저 정상 연결한 뒤 PC와 APK에 `https://실제도메인`을 입력합니다.

확인:

```sh
docker compose ps
docker compose logs --tail=80 app proxy
```

로그에는 비밀번호·스마트키를 출력하지 않도록 앱을 구현했습니다. 인프라 로그 수집 정책은 운영자가 관리합니다.

## 최초 운영 검증

실제 재고를 입력하기 전에 테스트 VIN으로 입고→U→위치→주문→작업→출고를 수행합니다. PC와 폰에서 동시에 같은 빈 Slot을 선택했을 때 하나만 성공하는지 확인합니다. PostgreSQL 통합 테스트도 아래 CI 또는 별도 빈 테스트 DB에서 먼저 실행합니다. 실제 운영 DB를 테스트에 지정하지 않습니다.

```sh
pip install -r requirements-dev.txt
TEST_DATABASE_URL='postgresql+psycopg://testuser:testpass@localhost/testdb' python -m pytest -q tests/test_workflow.py
```

테스트 계정과 레코드가 생기므로 반드시 폐기 가능한 DB에서 실행합니다.

## 일일 암호화 백업

```sh
sh deploy/backup.sh
```

`backups/warehouse-시각.swh` 파일을 만듭니다. 스크립트는 `.env`에 설정한 백업 암호를 컨테이너 환경에서 사용합니다. 같은 파일명을 덮어쓰지 않습니다. 예를 들어 서버 crontab에 실제 경로로 다음을 등록할 수 있습니다.

```cron
0 18 * * * cd /실제/프로젝트경로 && sh deploy/backup.sh >> /실제/백업로그경로 2>&1
```

이 예시는 서버 시간이 UTC일 때 한국시간 03시입니다. 서버 시간대를 확인하고 조정합니다. 백업 보존 기간과 별도 저장장치 복사는 운영자가 설정해야 합니다. 암호도 백업 파일과 별도로 보관합니다. 자동 스케줄 등록과 외부 저장장치 복사는 이번 환경에서 실행하지 않았습니다.

## 복구

1. 서버의 쓰기 작업을 중지하고 원 DB를 유지합니다.
2. **새 빈 DB**를 생성합니다. 현재 DB를 삭제하거나 덮어쓰지 않습니다.
3. 새 DB의 DATABASE_URL과 원 백업 암호를 지정해 복구합니다.

```sh
DATABASE_URL='새_빈_DB_URL' WAREHOUSE_BACKUP_PASSWORD='백업암호' python -m server.cli restore --file /백업/파일.swh
```

운영에서는 환경파일/비밀 관리 기능을 사용해 비밀번호가 셸 이력에 남지 않게 합니다. CLI는 환경변수가 없으면 암호를 직접 입력받습니다.

4. 차량 대수·VIN·점유 Slot·출고 Snapshot·마감표를 비교한 후 앱의 연결 DB를 새 DB로 전환합니다.
5. 모든 기기에서 로그아웃·재로그인합니다. 세션·미확정 명령은 백업에서 복구하지 않습니다.

복구 명령은 기존 테이블에 데이터가 있으면 중단합니다. 백업은 AES-GCM으로 암호화하며 암호 오류·변조 시 복호화에 실패합니다. 원 백업의 schema_version이 맞지 않으면 복구하지 않습니다.

## 버전 업데이트

현재 DB schema는 1입니다. 업데이트 전에 백업하고 동일 스키마의 코드만 교체합니다. 향후 DB 구조 변경은 별도 마이그레이션과 복구 검증 후 적용해야 합니다. 이 패키지에 임의의 미래 버전 마이그레이션은 포함하지 않습니다.

Android 테스트 APK는 테스트 서명입니다. 정식 배포 시 소유자의 릴리스 서명키를 생성·안전 보관하고 서명합니다. Windows 실행기는 코드 서명 인증서로 서명하지 않았습니다. 서명/호스팅 비용이 발생하는 서비스를 자동 구매하지 않았습니다.
