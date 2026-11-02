# 출고 달력 선택일 이력 필터 — 2026-11-02

운영 기준 acc4d047de0a38adef006a8b72d576119cf1a80d. 운영 DB를 읽기 전용 확인한 결과 2026-10-20 출고 Snapshot 3건이 존재하고 목록에 필요한 vehicle/options/items 형식도 정상이다. 사용자 화면은 달력 출고3대 / 목록0건 불일치이다.

기존 달력은 선택일을 인자로 받지만 이력 렌더러는 별도 전역 selectedDay/search로 다시 필터링했다. 동일한 달력 렌더 요청의 선택일/검색어에서 목록을 한 번만 필터하고 renderer에는 확정된 행만 전달하도록 변경했다. 이력 제목에 표시 건수, 검색 적용 시 조건 및 해제 버튼을 추가했다. 사용자 세션의 정확한 런타임 값은 직접 확인하지 못했으므로 당시 전역 값 변화가 원인이었다고 단정하지 않는다.

변경: web/dispatch-calendar.js, web/app.js, web/index.html, web/sw.js. DB/출고/마감 재작성 없음. 고객정보 권한 유지. 출고취소/반품 표기 및 중고차 분리 유지.
검증: tests/dispatch_selected_day_browser.py 실제 격리 서버+Chrome, 합성 과거 출고행으로 10/20 3건·10/21 2건·월전체5건, 현재재고가 없어도 과거Snapshot 표시, 검색 조건/해제, 연속 날짜 전환, 390px 통과. tests/calendar_browser.py 공통 달력·고객명·취소/반품·모바일·구매가액 분리 회귀 통과. JS 구문/git diff 검사 통과. 갤럭시 실기기 미검증, APK 변경 없음.

운영은 DB/Data/환경 백업 및 해시 검사 후 Git ff-only 적용. 백업/이전커밋/배포결과: deployment-recovery/dispatch-selection-* . 코드 rollback은 해당 prior/target 사이 Git revert로 이력 보존; 운영 DB를 옛 백업으로 덮어쓰지 않는다. GitHub push 없음.
