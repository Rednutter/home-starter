/** Fictional, read-only server projection. No upstream address, credential or proxy. */
import type { Plugin } from "vite";

export const profiles = ["house", "alex", "sam", "casey", "jamie", "riley"];
const colours = ["#df8457", "#8e9cbb", "#7a947a", "#c5a166", "#b07c91", "#728da2"];
const make = (type: string, id: string, name: string, colour: number) => ({
  item_id: id, provider: "library", name, sort_name: name, version: "", uri: `library://${type}/${id}`,
  media_type: type, household_category: "music", is_playable: true, available: true, favorite: true, external_ids: [],
  provider_mappings: [{ item_id: id, provider_domain: "fictional", provider_instance: "example-a", available: true, in_library: true, audio_format: { content_type: "unknown", sample_rate: 0, bit_depth: 0, channels: 2 }, url: null }],
  metadata: { description: "Fictional catalogue artwork and metadata for a read-only component preview.", genres: ["Alternative"], images: [{ type: "thumb", path: `http://127.0.0.1:18741/art/${colour}.svg`, provider: "builtin", remotely_accessible: true }], links: [] },
});
const artists = ["Harbour Lines", "Quiet Geometry", "Sunday Atlas", "Amber District", "The Long Way", "Paper Satellites"].map((name, i) => ({ ...make("artist", "a" + i, name, i), artist_type: "singer" }));
const albums = ["Soft Edges", "After the Rain", "Morning Signals", "Open Windows", "Somewhere Near", "Small Hours"].map((name, i) => ({ ...make("album", "b" + i, name, i), artists: [artists[i]], album_type: "album", year: 2025 }));
const tracks = artists.flatMap((artist, i) => ["A Little Further", "Something Like Home", "Daybreak"].map((name, j) => ({ ...make("track", `t${i}-${j}`, name, i), artists: [artist], album: albums[i], duration: 180 + j * 30, disc_number: 1, track_number: j + 1, position: j + 1 })));
const playlists = ["Weekend favourites", "A quieter morning", "The long drive", "Weekend favourites"].map((name, i) => ({ ...make("playlist", "p" + i, name, i), owner: "Example household", is_editable: false, cache_checksum: "preview" }));
// Explicit app ownership/visibility, never inferred from a provider account.
const access: Record<string, number[]> = { house: [0, 1, 2, 3], alex: [0, 4], sam: [1, 5], casey: [2], jamie: [3], riley: [4] };
const playlistAccess: Record<string, string[]> = { house: ["p0", "p1", "p2"], alex: ["p0", "p3"], sam: ["p1"], casey: ["p2"], jamie: [], riley: [] };

export function musicShelf(profile: string, rows: any[]) {
  return profile === "house" ? rows.filter(r => r.household_category === "music" && ["track", "artist", "playlist"].includes(r.media_type)) : rows;
}
export function combineExact(rows: any[]) {
  const combined = new Map<string, any>();
  for (const row of rows) {
    const previous = combined.get(row.uri);
    if (!previous) combined.set(row.uri, { ...row, provider_mappings: [...row.provider_mappings] });
    else previous.provider_mappings = [...new Map([...previous.provider_mappings, ...row.provider_mappings].map(m => [m.provider_instance + ":" + m.item_id, m])).values()];
  }
  return [...combined.values()];
}

