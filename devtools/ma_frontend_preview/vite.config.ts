import { defineConfig } from "vite";
import vue from "@vitejs/plugin-vue";
import vuetify, { transformAssetUrls } from "vite-plugin-vuetify";
import VueI18nPlugin from "@intlify/unplugin-vue-i18n/vite";
import tailwindcss from "@tailwindcss/vite";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { householdFixtureAdapter } from "./server-adapter";
import { householdRealAdapter } from "./real-adapter";

const here = path.dirname(fileURLToPath(import.meta.url));
const upstream = path.dirname(here);
export default defineConfig(({ mode }) => ({
  root: here,
  base: "./",
  resolve: { alias: { "@": path.join(upstream, "src") } },
  define: { "process.env": {} },
  plugins: [
    vue({ template: { transformAssetUrls } }), tailwindcss(),
    vuetify({ autoImport: true, styles: { configFile: path.join(upstream, "src/styles/settings.scss") } }),
    VueI18nPlugin({ include: [path.join(upstream, "src/translations/**")] }),
    { name: "no-preview-service-worker", resolveId(id) { if (id === "virtual:pwa-register/vue") return "\0preview-no-sw"; }, load(id) { if (id === "\0preview-no-sw") return 'import {ref} from "vue"; export function useRegisterSW(){return {offlineReady:ref(false),needRefresh:ref(false),updateServiceWorker:async()=>{throw Error("Service workers are disabled in this preview.")}}}'; } },
    mode === "real-readonly" ? householdRealAdapter() : householdFixtureAdapter(),
  ],
  server: { host: "127.0.0.1", port: 18741, strictPort: true, fs: { allow: [upstream] } },
  preview: { host: "127.0.0.1", port: mode === "real-readonly" ? 18744 : 18742, strictPort: true },
  build: { outDir: path.join(upstream, mode === "household-release" ? "household-release-dist" : mode === "real-readonly" ? "household-real-preview-dist" : "household-preview-dist"), emptyOutDir: mode === "household-release", assetsInlineLimit: mode === "household-release" ? 0 : 4096 },
}));
