# -*- coding: utf-8 -*-
"""
국민대학교 '오늘의 메뉴' 크롤러 v1
- 대상: https://www.kookmin.ac.kr/user/unLvlh/lvlhSpor/todayMenu/index.do
- 결과: menus.json (식당 > 날짜 > 코너 > 끼니 > 메뉴/가격)

실행 전 설치:
    pip install requests beautifulsoup4

실행:
    python kmu_crawler.py
"""

import json
import os
import re
from collections import OrderedDict
from datetime import date, datetime, timedelta

import requests
from bs4 import BeautifulSoup

URL = "https://www.kookmin.ac.kr/user/unLvlh/lvlhSpor/todayMenu/index.do"
MENUS_FILE = "menus.json"
ARCHIVE_DIR = "archive"        # 월별 보관 파일 폴더 (archive/YYYY-MM.json)
RECENT_DAYS = 21               # menus.json에 유지할 최근 기간(약 3주)


def kst_today() -> date:
    """GitHub Actions는 UTC로 도므로 KST(+9h) 기준 오늘 날짜를 계산."""
    return (datetime.utcnow() + timedelta(hours=9)).date()

# ── 정규식 패턴들 ──────────────────────────────────────────────
# 메뉴가 아닌 공지/안내 문구를 걸러내는 패턴
NOTICE_PAT = re.compile(
    r"(운영시간|휴점|휴무|미운영|주문\s*마감|문의해|변경\s*될\s*수|원산지|알레르기"
    r"|일일메뉴표|주말\s*보내세요|사전\s*주문|주문\s*필수|오픈합니다|정기식신청자"
    r"|방학\s*중\s*안내|안내\s*사항|상기\s*메뉴|원재료|식수)"
)
# "08:30 ~ 10:00", "중식11:30~14:00" 같은 콜론 형식 운영시간이 들어간 줄
CLOCK_PAT = re.compile(r"\d{1,2}:\d{2}")
# 시간대/요일만 적힌 줄 (예: "10시~17시", "평일 11시~18시", "토/일요일")
TIME_ONLY_PAT = re.compile(
    r"^[\s<(\[]*(평일|주말)?\s*(\d{1,2}\s*시\s*(\d{1,2}분)?\s*[~-]\s*\d{1,2}\s*시"
    r"(\s*\d{1,2}분)?|토/일요일|월~금|공휴일)[\s>)\]]*$"
)
# [중식] [석식] [조식] [중석식] 태그
MEAL_TAG = re.compile(r"\[(조식|중식|석식|중석식)\]")
# 가격: "￦5500", "￦ 5,500" 또는 줄 끝의 "메뉴명 4000" 형태
PRICE_WON = re.compile(r"￦\s*([\d,]+)")
PRICE_TAIL = re.compile(r"^(.*?)\s+(\d{4,5})$")  # "찹쌀탕수육 4000" 같은 케이스
# 날짜: 2026.05.18(월)
DATE_PAT = re.compile(r"(\d{4})\.(\d{2})\.(\d{2})")
# 장식 문자 제거용 (★프리미엄특식★, ♡...♡ 등은 남겨두고 싶으면 이 부분 수정)
DECOR_PAT = re.compile(r"[★☆♡♥◇※]+")

# 운영시간 줄 판별 (메뉴에서는 계속 제외하되, hours 필드로 따로 보존).
# 형식이 제각각이라 구조화하지 않고 원문 그대로 저장한다.
#   예: "운영시간", "평일운영시간", "중식11:30~14:00", "조식 : 08:30 ~ 10:00", "11시~18시"
HOURS_PAT = re.compile(
    r"운영\s*시간"                                          # '운영시간', '평일운영시간', '학기 중 운영시간'
    r"|\d{1,2}:\d{2}\s*[~∼\-]\s*\d{1,2}:\d{2}"              # 08:30 ~ 10:00, 11:30~14:00
    r"|\d{1,2}\s*시\s*[~∼\-]\s*\d{1,2}\s*시"                # 11시~18시, 10시~17시
    r"|(조식|중식|석식|조\s*중식)\s*:?\s*\d{1,2}\s*[:시]"   # 중식11:30, 석식17:00
)


# 최종 안전망: 완성된 이름이 공지처럼 보이면 버림 (가격 없는 경우에만)
JUNK_NAME_PAT = re.compile(r"(안내|방학|평일|주말|요일|휴무|휴점|운영|공휴일)")


