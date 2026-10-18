# 리스·렌탈 확장 설계 — 후속 개발

이 문서는 설계이며 사용시작/반납/고객인수 입력 화면은 이번 버전에 구현하지 않았습니다.

현재 차량 UUID와 VIN, 입고 회차(Stay), 실제 출고 시각, 당시 차량정보·장착품·추가 전달품 Snapshot을 보존합니다. 새 출고 Snapshot에는 제조년월도 포함합니다. 과거 출고 원장은 추정값으로 변경하지 않습니다.

## 확장 모델

| 데이터 | 주요 항목 | 역할 |
|---|---|---|
| RentalEpisode | id, vehicle_id, outbound_id, contract_ref, status, version | 계약·사용 회차. 재대여 시 새 회차 |
| RentalEvent | episode_id, event_type, occurred_at, recorded_at, actor, reason, correction_of | 사용 시작·반납·인수 및 정정 이력 |
| ReturnInspection | episode_id, stay_id, inspected_at, condition, notes | 실제 반납 검수·재입고 연결 |
| EquipmentEvent | vehicle_id, episode_id, item_snapshot, qty, action, occurred_at | 사용 중 장착·교환·탈거와 반납 시 차이 |

실제 출고일(dispatched_at)은 기존 Outbound.at을 참조합니다. 사용 시작일(use_started_at)은 출고일과 같다고 자동 확정하지 않습니다. 실제 반납(returned_at)과 고객 인수(acquired_at)는 별도 이벤트이며, 한 회차에서 동시에 완료되지 않도록 제한합니다.

사용 일수는 시작/종료, 휴지·교체 정책을 확정한 후 계산합니다. 과거 발생일과 나중에 입력한 날을 각각 저장합니다. 잘못 입력한 날짜는 기존 이벤트 삭제 대신 사유가 있는 정정 이벤트로 남깁니다.

반납예정만으로 창고 재고를 늘리지 않습니다. 실제 입고확정과 새 Stay 생성은 하나의 트랜잭션으로 처리합니다. 기존 반품·재입고 기능은 리스 계약 반납 기능 전체를 구현한 것이 아닙니다. 고객 인수는 소유권 이전 이벤트이며 재출고 실적으로 중복 집계하거나 재고에 다시 넣지 않습니다.

반납 검수에서 장착품의 분실·교환·탈거를 기록하더라도 최초 출고 Snapshot을 덮어쓰지 않습니다. 계약 모듈은 별도 명령·화면으로 분리하고 기존 차량/출고/입고 ID를 참조합니다. 중복 반납·인수는 버전 검사와 명령 멱등성으로 방지합니다. 관리자 입력과 타 부서 조회 권한을 분리합니다.
