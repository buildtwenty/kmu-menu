# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

국민대학교(Kookmin University) 학식(cafeteria menu) crawler + a static GitHub Pages viewer. A daily GitHub Action scrapes the school's "오늘의 메뉴" page into `menus.json`, commits it, and `index.html` renders that JSON as a mobile-friendly page. There is no build step, no backend, and no test suite.

## Commands

```bash
python kmu_crawler.py          # scrape live site -> overwrites menus.json, prints a summary
pip install -r requirements.txt  # requests, beautifulsoup4 (Python 3.12 in CI)
```

Preview the site locally (it `fetch()`es `menus.json`, so `file://` won't work — needs a server):

```bash
python -m http.server 8000     # then open http://localhost:8000/index.html
```

The crawler always hits the live university URL — there is no offline fixture. To test parser changes without network, save a page snapshot and feed it through `parse_table()` manually.

## Architecture

**Data flow:** `kmu_crawler.py` → `archive/YYYY-MM.json` (per-month full history) → `menus.json` (recent 3 weeks only) → `index.html` (client-side JS). The JSON shape is the contract between crawler and frontend; changing it means updating both `parse_table()` and the `render()`/`init()` functions in `index.html`.

**Data files (both share the same restaurants/menus shape):**
```
{ fetched_at|updated_at, source, restaurants: [
    { name, menus: [ { date: "YYYY-MM-DD", corner, meal, items: [ {name, price|null} ] } ] }
] }
```
`meal` is one of `조식`/`중식`/`석식`/`중식/석식` or `null`. `price` is an int (KRW) or `null` for unpriced set components.

**Archive split (`kmu_crawler.py`):** each crawl merges new data into `archive/YYYY-MM.json` by month (`merge_into_archives`), then regenerates `menus.json` as the last `RECENT_DAYS` (21) days pulled from the relevant month archives (`rebuild_recent`). `menus.json` stays small so first page load is light; the frontend lazily fetches `archive/YYYY-MM.json` only when the calendar opens a past month. `merge_restaurants` keys on (name, date, corner) — new data wins, old dates preserved. `migrate_to_archive.py` was the one-time move of the pre-split `menus.json` into archives.

**The crawler is essentially a text-cleaning pipeline.** The source HTML tables mix real menu items with operating hours, notices, allergen warnings, and decorative characters, all crammed into `<br>`-separated cells. Most of `kmu_crawler.py` is the regex filtering that separates food from noise:
- `NOTICE_PAT`, `TIME_ONLY_PAT`, `CLOCK_PAT`, `JUNK_NAME_PAT` — reject non-menu lines.
- `parse_cell()` accumulates lines into a `name_buffer` and "flushes" a menu item whenever it hits a price (`￦...` via `PRICE_WON`, or a trailing 4–5 digit number via `PRICE_TAIL`). `[중식]`/`[석식]` tags split a cell into separate meals.
- When touching parsing, expect to adjust these regexes rather than restructure the flow. Verify against a real fetch, since the source markup is the ground truth.

**Weekend handling (`parse_table`):** the source page duplicates weekday menus into Saturday/Sunday columns even though campus cafeterias are closed, so weekend (`weekday >= 5`) cells are dropped — **except** for `생활관식당` (dorm cafeteria), which does operate weekends. Any name-based special-casing like this lives here.

**`index.html` is a single self-contained file** (inline CSS + JS, no dependencies). On load it fetches only `menus.json` + `calories.json`, builds a continuous date selector + per-restaurant tabs, and highlights the current/next meal by wall-clock time (`nextMeal()`). The calendar button lazily loads `archive/YYYY-MM.json` for past-month browsing (`loadMonth`); `restaurantsForDate()` picks the archive month when browsing the past, else `menus.json`. The kcal toggle matches menu names against `calories.json` keywords (longest-match wins). Restaurant `name` is split into name + location via the `(...)` suffix convention (e.g. `한울식당(법학관 지하1층)`).

## Automation

`.github/workflows/crawl.yml` runs daily at 06:00 KST (21:00 UTC cron), executes the crawler, and commits `menus.json` + `archive/` if changed (bot user `menu-bot`). Commits titled `🍚 메뉴 자동 갱신 <date>` are this bot. A later step (`calorie_check.py` + `gh`) opens/updates a "칼로리 미매칭 메뉴" issue when today-or-later menus lack a calorie keyword (`continue-on-error`, so it never fails the run). Manually triggerable via `workflow_dispatch`.

## ⏳ 임시 메모 — 학교 셧다운(전기설비 점검) 대응 (끝나면 삭제, ~2026-08 중순)

**확정 정보(학교 공지 원문 · 2026-07-24 확인)**
- 셧다운 기간: **2026-07-25(토) ~ 08-02(일)**, 교내 전 건물 (**생활관 A·B·C동 제외**).
- 이 기간 교내 식당 **사실상 휴업** (생활관식당은 운영 가능성 있음).
- (이전 조사에서 단수 8/7·정전 8/8 미러 제목을 봤으나, 확정 공지 기간은 위 7/25~8/2. 8월 초 별도 단수/정전 세부일이 이 기간 안에 포함된 것으로 봄.)

**대응 완료(2026-07-24)**
- index.html: `SHUTDOWN` 상수(start/end/msg) + `inShutdown()`. 기간 내 날짜면 (a) 메뉴 영역 상단 조용한 안내 배너(`.shutdown-banner`, 남색 안내 톤), (b) 데이터 없는 날 빈 상태 문구를 "셧다운 휴무"로 대체. 기간 지나면 자동으로 안 뜸.
- kmu_crawler.py: 끼니 라벨 단독 유령 항목 제거(`MEAL_ONLY_PAT`). 셧다운 평일 "석식+미운영" 패턴 대비. (커밋 bb1a17c)

**🔻 TODO — 8/3 이후 배너 코드 제거**
- index.html에서 `SHUTDOWN` 상수, `inShutdown()`, `.shutdown-banner` CSS, render()의 배너 삽입부(`shutdownBanner`)·빈상태 `inShutdown` 분기를 제거. (기간이 지나면 화면엔 이미 안 뜨므로 급하진 않음. 정리 차원.)
- 이 임시 메모 섹션도 함께 삭제.

**셧다운 종료 후(8/2·8/3 크롤) 재확인 체크리스트**
1. `archive/2026-08.json`에 8/3(월)~ 개강 전 평일 정상 메뉴가 들어오는지.
2. 7/25~8/2 셀 저장 결과 — 휴무 문구가 비워져 프론트에 "셧다운 휴무/배너"로 뜨는지, "석식" 등 유령 항목이 안 남았는지(유령 수정 반영 확인).
3. Actions 로그: 셧다운 기간 크롤이 이상감지(오늘 이후 0건)로 실패해 알림 메일이 왔는지, 몇 통인지. 예상된 실패면 무시.
4. 생활관식당이 이 기간 실제로 운영해 데이터가 들어오는지(들어오면 배너와 함께 정상 표시됨).
5. 점검 종료 후 정상 크롤 재개 시 menus.json 자동 정상화 확인(실패일엔 커밋 안 되므로 낡은/빈 데이터 덮어쓰기 없음).

## 로드맵
### 완료
- 크롤러 + 자동 갱신 + 병합 보관
- 식당 탭 레이아웃, 연속 달력, 주말 휴무 표시, 상시 메뉴 분리
- 칼로리 추정 (kcal 토글, 미매칭 이슈 알림)
- 월별 아카이브 + 과거 탐색
- 날짜 탭 월요일 시작, 햄버거 서랍 메뉴, 운영시간 표시 보류(SHOW_HOURS=false)
- GoatCounter 연동 (익명 방문 통계, 비공개 · 화면 표시 없음)
  - 계정 생성·이메일 인증 완료, 대시보드: kmu-menu.goatcounter.com
  - 주간 이메일 리포트 설정됨 (매주 발송 → vydbswnd0729@naver.com)
  - 대시보드 시간대 Asia/Seoul 확인, 첫 방문 기록 확인 (2026-07-11)
  - 방문자 수는 사이트에 비공개 (대시보드로만 확인)
- 공유 기능 (헤더 📤 → 식당 선택 → 끼니 선택 2단계 바텀시트)
  - 식당 하나뿐이면 식당 선택 생략, 끼니 하나뿐이면 끼니 선택 생략(바로 공유)
  - 텍스트: 🍚 식당명 끼니 (M/D 요일) + "코너명 · 대표메뉴 가격" 줄 + 구분선(―――) + 링크
  - 대표메뉴 압축: 세트(4토막+)는 주메뉴만, 조사(와/과)로 끝나면 다음 토막까지
  - Web Share(모바일 OS 공유창) / 미지원 시 클립보드 복사 + 토스트
  - 카톡 실물 검증 완료 (title 미전달로 본문 중복 제거)
- 칼로리 테이블 보강: 보양식·탕류 등(삼계탕·해신탕·감자탕·설렁탕·지리탕·무국·쌈닭·냉소면·물냉)
  + 크롤러 공지 필터 보강(공휴일 단독표기 HOLIDAY_PAT, "부탁드립니다"류, 가격 뒤 자모 파편 ㅂ)
- 크롤러 이상 감지: 신선 스크레이프 통계(crawl_stats.json) 기반, 식당<3 또는 오늘 이후 메뉴 0이면
  워크플로우 실패 → GitHub 알림 메일 (커밋 전 검사라 빈/낡은 데이터 안 덮어씀)
- 디자인 다듬기 (첫인상): 터치영역 44px, 헤더 라인 SVG 아이콘(📤/☰ 통일),
  가로 스크롤 힌트(엣지 페이드), 좌우 거터 16px 통일, 로딩 스켈레톤,
  빈 상태 세로중앙+아이콘(메뉴 없는 날 식당칩 숨김), 달력 nodata 날짜 진하게
- 이스터에그 3종: 콘솔 서명(저장소 링크), 로고 5연타 크레딧 토스트, 치킨 메뉴 탭 시 🍗 팝
- 저장 데이터 노이즈 일회성 정리 (이슈 #2): 필터는 신규 유입만 막고 merge는 과거 보존이라
  필터 추가 전 저장된 '제헌절'·'부탁드립니다' 잔존 → 현재 필터를 저장 데이터에 1회 재적용해 제거
- 마무리 폴리시: 작은 회색 텍스트 대비 강화(--sub 한 톤 진하게), 접근성 aria
  (날짜 탭·식당 칩 role=tab+aria-selected, 끼니 aria-pressed, 공유·햄버거 aria-expanded,
   토스트 role=status), 스크롤 페이드를 오버플로 감지로 정교화(넘칠 때만·넘치는 쪽만,
   끝까지 스크롤하면 사라짐, resize·웹폰트 로딩에 반응)
### 다음 순서
1. 개강 홍보 준비 (도메인 구매 검토 포함)
(이후: 웹 푸시 Supabase)
### 조건부 / 보류
- 시험기간 주말: 10월 중간고사 때 실제 운영 확인 후 크롤러 주말 허용 + 문구 확정
- 특식 뱃지: 크롤러가 지우는 ★특식★ 장식을 뱃지로 살리기
- 도움말 페이지, 메뉴 검색, 가격 필터, 주간 보기, 통계 페이지
- 게시판: 운영 부담으로 보류 (한다면 "한줄평" 수준으로 축소)
- 미매칭 이슈 중복 코멘트 방지 (매 크롤마다 같은 이슈에 코멘트 누적되는 것)
- 병합 시 필터 소급 재적용: 기본은 안 함. 필터를 고칠 때 일회성 정리 스크립트로 처리.
  (merge 단순 유지 · 과거 데이터 소급 변형 위험 · NOTICE substring이 조립된 이름에 오제거 위험 회피.
   자동화한다면 앵커형 필터 HOLIDAY_PAT/JAMO_JUNK_PAT만 재적용하는 중간안이 그나마 안전)
