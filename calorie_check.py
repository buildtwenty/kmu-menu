# -*- coding: utf-8 -*-
"""
menus.json의 '오늘(KST) 이후' 메뉴 중 calories.json에 매칭되지 않는 항목을 찾는다.
- 결과 목록을 unmatched.md(이슈 본문용)로 저장
- 미매칭 고유 개수를 stdout으로 출력 (워크플로우에서 분기용)
매칭 규칙은 index.html과 동일: 메뉴명에 키워드가 포함되면 매칭.
"""

import datetime
import json

MENUS_FILE = "menus.json"
CAL_FILE = "calories.json"
OUT_FILE = "unmatched.md"


def load_keywords():
    cal = json.load(open(CAL_FILE, encoding="utf-8"))
    return [k for k in cal if not k.startswith("_")]


def is_matched(name, keywords):
    return any(k in name for k in keywords)


def main():
    keywords = load_keywords()
    data = json.load(open(MENUS_FILE, encoding="utf-8"))

    # GitHub Actions는 UTC로 도는데 menus.json 날짜는 KST 기준이므로 KST 오늘을 계산
    today = (datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=9)).date().isoformat()

    unmatched = {}  # 메뉴명 -> {날짜들}
    for r in data.get("restaurants", []):
        for m in r.get("menus", []):
            if m["date"] < today:      # 오늘 이후(오늘 포함)만 검사
                continue
            for item in m["items"]:
                name = item["name"]
                if not is_matched(name, keywords):
                    unmatched.setdefault(name, set()).add(m["date"])

    names = sorted(unmatched)
    with open(OUT_FILE, "w", encoding="utf-8") as f:
        if names:
            f.write("크롤링된 **오늘 이후** 메뉴 중 `calories.json`에 매칭되지 않은 항목입니다.\n")
            f.write("키워드를 추가하거나 메뉴명 오탈자를 확인해 주세요.\n\n")
            for n in names:
                dates = ", ".join(sorted(unmatched[n]))
                f.write(f"- `{n}` ({dates})\n")
            f.write(f"\n_자동 생성 · 기준일 {today}_\n")

    print(len(names))


if __name__ == "__main__":
    main()