def fetch_html() -> str:
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"
        )
    }
    resp = requests.get(URL, headers=headers, timeout=15)
    resp.raise_for_status()
    resp.encoding = "utf-8"
    return resp.text


def restaurant_name_from_caption(caption_text: str) -> str:
    """'국민대학교 한울식당(법학관 지하1층) 메뉴 테이블' -> '한울식당(법학관 지하1층)'"""
    name = caption_text.replace("국민대학교", "").replace("메뉴 테이블", "")
    return name.strip()


def guess_meal_from_corner(corner: str):
    """코너명에 끼니가 박혀있는 경우 추론 (예: '가마 중식', '석식Ⅰ', '5코너 (조식)')"""
    if "조식" in corner or "아침" in corner:
        return "조식"
    if "중식" in corner:
        return "중식"
    if "석식" in corner:
        return "석식"
    return None


def split_cell_lines(cell) -> list:
    """셀 안의 텍스트를 줄 단위 리스트로 (br 태그 기준)"""
    text = cell.get_text("\n", strip=True)
    lines = [ln.strip() for ln in text.split("\n")]
    return [ln for ln in lines if ln]


def parse_cell(lines: list, default_meal, hours_sink=None):
    """
    셀 한 칸을 파싱해서 [{meal, items:[{name, price}]}] 형태로 반환.
    - [중식]/[석식] 태그가 있으면 태그 기준으로 끼니를 나눔
    - 가격(￦)이 나올 때마다 '하나의 메뉴 세트'로 묶어서 flush
    - hours_sink(list)가 주어지면, 운영시간 줄을 원문 그대로 거기에 모은다
      (메뉴 items에서는 계속 제외)
    """
    results = []
    current_meal = default_meal
    current_items = []
    name_buffer = []

    def flush_item(price):
        nonlocal name_buffer
        name = " ".join(name_buffer).strip()
        name = DECOR_PAT.sub("", name).strip()
        name = re.sub(r"\s{2,}", " ", name)  # 연속 공백 정리
        # 안전망: 가격도 없고 이름이 공지처럼 보이면 버림
        if name and not (price is None and JUNK_NAME_PAT.search(name)):
            current_items.append({"name": name, "price": price})
        name_buffer = []

    def flush_meal():
        nonlocal current_items
        # 가격 없이 남은 이름도 저장 (가격 미표기 메뉴)
        if name_buffer:
            flush_item(None)
        if current_items:
            results.append({"meal": current_meal, "items": current_items})
        current_items = []

    for line in lines:
        # 운영시간 줄은 메뉴에서 제외하되 hours_sink에 원문 보존
        if HOURS_PAT.search(line):
            if hours_sink is not None:
                hours_sink.append(line)
            continue
        # 공지/안내 줄은 스킵
        if NOTICE_PAT.search(line):
            continue
        # 시간대/요일만 적힌 줄도 스킵 (예: "10시~17시", "평일 11시~18시")
        if TIME_ONLY_PAT.match(line):
            continue
        # "08:30 ~ 10:00" 같은 콜론 형식 운영시간이 포함된 줄은 공지로 간주
        if CLOCK_PAT.search(line):
            continue
        # <이벤트> <비오는날> 같은 꺾쇠 장식 제거 (메뉴명은 유지)
        line = re.sub(r"<[^>]*>", " ", line).strip()
        if not line:
            continue

        # 끼니 태그를 만나면 이전 끼니 마무리
        tag_match = MEAL_TAG.search(line)
        if tag_match:
            flush_meal()
            tag = tag_match.group(1)
            current_meal = "중식/석식" if tag == "중석식" else tag
            line = MEAL_TAG.sub("", line).strip()
            if not line:
                continue

        # 같은 줄에 ￦가격이 붙은 경우: "김말이떡볶이￦3300" 또는 "비빔막국수 ￦3300"
        won = PRICE_WON.search(line)
        if won:
            name_part = PRICE_WON.sub("", line).strip()
            if name_part:
                name_buffer.append(name_part)
            flush_item(int(won.group(1).replace(",", "")))
            continue

        # "찹쌀탕수육 4000" 처럼 ￦ 없이 숫자만 붙은 경우
        tail = PRICE_TAIL.match(line)
        if tail and not any(ch.isdigit() for ch in tail.group(1)[-2:]):
            name_buffer.append(tail.group(1).strip())
            flush_item(int(tail.group(2)))
            continue

        # 가격이 없는 일반 메뉴 줄 -> 이름 버퍼에 누적 (세트 구성품)
        name_buffer.append(line)

    flush_meal()
    return results


