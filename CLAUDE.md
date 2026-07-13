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
### 다음 순서
1. 이슈 #2 데이터 정리 (잔여 노이즈 '제헌절' 등 — 크롤러 필터는 반영됨,
   Actions 크롤 1회로 저장 데이터 정리 후 이슈 닫기)
2. 마무리 폴리시: 색 대비(작은 회색 텍스트), 접근성 aria(탭 aria-selected 등),
   스크롤 페이드를 오버플로 감지로 정교화(넘칠 때만 표시)
3. 개강 홍보 준비 (도메인 구매 검토 포함)
(이후: 웹 푸시 Supabase)
### 조건부 / 보류
- 시험기간 주말: 10월 중간고사 때 실제 운영 확인 후 크롤러 주말 허용 + 문구 확정
- 특식 뱃지: 크롤러가 지우는 ★특식★ 장식을 뱃지로 살리기
- 도움말 페이지, 메뉴 검색, 가격 필터, 주간 보기, 통계 페이지
- 게시판: 운영 부담으로 보류 (한다면 "한줄평" 수준으로 축소)
- 미매칭 이슈 중복 코멘트 방지 (매 크롤마다 같은 이슈에 코멘트 누적되는 것)
