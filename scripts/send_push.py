# -*- coding: utf-8 -*-
"""
아침 메뉴 웹 푸시 발송 (평일 08:00 KST, .github/workflows/push.yml)

- menus.json에서 오늘(KST) 메뉴 요약을 만든다. 공유 기능(index.html buildShareText)의
  압축 문법을 그대로 옮겨 식당마다 '대표메뉴 가격' 한 줄.
- Supabase subscriptions 테이블의 구독권에 pywebpush로 보낸다.
- 404/410(만료·해지된 구독)은 테이블에서 지운다.

환경변수 (GitHub Secrets → env):
  SUPABASE_SECRET_KEY   sb_secret_… (구독 조회·삭제용. 코드에 넣지 말 것)
  VAPID_PRIVATE_KEY     VAPID 개인키 PEM 전문 (코드에 넣지 말 것)
  VAPID_SUBJECT         (선택) mailto:… 기본값 있음

실행:
  python scripts/send_push.py            # 발송
  python scripts/send_push.py --dry-run  # 요약 텍스트와 대상 수만 출력, 발송 없음
  python scripts/send_push.py --date 2026-09-18 [--dry-run]   # 특정 날짜로 요약
"""

import argparse
import json
import os
import re
import sys
from datetime import date, datetime
from zoneinfo import ZoneInfo

import requests

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MENUS_FILE = os.path.join(ROOT, "menus.json")

SUPABASE_URL = "https://xwxvvexfnmuzjbnkzqlx.supabase.co"   # 공개 값
SITE_URL = "https://buildtwenty.github.io/kmu-menu/"
VAPID_SUBJECT_DEFAULT = "mailto:teambuildtwenty@gmail.com"
KST = ZoneInfo("Asia/Seoul")
WEEKDAYS = ["월", "화", "수", "목", "금", "토", "일"]

# index.html RESTAURANT_ORDER와 동일 (이용자 많은 순). 목록에 없는 식당은 뒤로.
RESTAURANT_ORDER = ["학생식당", "한울식당", "교직원식당", "청향 한식당", "청향 양식당", "K-Bob+"]
MAX_LINES = 6          # 알림 본문 줄 수 (안드로이드 펼침 기준 6줄 정도가 한계)
TTL_SECONDS = 6 * 3600 # 오전 중에만 의미 있는 알림 → 6시간 지나면 폐기


# ── 공유 기능의 대표메뉴 압축 (index.html splitDish 포팅) ──────────
# 판정에서만 빼는 장식 토막
DECO_PATS = [
    re.compile(r"(?<!\S)\*[^*\s]+\*(?!\S)"),                       # *가을낭만*
    re.compile(r"(?<!\S)\[[^\]]*\]"),                              # 단독 [오늘의 추천메뉴]
    re.compile(r"(?<![^\s\]])-(?:\S+(?:\s+\S+편(?!\S))?)?(?!\S)"),  # ]-인천 강화도편 부제
    re.compile(r"^T/O(?!\S)", re.I),                               # 앞의 T/O
]
SINGLE_DISH_CORNER = re.compile(r"^메뉴\s*\d+$")   # 코너 하나에 요리 하나(청향)


def main_dish(name: str, corner: str) -> str:
    """세트('주메뉴 쌀밥 반찬 …')는 주메뉴만, 단품(3토막 이하)은 그대로."""
    s = (name or "").strip()
    bare = re.sub(r"^\[[^\]]*\]\s*", "", s)
    bare = re.sub(r"^T/O\s+", "", bare, flags=re.I)
    deco = [(m.start(), m.end()) for pat in DECO_PATS for m in pat.finditer(s)]
    toks = [(m.start(), m.end()) for m in re.finditer(r"\S+", s)
            if not any(a < y and x < b for (a, b), (x, y) in [((m.start(), m.end()), d) for d in deco])]
    if len(toks) < 4 or SINGLE_DISH_CORNER.match(corner or ""):
        return bare
    end = toks[0][1]
    if re.search(r"[와과&]$", s[toks[0][0]:end]) and len(toks) > 1:   # 조사로 끝나면 다음 토막까지
        end = toks[1][1]
    return s[toks[0][0]:end]


def base_name(full: str) -> str:
    m = re.match(r"^(.*?)\s*\(", full)
    return m.group(1) if m else full


def classify_corners(restaurant: dict) -> dict:
    """최근 평일 최대 10일 동안 매일 동일한 코너는 'fixed'(상시), 아니면 'varying'."""
    dates = sorted({m["date"] for m in restaurant["menus"]
                    if date.fromisoformat(m["date"]).weekday() <= 4})[-10:]
    dset = set(dates)
    sig = {}
    for m in restaurant["menus"]:
        if m["date"] not in dset:
            continue
        s = sig.setdefault(m["corner"], {})
        s[m["date"]] = s.get(m["date"], "") + "|".join(f"{i['name']}:{i.get('price')}" for i in m["items"]) + "#"
    return {c: ("fixed" if len(v) >= 2 and len(set(v.values())) == 1 else "varying")
            for c, v in sig.items()}


def meal_rank(meal):
    """아침 알림이므로 점심(또는 끼니 구분 없음)을 대표로, 그다음 조식, 석식."""
    if meal is None or "중식" in meal:
        return 0
    if meal == "조식":
        return 1
    return 2


def restaurant_line(r: dict, day: str):
    menus = [m for m in r["menus"] if m["date"] == day and m["items"]]
    if not menus:
        return None
    cls = classify_corners(r)
    # 변동 코너 우선 → 점심 우선 → 원본 순서 (안정 정렬)
    menus.sort(key=lambda m: (cls.get(m["corner"]) == "fixed", meal_rank(m.get("meal"))))
    m = menus[0]
    item = next((i for i in m["items"] if i.get("price")), m["items"][0])
    dish = main_dish(item["name"], m["corner"])
    price = f" {item['price']:,}원" if item.get("price") else ""
    return f"{base_name(r['name'])} · {dish}{price}"