def parse_table(table) -> dict:
    caption = table.find("caption")
    name = restaurant_name_from_caption(caption.get_text(strip=True)) if caption else "이름미상"

    # 헤더에서 날짜 추출
    dates = []
    header_cells = table.find("tr").find_all(["th", "td"])
    for cell in header_cells:
        m = DATE_PAT.search(cell.get_text())
        dates.append(f"{m.group(1)}-{m.group(2)}-{m.group(3)}" if m else None)

    menus = []
    hours_raw = []
    for row in table.find_all("tr")[1:]:
        cells = row.find_all(["th", "td"])
        if len(cells) < 2:
            continue
        corner = " ".join(cells[0].get_text(" ", strip=True).split())
        default_meal = guess_meal_from_corner(corner)

        for idx, cell in enumerate(cells[1:], start=1):
            if idx >= len(dates) or dates[idx] is None:
                continue
            lines = split_cell_lines(cell)
            if not lines:
                continue
            # 운영시간 줄은 주말/평일 구분 없이 원문 그대로 수집 (메뉴에서는 제외)
            for ln in lines:
                if HOURS_PAT.search(ln):
                    hours_raw.append(ln)
            # 주말(토/일) 데이터는 메뉴에서 버림 — 교내 식당은 주말 휴무인데
            # 원본 페이지가 주간 메뉴를 주말 칸에도 복붙해두기 때문.
            # 단, 생활관식당(기숙사)은 주말에도 운영하므로 예외.
            weekday = date.fromisoformat(dates[idx]).weekday()  # 5=토, 6=일
            if weekday >= 5 and "생활관" not in name:
                continue
            for block in parse_cell(lines, default_meal):
                menus.append({
                    "date": dates[idx],
                    "corner": corner,
                    "meal": block["meal"],
                    "items": block["items"],
                })

    # 운영시간 중복 제거(첫 등장 순서 보존)
    seen = set()
    hours = [h for h in hours_raw if not (h in seen or seen.add(h))]

    result = {"name": name, "menus": menus}
    if hours:
        result["hours"] = hours
    return result


def load_existing_restaurants(path: str) -> list:
    """기존 menus.json을 읽어 restaurants 리스트를 반환. 없거나 깨졌으면 빈 리스트."""
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f).get("restaurants", [])
    except (FileNotFoundError, json.JSONDecodeError):
        return []


def _group(restaurants: list) -> "OrderedDict":
    """restaurants -> {식당: {날짜: {코너: [블록,...]}}} (삽입 순서 보존)."""
    grouped = OrderedDict()
    for r in restaurants:
        dates = grouped.setdefault(r["name"], OrderedDict())
        for m in r["menus"]:
            corners = dates.setdefault(m["date"], OrderedDict())
            corners.setdefault(m["corner"], []).append(m)
    return grouped


def merge_restaurants(old_restaurants: list, new_restaurants: list) -> list:
    """
    (식당, 날짜, 코너) 기준으로 기존 데이터와 새 크롤을 병합한다.
    - 같은 (날짜, 코너)를 다시 크롤링하면 새 데이터가 기존을 덮어씀 (새 데이터 우선).
    - 새 크롤에 없는 과거 (날짜, 코너)는 그대로 보존.
    출력은 날짜 오름차순, 코너는 삽입 순서(원본 표의 코너 순서)를 유지.
    """
    merged = _group(old_restaurants)  # 기존을 바탕으로
    for name, dates in _group(new_restaurants).items():
        m_dates = merged.setdefault(name, OrderedDict())
        for dt, corners in dates.items():
            m_corners = m_dates.setdefault(dt, OrderedDict())
            for corner, blocks in corners.items():
                m_corners[corner] = blocks  # 새 (날짜,코너)가 기존을 덮어씀

    # hours(운영시간)는 식당 단위 메타데이터: 새 크롤 것이 있으면 최신으로 갱신
    hours_map = {}
    for r in old_restaurants:
        if r.get("hours"):
            hours_map[r["name"]] = r["hours"]
    for r in new_restaurants:
        if r.get("hours"):
            hours_map[r["name"]] = r["hours"]

    result = []
    for name, dates in merged.items():
        menus = []
        for dt in sorted(dates):  # 날짜 오름차순
            for blocks in dates[dt].values():  # 코너 삽입 순서 유지
                menus.extend(blocks)
        entry = {"name": name, "menus": menus}
        if hours_map.get(name):
            entry["hours"] = hours_map[name]
        result.append(entry)
    return result


