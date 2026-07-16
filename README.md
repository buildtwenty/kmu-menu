# 국민대 오늘의 학식 🍚

국민대학교 학생식당 메뉴를 매일 자동으로 크롤링해 모바일 친화적인 페이지로 보여주는 정적 사이트.

### 🔗 https://buildtwenty.github.io/kmu-menu/

- 식당별 탭 · 날짜 선택 · 현재/다음 끼니 자동 하이라이트
- 칼로리 토글 (메뉴명 키워드 매칭)
- 캘린더로 지난달 메뉴 조회 (아카이브 지연 로딩)
- 빌드 과정 없음 · 백엔드 없음 · 순수 정적 파일

## 동작 방식

```
kmu_crawler.py  →  archive/YYYY-MM.json  →  menus.json  →  index.html
 (학교 페이지)      (월별 전체 이력)         (최근 3주)      (클라이언트 JS)
```

- **크롤러** (`kmu_crawler.py`): 학교 '오늘의 메뉴' 페이지를 긁어 월별 아카이브에 병합하고, 최근 21일치를 `menus.json`으로 재생성. 대부분이 실제 메뉴와 공지·운영시간·알레르기 문구를 분리하는 정규식 필터링이다.
- **뷰어** (`index.html`): 의존성 없는 단일 파일. `menus.json` + `calories.json`만 로드해 렌더링하고, 지난달은 `archive/`를 필요할 때만 가져온다.
- **데이터 스키마** (크롤러 ↔ 프론트 계약):
  ```json
  { "restaurants": [
      { "name": "한울식당(법학관 지하1층)",
        "menus": [ { "date": "YYYY-MM-DD", "corner": "...", "meal": "중식",
                     "items": [ { "name": "제육볶음", "price": 5000 } ] } ] } ] }
  ```

## 자동화

`.github/workflows/crawl.yml` — 매일 **06:00 KST**(21:00 UTC) 크롤러 실행 후 `menus.json`·`archive/`를 봇(`menu-bot`)이 커밋. 커밋 제목 `🍚 메뉴 자동 갱신 <날짜>`이 봇 커밋이다.

- **이상 감지**: 학교 페이지 개편 등으로 새로 긁힌 식당이 3곳 미만이거나 오늘 이후 메뉴가 0건이면 워크플로우를 실패시켜 알림 메일 발송 (낡은/빈 데이터로 덮어쓰지 않음).
- **칼로리 미매칭 이슈**: `calorie_check.py`가 칼로리 키워드에 안 잡히는 메뉴를 찾아 GitHub 이슈로 자동 등록 (`continue-on-error`).
- Actions 탭에서 `workflow_dispatch`로 수동 실행 가능.

## 로컬 개발

```bash
pip install -r requirements.txt   # requests, beautifulsoup4 (CI는 Python 3.12)
python kmu_crawler.py             # 라이브 사이트 크롤 → menus.json 갱신 + 요약 출력

python -m http.server 8000        # 미리보기: http://localhost:8000/index.html
```

> `index.html`이 `menus.json`을 `fetch()`하므로 `file://`로 열면 안 되고 HTTP 서버가 필요하다.
> 파서 수정 시엔 소스 HTML이 정답이므로 실제 크롤로 검증할 것. 크롤러는 오프라인 픽스처가 없다.

## 파일

| 파일 | 역할 |
|---|---|
| `kmu_crawler.py` | 크롤 + 아카이브 병합 + `menus.json` 재생성 |
| `calorie_check.py` | 칼로리 미매칭 메뉴 탐지 (이슈 본문 생성) |
| `migrate_to_archive.py` | (일회성) 구 `menus.json` → 월별 아카이브 이전 |
| `index.html` | 단일 파일 뷰어 (인라인 CSS/JS) |
| `menus.json` / `archive/` | 최근 3주 / 월별 전체 이력 |
| `calories.json` | 메뉴 키워드 → 칼로리 매핑 |

내부 개발 규칙과 파싱 상세는 [`CLAUDE.md`](./CLAUDE.md) 참고.
