// Frontend routing helpers: ingress-relative API URLs and HA navigation.
// Run with: node --test tests/js/
import { test } from "node:test";
import assert from "node:assert/strict";
import { apiUrl, isSafeHaPath, navigateHA, NAVIGATE_MESSAGE } from "../../home_starter/server/homestarter/static/routes.js";

const INGRESS = "https://ha.example:8123/api/hassio_ingress/Xk3mN8pQ2rT5vW9yB1dF4hJ7lN0pS3uW6zA9cE2g/";

test("API URLs stay under the ingress prefix", () => {
  assert.equal(apiUrl("api/scan", INGRESS), INGRESS + "api/scan");
  assert.equal(apiUrl("/api/music", INGRESS), INGRESS + "api/music"); // leading slash can't escape the prefix
  assert.equal(apiUrl("api/scan?refresh=1", INGRESS), INGRESS + "api/scan?refresh=1");
  assert.equal(apiUrl("api/music/setup", "http://127.0.0.1:8099/"), "http://127.0.0.1:8099/api/music/setup");
});

test("safe HA paths", () => {
  assert.ok(isSafeHaPath("/app/d5369777_music_assistant"));
  assert.ok(isSafeHaPath("/_my_redirect/supervisor_addon?addon=x&repository_url=https%3A%2F%2Fgithub.com"));
  for (const bad of ["//evil.example", "https://evil.example", "javascript:alert(1)", "/\\evil", "app/x", "/x\nY", "/javascript:x", null, 42]) {
    assert.equal(isSafeHaPath(bad), false, String(bad));
  }
});

function fakeWindow({ framed = true, throwsOnPost = false } = {}) {
  const calls = { posted: [], assigned: [], opened: [] };
  const top = { location: { assign: (p) => calls.assigned.push(p) } };
  const win = {
    location: { origin: "https://ha.example:8123" },
    top,
    open: (p, target) => calls.opened.push([p, target]),
  };
  win.parent = framed
    ? { postMessage: (msg, origin) => { if (throwsOnPost) throw new Error("x"); calls.posted.push([msg, origin]); } }
    : win;
  return { win, calls };
}

test("inside the ingress iframe it asks Home Assistant to navigate (same-origin message)", () => {
  const { win, calls } = fakeWindow();
  const timers = [];
  const result = navigateHA("/app/d5369777_music_assistant", { win, setTimeout: (fn, ms) => timers.push([fn, ms]) });
  assert.equal(result, "message");
  assert.deepEqual(calls.posted, [[{ type: NAVIGATE_MESSAGE, path: "/app/d5369777_music_assistant" }, "https://ha.example:8123"]]);
  assert.equal(calls.assigned.length, 0);
  assert.equal(timers.length, 1);
});

test("falls back to top-level navigation if HA didn't take over", () => {
  const { win, calls } = fakeWindow();
  const timers = [];
  navigateHA("/app/d5369777_music_assistant", { win, setTimeout: (fn, ms) => timers.push([fn, ms]), fallbackDelay: 10 });
  timers[0][0](); // HA did not tear the iframe down -> fallback fires
  assert.deepEqual(calls.assigned, ["/app/d5369777_music_assistant"]);
  assert.equal(timers[0][1], 10);
});

test("outside a frame it navigates the window directly", () => {
  const { win, calls } = fakeWindow({ framed: false });
  assert.equal(navigateHA("/config/integrations/dashboard", { win }), "top");
  assert.deepEqual(calls.assigned, ["/config/integrations/dashboard"]);
  assert.equal(calls.posted.length, 0);
});

test("cross-origin top falls back to window.open(_top)", () => {
  const { win, calls } = fakeWindow({ framed: false });
  win.top = { get location() { throw new Error("cross-origin"); } };
  assert.equal(navigateHA("/app/x", { win }), "open");
  assert.deepEqual(calls.opened, [["/app/x", "_top"]]);
});

test("unsafe paths are refused", () => {
  const { win, calls } = fakeWindow();
  assert.equal(navigateHA("https://evil.example/", { win, setTimeout: () => {} }), "blocked");
  assert.equal(navigateHA("//evil.example/", { win, setTimeout: () => {} }), "blocked");
  assert.equal(calls.posted.length + calls.assigned.length, 0);
});

test("postMessage failure navigates directly", () => {
  const { win, calls } = fakeWindow({ throwsOnPost: true });
  assert.equal(navigateHA("/app/x", { win, setTimeout: () => {} }), "top");
  assert.deepEqual(calls.assigned, ["/app/x"]);
});