export function project(profile: string, command: string, args: Record<string, any> = {}) {
  if (!profiles.includes(profile)) throw Error("Choose an available example profile.");
  if (command === "household/discovery") return {items:[],sources:[{source:"Fictional preview",state:"search-needed"}],note:"Real discovery is available only in the separate read-only metadata preview. No stations or shows have been invented."};
  if (command === "config/core/get_value" && args.domain === "player_queues" && /^default_click_action_(artist|album|playlist|track)$/.test(String(args.key))) return "details";
  const ids = access[profile];
  const visible = { artists: artists.filter((_, i) => ids.includes(i)), albums: albums.filter((_, i) => ids.includes(i)), tracks: tracks.filter(t => ids.includes(Number(t.artists[0].item_id.slice(1)))), playlists: playlists.filter(p => playlistAccess[profile].includes(p.item_id)) };
  if (["music/genres/genre_exclusions_for_media_item", "music/genres/genres_for_media_item"].includes(command)) {
    if (!Object.values(visible).flat().some(r => r.media_type === args.media_type && r.item_id === args.media_id)) throw Error("Item unavailable for this profile.");
    return [];
  }
  if (command === "household/shelves") return { profile, media: "music-only", source_state: "Fictional sources A and B combined by exact identity", playlists: visible.playlists };
  if (command === "household/favourites") return musicShelf(profile, [...visible.playlists, ...visible.artists.slice(0, 2), ...visible.tracks.slice(0, 2)]);
  // Explicit fictional per-profile history; not inferred from a provider's library.
  if (command === "household/recent") return musicShelf(profile, [...visible.tracks.slice(-2).reverse(), ...visible.playlists.slice(0, 1)]);
  const parts = command.split("/");
  const rows = visible[parts[1] as keyof typeof visible];
  if (command === "music/genres/library_items") return [];
  if (!rows || parts[0] !== "music") throw Error("Read-only preview: this operation is unavailable.");
  if (parts[2] === "count") return rows.length;
  if (parts[2] === "library_items") {
    // Two fictional source pages overlap by canonical upstream identity.
    const sourceA = rows.filter((_, i) => i % 2 === 0);
    const sourceB = [...rows.filter((_, i) => i % 2 === 1), ...rows.slice(0, 1)].map(r => ({ ...r, provider_mappings: r.provider_mappings.map(m => ({ ...m, provider_instance: "example-b" })) }));
    const unique = combineExact([...sourceA, ...sourceB]).sort((a, b) => rows.findIndex(r => r.uri === a.uri) - rows.findIndex(r => r.uri === b.uri));
    const filtered = unique.filter(r => !args.search || r.name.toLowerCase().includes(String(args.search).toLowerCase()));
    return filtered.slice(Number(args.offset) || 0, (Number(args.offset) || 0) + Math.min(Number(args.limit) || 100, 500));
  }
  if (["get_artist", "get_album", "get_track", "get_playlist"].includes(parts[2])) {
    const item = rows.find(r => r.item_id === args.item_id); if (!item) throw Error("This item is not in the selected profile's collection."); return item;
  }
  const artist = visible.artists.find(a => a.item_id === args.item_id);
  if (parts[1] === "artists" && ["artist_albums", "top_albums", "artist_tracks", "top_tracks", "similar_artists"].includes(parts[2])) {
    if (!artist) throw Error("This artist is not in the selected profile's collection.");
    if (parts[2] === "similar_artists") return [];
    return (parts[2].includes("albums") ? visible.albums : visible.tracks).filter(row => row.artists[0].item_id === artist.item_id);
  }
  if (parts[1] === "albums" && parts[2] === "album_tracks") {
    if (!visible.albums.some(a => a.item_id === args.item_id)) throw Error("Album unavailable for this profile.");
    return visible.tracks.filter(t => t.album.item_id === args.item_id);
  }
  if (parts[1] === "albums" && parts[2] === "album_versions") {
    if (!visible.albums.some(a => a.item_id === args.item_id)) throw Error("Album unavailable for this profile.");
    return [];
  }
  if (parts[1] === "playlists" && parts[2] === "playlist_tracks") {
    if (!visible.playlists.some(p => p.item_id === args.item_id)) throw Error("Playlist unavailable for this profile."); return visible.tracks.slice(0, 6);
  }
  throw Error("Read-only preview: this operation is unavailable.");
}

export function householdFixtureAdapter(): Plugin {
  const install = (server: any) => {
    server.middlewares.use(async (req, res, next) => {
      if (req.url?.startsWith("/imageproxy?")) {
        const query = new URL(req.url, "http://127.0.0.1:18741");
        const image = decodeURIComponent(query.searchParams.get("path") || "");
        if (!/^http:\/\/127\.0\.0\.1:1874[12]\/art\/[0-5]\.svg$/.test(image)) { res.statusCode = 404; res.end(); return; }
        req.url = new URL(image).pathname;
      }
      if (req.url?.startsWith("/art/")) {
        const i = Number(req.url.match(/^\/art\/(\d)\.svg$/)?.[1]);
        if (!Number.isInteger(i) || i >= colours.length) { res.statusCode = 404; res.end(); return; }
        res.setHeader("Content-Type", "image/svg+xml");
        res.end(`<svg xmlns="http://www.w3.org/2000/svg" width="600" height="600"><rect width="600" height="600" fill="${colours[i]}"/><circle cx="350" cy="200" r="170" fill="#ffffff" opacity=".18"/><path d="M0 500 Q180 180 600 390 L600 600 H0" fill="#182128" opacity=".5"/><path d="M0 560 Q250 320 600 480 L600 600 H0" fill="#11161e" opacity=".45"/></svg>`); return;
      }
      if (req.url !== "/__household/read") { next(); return; }
      res.setHeader("Content-Type", "application/json"); res.setHeader("Cache-Control", "no-store");
      if (req.method !== "POST") { res.statusCode = 405; res.end(JSON.stringify({ error: "Read contract requires JSON." })); return; }
      try {
        let raw = ""; for await (const chunk of req) { raw += chunk; if (raw.length > 8192) throw Error("Request too large."); }
        const body = JSON.parse(raw);
        if (Object.keys(body).some(k => !["profile", "command", "args"].includes(k))) throw Error("Unsupported read contract.");
        if (!["127.0.0.1:18741", "127.0.0.1:18742"].includes(req.headers.host || "")) throw Error("Use the loopback preview address.");
        res.end(JSON.stringify({ result: project(body.profile, body.command, body.args) }).replaceAll("http://127.0.0.1:18741/art/", "http://" + req.headers.host + "/art/"));
      } catch (error) { res.statusCode = 403; res.end(JSON.stringify({ error: error instanceof Error ? error.message : "Read unavailable." })); }
    });
  };
  return { name: "isolated-household-read-projection", configureServer: install, configurePreviewServer: install };
}
