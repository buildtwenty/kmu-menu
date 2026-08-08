---
description: 칼로리 미매칭 이슈를 표준 루틴대로 처리 (키워드 추가 → 회귀 확인 → 코멘트·close → push)
argument-hint: [이슈번호]
---

`calorie_check.py`가 자동 생성한 **칼로리 미매칭 메뉴** 이슈 #$1 을 아래 루틴대로 처리한다.
($1 이 비어 있으면 `gh issue list --search "칼로리 미매칭 in:title" --state open` 으로 찾아서 확인 후 진행)

## 0. 준비

```bash
git pull --rebase
gh issue view $1 --comments   # 본문 + 이후 코멘트(날짜별 갱신본)를 모두 본다
python3 calorie_check.py      # 로컬 최신 상태의 미매칭 개수
```

이슈 **본문 + 모든 코멘트의 합집합**을 처리 대상으로 삼는다. `calorie_check.py`는 "오늘 이후"만
검사하므로, 이미 지나간 날짜의 항목은 로컬 실행에서 안 잡히지만 같은 메뉴가 다시 나오면 또 걸린다.

각 항목이 어느 식당/코너/가격인지 먼저 확인한다 (메뉴인지 노이즈인지 판단 근거):

```bash
python3 - <<'EOF'
import json, glob
names = ["<항목1>", "<항목2>"]          # 이슈에서 뽑은 이름(부분 문자열)
for f in ["menus.json"] + sorted(glob.glob("archive/*.json")):
    d = json.load(open(f, encoding="utf-8"))
    for r in d["restaurants"]:
        for m in r["menus"]:
            for it in m["items"]:
                if any(n in it["name"] for n in names):
                    print(f, r["name"], m["date"], m.get("corner"), m.get("meal"), it["name"], it["price"], sep=" | ")
EOF
```

## 1. 매칭 규칙 (이걸 모르면 잘못된 키워드를 넣게 된다)

`index.html`의 `matchCalorie()` = **토큰 단위 매칭**:
공백과 `/`로 토큰을 자르고, **키워드가 걸리는 첫 토큰**을 메인 요리로 보고
그 토큰 안에서 **가장 긴 키워드**를 고른다. (전역 최장일치가 아니다 —
세트 끝의 `그린샐러드` 같은 긴 사이드 키워드가 메인을 가리는 걸 막으려는 설계)

따라서 새 키워드를 넣기 전에 항상 두 가지를 본다:
- **같은 토큰 안 잠식**: 더 짧은 새 키워드가 기존의 더 정확한 키워드를 이기지는 않는지,
  반대로 새 키워드가 기존 항목의 범위를 엉뚱하게 낮추지는 않는지
  (예: `장터국`만 넣으면 `소고기장터국밥`이 국밥 600–800 → 250–450으로 내려감
  → `장터국밥`을 함께 넣어 방어)
- **앞 토큰 가로채기**: 사이드에만 쓰이는 단어를 넣으면 메인보다 앞 토큰에서 걸려 메뉴 전체를
  사이드 칼로리로 표시함 (예: `요구르트`, `옥수수`, `콩나물국`은 이래서 **넣지 않음**)

## 2. 항목별 판단 원칙

1. **실제 음식** → `calories.json`에 보수적 범위 `[min, max]` 추가.
   비슷한 기존 항목의 범위와 톤을 맞춘다 (예: `북어` = 기존 `황태` [200,400],
   `배추국` = 기존 `무국`/`아욱국` [150,350]).
   중복·충돌·잠식 확인 후, **순손해면 넣지 말고 사유를 기록**한다 (베이컨 제외 사례).
   substring 충돌도 본다 (예: `커리`는 `치커리겉절이`와 충돌 → `커리라이스`로 한정).
2. **원본 오타 의심** → 오타 키워드는 넣지 말고 부분 매칭으로 커버되는지 본다
   (`물냉`, `제비` 방식). 커버되면 **오매칭 검사 필수**.
3. **메뉴가 아닌 것**(공휴일·안내문·옵션 표기 등) → 칼로리가 아니라 **크롤러 필터 문제**.
   `kmu_crawler.py`의 `NOTICE_PAT` / `HOLIDAY_PAT` 등을 보강하고 기존 메뉴 회귀 확인.
   필터를 추가했으면 **저장된 데이터의 해당 노이즈도 일회성 정리**(세트 규칙 — 이슈 #2 전례).
4. **판단이 애매하면 임의로 정하지 말고 사용자에게 묻는다.**

## 3. 회귀 확인 (키워드를 건드렸으면 필수)

저장된 모든 고유 메뉴명에 대해 `index.html`과 동일한 토큰 매칭으로 전/후를 비교한다.

```bash
git stash -q && cp calories.json /tmp/cal_old.json && git stash pop -q
python3 - <<'EOF'
import json, glob, re
old = json.load(open("/tmp/cal_old.json", encoding="utf-8"))
new = json.load(open("calories.json", encoding="utf-8"))

def match(name, cal):                      # index.html matchCalorie()와 동일 규칙
    for tok in re.split(r"[\s/]+", name):
        best = None
        for k in cal:
            if k[0] == "_":
                continue
            if k in tok and (best is None or len(k) > len(best)):
                best = k
        if best:
            return best, tuple(cal[best])
    return None, None

items = {}
for f in ["menus.json"] + sorted(glob.glob("archive/*.json")):
    d = json.load(open(f, encoding="utf-8"))
    for r in d["restaurants"]:
        for m in r["menus"]:
            for it in m["items"]:
                items.setdefault(it["name"], m["date"])
print("총 고유 메뉴명:", len(items))
newly, chg = [], []
for n in sorted(items):
    ko, vo = match(n, old)
    kn, vn = match(n, new)
    if (ko, vo) == (kn, vn):
        continue
    (newly if ko is None else chg).append((n, ko, vo, kn, vn))
print(f"\n=== 새로 매칭 {len(newly)}건 ===")
for n, ko, vo, kn, vn in newly:
    print(f"  + [{kn}] {list(vn)}  <- {n}")
print(f"\n=== 기존 매칭 변경 {len(chg)}건 ===")
for n, ko, vo, kn, vn in chg:
    print(f"  ~ [{ko}]{list(vo)} -> [{kn}]{list(vn)}   {n}")
EOF
```

판정 기준: 새로 매칭된 항목이 이슈 목록을 모두 덮는지, **기존 매칭 변경은 전부
"사이드 → 메인 요리" 방향의 개선**인지. 나빠진 게 하나라도 있으면 키워드를 다시 손본다.

## 4. 마무리

```bash
python3 -c "import json; json.load(open('calories.json')); print('json ok')"
python3 calorie_check.py      # 0 이어야 함
```

- 커밋: 추가한 키워드 + **넣지 않기로 한 것과 그 사유** + 회귀 결과를 메시지에 남긴다.
- push 후 이슈에 처리 내역 코멘트(키워드 표 / 판단 근거 / 회귀 결과) → `gh issue close $1 -r completed`.
- **크롤러(`kmu_crawler.py`)를 건드렸으면** Actions 재실행이 필요한지 사용자에게 알린다.
  `calories.json`만 고쳤다면 프론트가 직접 fetch하므로 push 즉시 반영 — 재실행 불필요.
- 새로 알게 된 판단(넣지 않은 키워드의 사유 등)이 재발할 성격이면 `CLAUDE.md` 로드맵
  조건부 항목이나 이 파일에 반영한다.
