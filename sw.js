/* 국민대 학식 — 웹 푸시 서비스 워커
   역할은 두 가지뿐: push 이벤트로 알림을 띄우고, 알림을 누르면 사이트를 연다.
   메뉴는 항상 최신을 받아야 하므로 fetch 캐싱은 하지 않는다.
   경로는 프로젝트 페이지(/kmu-menu/) 기준. */
const SITE_PATH = "/kmu-menu/";
const ICON = SITE_PATH + "icons/icon-192.png";

self.addEventListener("install", () => self.skipWaiting());
self.addEventListener("activate", event => event.waitUntil(self.clients.claim()));

// 발송 스크립트(scripts/send_push.py)가 보내는 JSON: {title, body, url?, tag?}
self.addEventListener("push", event => {
  let data = {};
  if (event.data) {
    try { data = event.data.json(); }
    catch (e) { data = { body: event.data.text() }; }
  }
  const title = data.title || "🍚 오늘의 학식";
  const options = {
    body: data.body || "오늘 메뉴가 올라왔어요",
    icon: data.icon || ICON,
    tag: data.tag || "kmu-menu-daily",   // 같은 tag면 이전 알림을 교체 (중복 발송 대비)
    renotify: false,
    data: { url: data.url || SITE_PATH },
  };
  event.waitUntil(self.registration.showNotification(title, options));
});

// 알림 클릭: 이미 열린 사이트 탭이 있으면 포커스, 없으면 새로 연다
self.addEventListener("notificationclick", event => {
  event.notification.close();
  const target = new URL((event.notification.data && event.notification.data.url) || SITE_PATH,
                         self.location.origin).href;
  event.waitUntil(
    self.clients.matchAll({ type: "window", includeUncontrolled: true }).then(list => {
      for (const c of list) {
        if (c.url.startsWith(self.location.origin + SITE_PATH) && "focus" in c) {
          return c.focus();
        }
      }
      return self.clients.openWindow(target);
    })
  );
});
