# 한국 캘린더 표시 자료

확인일: 2026-10-29. 업무 집계/가격/권한에는 영향을 주지 않는 로컬 표시 자료.

2024–2027년 국경일·전국 공휴일을 포함한다. 토요일 파랑, 일요일 빨강, 공휴일 빨강 우선. 2024/2025 제헌절은 국경일 명칭만 표시하며 공휴일로 표시하지 않는다. 2026 노동절·제헌절 지정은 2027 월력요항 발표의 정정 설명을 반영했다.
지원 범위 밖 연도에는 국경일 명칭과 자료 범위 안내만 표시한다. 음력/대체/선거/임시공휴일을 추정하지 않는다. 새 월력요항이나 임시공휴일 발표 시 korean-holidays.js를 업데이트하고 테스트 후 배포한다. 지역 공휴일과 사업장 자체 휴무는 포함하지 않는다.

Sources:
- https://astro.kasi.re.kr/kor/life/post/calendarData?search_year=2024
- https://astro.kasi.re.kr/kor/life/post/calendarData?search_year=2025
- https://astro.kasi.re.kr/kor/life/post/calendarData?year=2026
- https://astro.kasi.re.kr/kor/life/post/calendarData?year=2027
- https://www.kasa.go.kr/prog/plcyBrf/brief/kor/sub01_01_04/view.do?plcyBrfNo=431 (우주항공청 2027년 월력요항, 공공누리 제1유형)
- https://m.korea.kr/news/policyNewsView.do?newsId=148933400 (2024-10-01)
- https://www.korea.kr/news/policyNewsView.do?newsId=148938559 (2025-01-27)
- https://www.goebc.kr/upload/soancho-e/na/bbs_174/2025/04/FA92F753-7D64-C103-3E64-8DFB54969136.pdf (2025-06-03)

Validation: isolated actual Chrome server smoke passed calendar navigation, mobile viewport 390px, identical typography across four calendar labels, weekend colors, Oct 3/5 holiday markers, 2025 vs 2026 Constitution Day classification. Existing domain API isolation checks passed. Galaxy device unverified.
Deployment: web-only Git fast-forward. No database/photos/settings mutations or server restart. Rollback by reverting this code commit, keeping all business data.
