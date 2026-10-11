# -*- coding: utf-8 -*-
"""
Supabase keep-alive 핑 (.github/workflows/crawl.yml 에서 매일 실행)

무료 플랜 프로젝트는 일주일쯤 요청이 없으면 자동 일시정지(pause)되고, 그러면 호스트 자체가
안 풀려 아침 푸시 발송(send_push.py)이 통째로 죽는다 — 2026-10-02부터 실제로 겪은 장애.
구독 테이블에 가장 가벼운 조회 하나를 보내 '활동'을 남긴다. 결과는 로그로만 남기고
실패해도 크롤링 워크플로는 막지 않는다 (crawl.yml 쪽 continue-on-error).

환경변수: SUPABASE_SECRET_KEY (GitHub Secrets → env)
"""

import os
import sys

import requests

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from send_push import SUPABASE_URL, sb_headers  # noqa: E402  (URL을 한 곳에만 둔다)


def main() -> int:
    secret = os.environ.get("SUPABASE_SECRET_KEY")
    if not secret:
        print("::warning::SUPABASE_SECRET_KEY 없음 → keep-alive 생략")
        return 0
    try:
        resp = requests.get(
            f"{SUPABASE_URL}/rest/v1/subscriptions",
            params={"select": "id", "limit": 1},
            headers=sb_headers(secret), timeout=20,
        )
    except requests.RequestException as ex:
        print(f"::warning::Supabase keep-alive 실패: {type(ex).__name__} "
              "— 프로젝트가 일시정지됐는지 대시보드에서 확인")
        return 1
    if resp.status_code != 200:
        print(f"::warning::Supabase keep-alive HTTP {resp.status_code}: {resp.text[:120]}")
        return 1
    print("Supabase keep-alive OK (HTTP 200)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