def build_summary(data: dict, day: str):
    """{title, body} 또는 오늘 메뉴가 없으면 None."""
    order = {n: i for i, n in enumerate(RESTAURANT_ORDER)}
    rests = sorted(data["restaurants"], key=lambda r: order.get(base_name(r["name"]), len(order)))
    lines = [ln for ln in (restaurant_line(r, day) for r in rests) if ln]
    if not lines:
        return None
    d = date.fromisoformat(day)
    return {
        "title": f"🍚 오늘의 학식 ({WEEKDAYS[d.weekday()]})",
        "body": "\n".join(lines[:MAX_LINES]),
        "url": SITE_URL,
        "tag": f"kmu-menu-{day}",
    }


# ── Supabase (secret key: 구독 조회·삭제) ──────────────────────────
def sb_headers(secret: str) -> dict:
    return {"apikey": secret, "Authorization": f"Bearer {secret}"}


def fetch_subscriptions(secret: str) -> list:
    out, offset, page = [], 0, 1000
    while True:
        resp = requests.get(
            f"{SUPABASE_URL}/rest/v1/subscriptions",
            params={"select": "id,endpoint,keys", "order": "id", "offset": offset, "limit": page},
            headers=sb_headers(secret), timeout=30,
        )
        resp.raise_for_status()
        rows = resp.json()
        out.extend(rows)
        if len(rows) < page:
            return out
        offset += page


def delete_subscription(secret: str, row_id) -> bool:
    resp = requests.delete(
        f"{SUPABASE_URL}/rest/v1/subscriptions",
        params={"id": f"eq.{row_id}"},
        headers={**sb_headers(secret), "Prefer": "return=minimal"}, timeout=30,
    )
    return resp.ok


# ── 발송 ───────────────────────────────────────────────────────────
def send_all(subs: list, payload: dict, pem: str, secret: str) -> dict:
    from py_vapid import Vapid
    from pywebpush import WebPushException, webpush

    vapid = Vapid.from_pem(pem.encode("utf-8"))
    claims = {"sub": os.environ.get("VAPID_SUBJECT", VAPID_SUBJECT_DEFAULT)}
    data = json.dumps(payload, ensure_ascii=False)
    stats = {"ok": 0, "expired": 0, "failed": 0}
    for row in subs:
        keys = row.get("keys")
        if isinstance(keys, str):
            try:
                keys = json.loads(keys)
            except json.JSONDecodeError:
                keys = None
        if not row.get("endpoint") or not isinstance(keys, dict):
            print(f"  [skip] id={row.get('id')} 구독권 형식 이상")
            stats["failed"] += 1
            continue
        info = {"endpoint": row["endpoint"], "keys": keys}
        status = None
        try:
            resp = webpush(subscription_info=info, data=data, vapid_private_key=vapid,
                           vapid_claims=dict(claims), ttl=TTL_SECONDS, timeout=15)
            status = getattr(resp, "status_code", None)
        except WebPushException as ex:
            status = getattr(ex, "status_code", None) \
                or (ex.response.status_code if ex.response is not None else None)
            if status not in (404, 410):
                print(f"  [fail] id={row['id']} {status} {str(ex)[:120]}")
        except Exception as ex:  # 네트워크 등
            print(f"  [fail] id={row['id']} {type(ex).__name__}: {str(ex)[:120]}")

        if status in (200, 201, 202):
            stats["ok"] += 1
        elif status in (404, 410):
            # 만료·해지된 구독 → 테이블에서 정리
            gone = delete_subscription(secret, row["id"])
            print(f"  [expired] id={row['id']} {status} → 삭제 {'완료' if gone else '실패'}")
            stats["expired"] += 1
        else:
            stats["failed"] += 1
    return stats


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="요약·대상 수만 출력하고 발송하지 않음")
    ap.add_argument("--date", help="요약할 날짜 YYYY-MM-DD (기본: 오늘 KST)")
    args = ap.parse_args()

    day = args.date or datetime.now(KST).date().isoformat()
    with open(MENUS_FILE, encoding="utf-8") as f:
        data = json.load(f)

    payload = build_summary(data, day)
    if not payload:
        print(f"{day}: 오늘 메뉴가 없어 발송을 건너뜁니다.")
        return 0

    print(f"[{day}] 발송 내용")
    print("  제목:", payload["title"])
    for ln in payload["body"].split("\n"):
        print("  ", ln)

    secret = os.environ.get("SUPABASE_SECRET_KEY")
    pem = os.environ.get("VAPID_PRIVATE_KEY")

    if args.dry_run:
        if secret:
            subs = fetch_subscriptions(secret)
            print(f"[dry-run] 대상 구독 {len(subs)}건 (발송 안 함)")
        else:
            print("[dry-run] SUPABASE_SECRET_KEY 없음 → 대상 수 조회 생략 (발송 안 함)")
        return 0

    missing = [k for k, v in (("SUPABASE_SECRET_KEY", secret), ("VAPID_PRIVATE_KEY", pem)) if not v]
    if missing:
        print("::error::환경변수 누락: " + ", ".join(missing))
        return 1

    subs = fetch_subscriptions(secret)
    print(f"대상 구독 {len(subs)}건")
    if not subs:
        print("구독이 없어 발송할 곳이 없습니다.")
        return 0
    stats = send_all(subs, payload, pem, secret)
    print(f"결과: 성공 {stats['ok']} / 만료 정리 {stats['expired']} / 실패 {stats['failed']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
