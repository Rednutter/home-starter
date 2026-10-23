import test from "node:test";
import assert from "node:assert/strict";
import { project, musicShelf } from "./server-adapter.ts";

test("House music deduplicates exact identities and pages without truncation", () => {
  const all = project("house", "music/artists/library_items");
  const paged = [0, 2].flatMap(offset => project("house", "music/artists/library_items", { offset, limit: 2 }));
  assert.equal(all.length, 4);
  assert.deepEqual(paged.map(r => r.uri), all.map(r => r.uri));
  assert.equal(new Set(all.map(r => r.uri)).size, all.length);
  assert.equal(all[0].provider_mappings.length, 2);
});
test("House classification excludes ambient tracks and unknown provenance rather than guessing from media type", () => {
  const rows = [{ media_type: "track", household_category: "ambient" }, { media_type: "track" }, { media_type: "podcast", household_category: "music" }, { media_type: "track", household_category: "music" }];
  assert.deepEqual(musicShelf("house", rows), [rows[3]]);
});
test("personal collections follow explicit ownership, never House or another person", () => {
  assert.deepEqual(project("alex", "music/artists/library_items").map(r => r.item_id), ["a0", "a4"]);
  assert.deepEqual(project("sam", "music/artists/library_items").map(r => r.item_id), ["a1", "a5"]);
  assert.throws(() => project("sam", "music/artists/get_artist", { item_id: "a0" }));
  assert.throws(() => project("unknown", "music/artists/library_items"));
});
test("different playlists with the same name retain separate exact identities", () => {
  const rows = project("alex", "music/playlists/library_items");
  assert.equal(rows.length, 2);
  assert.equal(rows[0].name, rows[1].name);
  assert.notEqual(rows[0].uri, rows[1].uri);
  assert(!project("house", "music/playlists/library_items").some(r => r.item_id === "p3"));
});
test("profile favourites/recents remain scoped; House shelves contain music only", () => {
  for (const command of ["household/recent", "household/favourites"]) {
    const house = project("house", command);
    assert(house.every(r => ["artist", "track", "playlist"].includes(r.media_type)));
    assert.notDeepEqual(project("alex", command), project("sam", command));
  }
});
test("typed search retains profile boundaries and unavailable writes fail closed", () => {
  assert.equal(project("alex", "music/artists/library_items", { search: "quiet" }).length, 0);
  assert.equal(project("sam", "music/artists/library_items", { search: "quiet" }).length, 1);
  for (const command of ["player_queues/play_media", "players/cmd/volume_set", "music/artists/update", "music/playlists/delete", "config/get", "auth/login"]) assert.throws(() => project("house", command));
});
