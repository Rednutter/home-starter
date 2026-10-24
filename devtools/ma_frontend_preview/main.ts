import { createApp } from "vue";
import api, { ConnectionState } from "@/plugins/api";
import router, { routes } from "@/plugins/router";
import { store } from "@/plugins/store";
import { registerPlugins } from "@/plugins";
import vuetify from "@/plugins/vuetify";
import "@/styles/global.css";
import "@fontsource/roboto/400.css";
import "@fontsource/roboto/500.css";
import "@fontsource/roboto/700.css";
import "./preview.css";
import "./native-theme.css";
import Shell from "./Shell.vue";
import Shelves from "./Shelves.vue";
import PlaylistSharing from "./PlaylistSharing.vue";
import Discovery from "./Discovery.vue";
import { connectHousehold, currentMedia } from "./household";
import HouseholdShelf from './HouseholdShelf.vue';
import { profile, generation, readStatus, viewPreferences, readFailures, realMode, releaseMode, people, previewNotes, booting } from "./context";

const previewBase = new URL('.', document.baseURI);
const endpoint = (name: string) => releaseMode ? new URL(name, previewBase).href : '/__household/' + name;

// The browser never initializes a native MA transport. Its models come from the
// named household read projection; native control/admin RPC is never forwarded.
api.sendCommand = async function <T>(command: string, args?: Record<string, unknown>): Promise<T> {
  // Native list/search preferences stay only in this preview tab's memory.
  // This is not a user-management proxy or a persistent household write.
  if (command === "auth/user/update" && args?.user_id === "fictional-" + profile.value
      && Object.keys(args).every(key => ["user_id", "preferences"].includes(key))
      && args.preferences && typeof args.preferences === "object"
      && Object.keys(args.preferences).every(key => key.startsWith("itemsListing."))) {
    viewPreferences[profile.value] = JSON.parse(JSON.stringify(args.preferences)) as Record<string, unknown>;
    return { ...store.currentUser, preferences: viewPreferences[profile.value] } as T;
  }
  const selected = profile.value, version = generation.value;
  const readOnly = /^(music\/[^/]+\/(library_items|count|get_[a-z_]+|artist_[a-z_]+|album_[a-z_]+|playlist_tracks|top_[a-z_]+|similar_artists|genres_for_media_item|genre_exclusions_for_media_item)|config\/core\/get_value|household\/(favourites|recent|shelves))$/.test(command);
  const unavailable = () => (command.endsWith("/count") ? undefined : command.includes("/get_") ? null : []) as T;
  try {
    const response = await fetch(endpoint('read'), { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ profile: selected, command, args, ...(realMode ? {generation:version}: {}) }), signal: AbortSignal.timeout(8000) });
    const body = await response.json();
    if (selected !== profile.value || version !== generation.value) return unavailable();
    if (!response.ok) throw Error(body.error || "Example catalogue unavailable.");
    readFailures.delete(command); readStatus.value = [...readFailures.values()][0] || "";
    if(releaseMode && body.result?.household_selection && command.includes('/get_'))currentMedia.value=body.result;
    return body.result as T;
  } catch (error) {
    if (selected !== profile.value || version !== generation.value) return unavailable();
    const message = error instanceof Error && error.name !== "TimeoutError" ? error.message : "Example catalogue took too long. Try another collection.";
    readFailures.set(command, message); readStatus.value = message;
    if (!readOnly) throw error;
    // Native views may fire count reads without awaiting them. Unknown counts
    // stay undefined; failed lists are empty WITH the visible unavailable state.
    return unavailable();
  }
};
api.state.value = ConnectionState.INITIALIZED;
api.baseUrl = releaseMode ? previewBase.href.replace(/\/$/, '') : window.location.origin;
api.providers["example-a"] = { instance_id: "example-a", domain: "fictional", name: "Example source A", type: "music", available: true, is_streaming_provider: false, supported_features: ["library_artists", "library_albums", "library_tracks", "library_playlists"], unique: false } as any;
api.providers["example-b"] = { ...api.providers["example-a"], instance_id: "example-b", name: "Example source B" };
api.providerManifests["fictional"] = { domain: "fictional", name: "Example source", type: "music", multi_instance: true, supported_features: [] } as any;
store.apiInitialized = true;
store.currentUser = { user_id: "fictional-house", username: "fictional-house", role: "user", enabled: true, created_at: "", display_name: "Fictional preview", avatar_url: null, preferences: {}, provider_filter: [], player_filter: [] } as any;
// Preserve upstream route records/components/props and the SAME router used by
// native Back/detail helpers. Exclude upstream layouts/settings/auth/players.
const keep: any[] = [];
function select(records: any[]) { for (const record of records) { if (["/artists", "/albums", "/playlists", "/tracks"].includes(record.path)) keep.push(record); else if (record.children) select(record.children); } }
select(routes);
router.clearRoutes();
for (const route of keep) router.addRoute(route);
router.addRoute({ path: "/favourites", component: Shelves, props: { shelf: "favourites" } });
router.addRoute({ path: "/recent", component: Shelves, props: { shelf: "recent" } });
if(!releaseMode)router.addRoute({ path: "/playlist-sharing", component: PlaylistSharing });
router.addRoute({ path: "/discover-radio", component: Discovery, props: {category:"radio"} });
router.addRoute({ path: "/find-podcasts", component: Discovery, props: {category:"podcast"} });
if(releaseMode)for(const [path,kind] of [['/episodes','episodes'],['/ambient','ambient'],['/audiobooks','books']])router.addRoute({path,component:HouseholdShelf,props:{kind}});
router.addRoute({ path: "/", redirect: "/artists" });
router.addRoute({ path: "/:pathMatch(.*)*", redirect: "/artists" });
async function start() {
  // Pinned light/dark palettes are packaged as an external stylesheet. The
  // read-only trial has no theme editor, so it needs no injected style element.
  // Leave upstream code unchanged and preserve script/style-src 'self'.
  if (releaseMode) vuetify.theme.install = () => {};
  if (realMode) {
    people.value = [];
    for (const key of Object.keys(api.providers)) delete api.providers[key];
  }
  // Mount the usable navigation shell before network/catalogue work. Routes
  // remain gated until the authority/profile bootstrap has succeeded.
  const app = createApp(Shell); registerPlugins(app); app.mount("#app");
  if (realMode) {
    try {
      const response = await fetch(endpoint('bootstrap'), { cache:"no-store", signal:AbortSignal.timeout(releaseMode ? 65000 : 10000) });
      if (!response.ok) throw Error("Real metadata bridge unavailable.");
      const bootstrap = await response.json();
      people.value = bootstrap.profiles; previewNotes.value = bootstrap.notes;
      for (const provider of bootstrap.providers) api.providers[provider.instance_id] = provider;
      if(releaseMode && bootstrap.surface)void connectHousehold(bootstrap.surface);
    } catch { previewNotes.value = "Media sources are unavailable. Reload to reconnect; no playback was changed."; }
    finally { booting.value = false; }
  }
}
void start();

