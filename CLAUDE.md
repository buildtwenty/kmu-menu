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

**Data flow:** `kmu_crawler.py` → `menus.json` → `index.html` (client-side JS). `menus.json` is the only interface between the two halves; its shape is the contract. Changing the JSON schema means updating both `parse_table()` and the `render()`/`init()` functions in `index.html`.

**`menus.json` shape:**
```
{ fetched_at, source, restaurants: [
    { name, menus: [ { date: "YYYY-MM-DD", corner, meal, items: [ {name, price|null} ] } ] }
] }
```
`meal` is one of `조식`/`중식`/`석식`/`중식/석식` or `null`. `price` is an int (KRW) or `null` for unpriced set components.

**The crawler is essentially a text-cleaning pipeline.** The source HTML tables mix real menu items with operating hours, notices, allergen warnings, and decorative characters, all crammed into `<br>`-separated cells. Most of `kmu_crawler.py` is the regex filtering that separates food from noise:
- `NOTICE_PAT`, `TIME_ONLY_PAT`, `CLOCK_PAT`, `JUNK_NAME_PAT` — reject non-menu lines.
- `parse_cell()` accumulates lines into a `name_buffer` and "flushes" a menu item whenever it hits a price (`￦...` via `PRICE_WON`, or a trailing 4–5 digit number via `PRICE_TAIL`). `[중식]`/`[석식]` tags split a cell into separate meals.
- When touching parsing, expect to adjust these regexes rather than restructure the flow. Verify against a real fetch, since the source markup is the ground truth.

**Weekend handling (`parse_table`):** the source page duplicates weekday menus into Saturday/Sunday columns even though campus cafeterias are closed, so weekend (`weekday >= 5`) cells are dropped — **except** for `생활관식당` (dorm cafeteria), which does operate weekends. Any name-based special-casing like this lives here.

**`index.html` is a single self-contained file** (inline CSS + JS, no dependencies). It fetches `menus.json`, builds a date selector, and highlights the current/next meal based on wall-clock time (`nextMeal()`). Restaurant `name` is split into name + location via the `(...)` suffix convention (e.g. `한울식당(법학관 지하1층)`).

## Automation

`.github/workflows/crawl.yml` runs daily at 06:00 KST (21:00 UTC cron), executes the crawler, and commits `menus.json` if it changed (bot user `menu-bot`). Commits titled `🍚 메뉴 자동 갱신 <date>` are this bot. Manually triggerable via `workflow_dispatch`.

## TODO

- **시험기간 주말 메뉴 허용** — 크롤러의 주말 제외 로직(`parse_table`의 `weekday >= 5` 필터)에 허용 날짜 범위(시험기간) 설정을 추가해, 해당 기간에는 주말 메뉴도 보존하도록.
- **다음 주 메뉴 미리보기** — 학교 '오늘의 메뉴' 페이지의 주간 이동(다음 주) 파라미터를 조사해, 미래 주차 메뉴도 크롤링/표시.
- **한울식당 고정 코너 처리** — 매일 동일한 1코너 등 고정 코너를 카드 하단으로 내리거나 접어서, 날짜별로 바뀌는 코너가 먼저 보이게. (index.html `render()`)
- **예정 기능** — 오전 8시 알림 → 좋아요 → 식당 지도.
