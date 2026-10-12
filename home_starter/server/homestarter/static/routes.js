// Ingress-safe URL and navigation helpers (no DOM rendering; unit tested).
//
// The page is served under /api/hassio_ingress/<token>/ and the server sets a
// <base href> for that prefix, so every API URL is built relative to
// document.baseURI and never assumes the app is mounted at "/".

export const NAVIGATE_MESSAGE = "home-assistant/navigate";
export const FALLBACK_DELAY_MS = 1500;

/** Resolve an app-relative path ("api/scan") against the page base. */
export function apiUrl(path, baseURI) {
  const rel = String(path).replace(/^\/+/, "");
  return new URL(rel, baseURI).toString();
}

/** Same-origin absolute HA frontend path only (mirrors navigation.is_safe_ha_path). */
export function isSafeHaPath(path) {
  if (typeof path !== "string" || !path.startsWith("/") || path.startsWith("//")) return false;
  if (path.includes("\\") || /[\u0000-\u001f]/.test(path)) return false;
  return !path.split("?", 1)[0].includes(":");
}

function topNavigate(win, path) {
  try {
    win.top.location.assign(path);
    return "top";
  } catch (_err) {
    win.open(path, "_top");
    return "open";
  }
}

/**
 * Navigate the Home Assistant frontend to `path`.
 *
 * Inside the ingress iframe, Home Assistant's app panel listens for
 * {type: "home-assistant/navigate", path} messages from its iframe and routes
 * inside the SPA (frontend src/panels/app/ha-panel-app.ts). When HA handles
 * it, this iframe is torn down and the fallback timer never fires. If nothing
 * happens (older frontend), fall back to a top-level navigation to the same
 * same-origin path.
 */
export function navigateHA(path, env = {}) {
  const win = env.win ?? globalThis.window;
  const schedule = env.setTimeout ?? globalThis.setTimeout;
  const delay = env.fallbackDelay ?? FALLBACK_DELAY_MS;
  if (!isSafeHaPath(path)) return "blocked";
  const framed = win.parent && win.parent !== win;
  if (framed) {
    try {
      win.parent.postMessage({ type: NAVIGATE_MESSAGE, path }, win.location.origin);
    } catch (_err) {
      return topNavigate(win, path);
    }
    schedule(() => topNavigate(win, path), delay);
    return "message";
  }
  return topNavigate(win, path);
}