// UI affordance plus server denial. Keyboard/unknown native writes still hit
// the rejecting read-only adapter; there is no arbitrary native command proxy.
const disable = () => document.querySelectorAll<HTMLButtonElement>("#playbutton button, button[title*='favorite'], button[title*='Favorite'], button[title*='favourite'], .native-library .ed-card button").forEach(button => { if (!button.disabled) { button.disabled = true; button.title = "Read-only preview - playback and edits unavailable"; } });
new MutationObserver(disable).observe(document.body, { childList: true, subtree: true, attributes:true, attributeFilter:['disabled'] });
document.addEventListener('contextmenu',event=>{if(event.target instanceof Element && event.target.closest('.native-library .ed-card')){event.preventDefault();event.stopImmediatePropagation();}},true);
disable();

// Keep native source untouched. Failed artwork has a quiet, accessible fallback
// within this isolated shell; it never substitutes invented artist imagery.
document.addEventListener("error", (event) => {
  const image = event.target;
  if (!(image instanceof HTMLImageElement) || !image.closest(".native-library .ed-card__art")) return;
  image.hidden = true;
  const parent = image.parentElement!;
  if (parent.querySelector(".household-art-fallback")) return;
  const fallback = document.createElement("span");
  fallback.className = "household-art-fallback";
  fallback.setAttribute("role", "img");
  fallback.setAttribute("aria-label", "Artwork unavailable");
  fallback.textContent = "♪";
  parent.append(fallback);
}, true);