# ── 월별 아카이브 ──────────────────────────────────────────────

def archive_path(ym: str) -> str:
    return os.path.join(ARCHIVE_DIR, f"{ym}.json")


def load_archive(ym: str) -> list:
    """archive/YYYY-MM.json의 restaurants 리스트. 없거나 깨졌으면 빈 리스트."""
    try:
        with open(archive_path(ym), encoding="utf-8") as f:
            return json.load(f).get("restaurants", [])
    except (FileNotFoundError, json.JSONDecodeError):
        return []


def save_archive(ym: str, restaurants: list) -> None:
    os.makedirs(ARCHIVE_DIR, exist_ok=True)
    data = {
        "month": ym,
        "updated_at": datetime.now().isoformat(timespec="seconds"),
        "source": URL,
        "restaurants": restaurants,
    }
    with open(archive_path(ym), "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def split_by_month(restaurants: list) -> dict:
    """restaurants를 월(YYYY-MM)별로 나눈다. -> {ym: restaurants(해당 월 메뉴만)}"""
    months = OrderedDict()
    for r in restaurants:
        by_ym = OrderedDict()
        for m in r["menus"]:
            by_ym.setdefault(m["date"][:7], []).append(m)
        for ym, menus in by_ym.items():
            entry = {"name": r["name"], "menus": menus}
            if r.get("hours"):
                entry["hours"] = r["hours"]  # 운영시간은 식당 단위라 각 월에 함께 저장
            months.setdefault(ym, []).append(entry)
    return months


def merge_into_archives(new_restaurants: list) -> list:
    """이번 크롤 데이터를 월별 archive 파일에 병합 저장. 갱신된 월 목록 반환."""
    touched = []
    for ym, month_restaurants in split_by_month(new_restaurants).items():
        merged = merge_restaurants(load_archive(ym), month_restaurants)
        save_archive(ym, merged)
        touched.append(ym)
    return touched


def rebuild_recent(today: date) -> list:
    """archive들에서 최근 RECENT_DAYS일치를 추려 menus.json용 restaurants를 만든다."""
    cutoff = today - timedelta(days=RECENT_DAYS)
    # 최근 창(cutoff~오늘)이 걸치는 달들의 archive를 모아 병합
    months = set()
    d = cutoff
    while d <= today:
        months.add(d.strftime("%Y-%m"))
        d += timedelta(days=1)
    # 미래(다가오는 주) 데이터가 든 이번 달 archive도 포함
    months.add(today.strftime("%Y-%m"))

    merged = []
    for ym in sorted(months):
        merged = merge_restaurants(merged, load_archive(ym))

    result = []
    for r in merged:
        menus = [m for m in r["menus"] if m["date"] >= cutoff.isoformat()]
        if menus:
            entry = {"name": r["name"], "menus": menus}
            if r.get("hours"):
                entry["hours"] = r["hours"]
            result.append(entry)
    return result


def write_menus(restaurants: list) -> None:
    data = {
        "fetched_at": datetime.now().isoformat(timespec="seconds"),
        "source": URL,
        "restaurants": restaurants,
    }
    with open(MENUS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def main():
    html = fetch_html()
    soup = BeautifulSoup(html, "html.parser")

    new_restaurants = []
    for table in soup.find_all("table"):
        parsed = parse_table(table)
        if parsed["menus"]:  # 메뉴가 하나도 없는 테이블은 제외
            new_restaurants.append(parsed)

    # 1) 이번 크롤 데이터를 월별 archive에 병합 (과거 무손실 보존)
    touched = merge_into_archives(new_restaurants)

    # 2) archive에서 최근 3주치를 추려 menus.json 재생성 (첫 로딩용, 가볍게)
    today = kst_today()
    restaurants = rebuild_recent(today)
    write_menus(restaurants)

    # 간단 요약 출력
    print(f"✅ 완료! 갱신 archive: {', '.join(touched) or '없음'}")
    print(f"   menus.json: 식당 {len(restaurants)}곳 (최근 {RECENT_DAYS}일, 기준일 {today})")
    for r in restaurants:
        dates = sorted({m["date"] for m in r["menus"]})
        span = f"{dates[0]}~{dates[-1]}" if dates else "없음"
        print(f"  - {r['name']}: 메뉴 블록 {len(r['menus'])}개, 날짜 {len(dates)}일 ({span})")


if __name__ == "__main__":
    main()
