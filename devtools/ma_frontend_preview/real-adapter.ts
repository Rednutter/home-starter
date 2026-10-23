/** Local-only named read relay. It never holds HA credentials or forwards MA RPC. */
import { randomUUID } from "node:crypto";
import type { Plugin } from "vite";

const ORIGIN = "http://127.0.0.1:18744";
const BACKEND = "http://127.0.0.1:18743";
const COOKIE = "metadata_preview_context";
const cookie = (req: any) => req.headers.cookie?.split(";").map((s: string) => s.trim()).find((s: string) => s.startsWith(COOKIE + "="))?.slice(COOKIE.length + 1);
const imageId = (path: string) => path.match(/^\/art\/([a-f0-9]{64})$/)?.[1];

function localImages(value: any): any {
  if (Array.isArray(value)) return value.map(localImages);
  if (!value || typeof value !== "object") return value;
  const result = { ...value };
  if (result.metadata?.images) result.metadata = { ...result.metadata, images: result.metadata.images.flatMap((i: any) => imageId(i.path || "") ? [{ ...i, path: ORIGIN + i.path }] : []) };
  for (const key of ["artists", "album", "items"]) if (result[key]) result[key] = localImages(result[key]);
  return result;
}

export function householdRealAdapter(): Plugin {
  const install = (server: any) => { server.middlewares.use(async (req: any, res: any, next: any) => {
    const url = new URL(req.url || "/", ORIGIN);
    const handled = ["/__household/bootstrap", "/__household/read", "/imageproxy"].includes(url.pathname) || url.pathname.startsWith("/art/");
    if (!handled) { next(); return; }
    res.setHeader("Cache-Control", "no-store"); res.setHeader("X-Content-Type-Options", "nosniff");
    if (req.headers.host !== "127.0.0.1:18744" || req.headers.origin && req.headers.origin !== ORIGIN || req.headers["sec-fetch-site"] === "cross-site") { res.statusCode = 403; res.end("Use the local metadata preview."); return; }
    try {
      let context = cookie(req);
      let path: string, body: string | undefined;
      if (url.pathname === "/__household/bootstrap" && req.method === "GET") {
        context = randomUUID(); path = "/bootstrap";
        res.setHeader("Set-Cookie", COOKIE + "=" + context + "; HttpOnly; SameSite=Strict; Path=/; Max-Age=1800");
      } else {
        if (!/^[a-f0-9-]{36}$/.test(context || "")) throw Error("Reopen the metadata preview.");
        if (url.pathname === "/__household/read" && req.method === "POST" && req.headers.origin === ORIGIN && req.headers["content-type"]?.startsWith("application/json")) {
          body = ""; for await (const chunk of req) { body += chunk; if (body.length > 16384) throw Error("Request too large."); }
          const input = JSON.parse(body);
          if (Object.keys(input).some(k => !["profile", "generation", "command", "args"].includes(k))) throw Error("Unsupported read request.");
          path = "/read";
        } else if (req.method === "GET") {
          const candidate = url.pathname === "/imageproxy" ? decodeURIComponent(url.searchParams.get("path") || "").replace(ORIGIN, "") : url.pathname;
          const id = imageId(candidate); if (!id) throw Error("Artwork unavailable."); path = "/art/" + id;
        } else throw Error("Read-only metadata preview.");
      }
      const upstream = await fetch(BACKEND + path, { method: body ? "POST" : "GET", headers: { "X-Preview-Context": context!, ...(body ? { "Content-Type": "application/json" } : {}) }, body, redirect: "error", signal: AbortSignal.timeout(20000) });
      res.statusCode = upstream.status;
      const type = upstream.headers.get("content-type") || "text/plain";
      res.setHeader("Content-Type", type);
      if (type.includes("application/json")) {
        const value = await upstream.json();
        if (value.result !== undefined) value.result = localImages(value.result);
        res.end(JSON.stringify(value));
      } else if (["image/png", "image/jpeg", "image/webp"].includes(type)) {
        const bytes = await upstream.arrayBuffer(); if (bytes.byteLength > 4194304) throw Error("Artwork unavailable."); res.end(Buffer.from(bytes));
      } else res.end("Artwork unavailable.");
    } catch {
      res.statusCode = 503; res.setHeader("Content-Type", "application/json"); res.end(JSON.stringify({ error: "Read-only metadata or artwork is unavailable. Existing household playback is unchanged." }));
    }
  }); };
  return { name: "local-real-metadata-read-only", configureServer: install, configurePreviewServer: install };
}
