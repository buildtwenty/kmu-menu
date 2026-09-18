-- 웹 푸시 구독 설정(식당·키워드) 저장용 RLS — Supabase SQL Editor에서 1회 실행
--
-- 상황: subscriptions 테이블은 anon(publishable key)이 insert만 가능. 알림 설정 시트가
-- 자기 행의 restaurants / keywords 를 바꾸려면 update 정책이 필요하다.
-- 본인 판별: 클라이언트는 자기 endpoint(추측 불가능한 푸시 URL)를 요청 헤더 X-Endpoint 에
-- 담아 보내고(index.html updatePrefsOnServer), 정책은 그 헤더와 endpoint 컬럼이 같은 행만 허용한다.
-- → 한 요청에 한 endpoint만 열리므로 "?id=gt.0" 같은 일괄 갱신은 0행이 된다.
-- 컬럼 권한으로 restaurants, keywords 두 컬럼만 바꿀 수 있게 하고 endpoint/keys는 못 건드린다.
-- delete 정책은 두지 않는다: 해제는 브라우저 구독 해지 → 다음 발송 410 → send_push.py가 정리.

-- 1) anon의 update 권한을 두 컬럼으로 한정 (Supabase 기본은 테이블 전체 update 권한)
revoke update on table public.subscriptions from anon;
grant  update (restaurants, keywords) on table public.subscriptions to anon;

-- 2) 자기 행(endpoint = X-Endpoint 헤더)만 update 허용
--    request.headers 의 키는 소문자(x-endpoint)로 들어온다.
drop policy if exists "anon_update_own_prefs_by_endpoint" on public.subscriptions;
create policy "anon_update_own_prefs_by_endpoint"
  on public.subscriptions
  for update
  to anon
  using      (endpoint = (current_setting('request.headers', true)::json ->> 'x-endpoint'))
  with check (endpoint = (current_setting('request.headers', true)::json ->> 'x-endpoint'));

-- 확인 (실행 후):
--   select policyname, cmd, roles from pg_policies where tablename = 'subscriptions';
--   select privilege_type, column_name from information_schema.column_privileges
--    where table_name = 'subscriptions' and grantee = 'anon' and privilege_type = 'UPDATE';
--   → UPDATE 가 restaurants, keywords 두 컬럼에만 있어야 한다.
