import { test } from "node:test";
import assert from "node:assert/strict";
import { moveItem, newItemId } from "../../home_starter/server/homestarter/static/surfaces.js";

test("first-use record IDs work when HTTP browser crypto has no randomUUID", () => {
  const httpCrypto = { getRandomValues: bytes => crypto.getRandomValues(bytes) };
  assert.equal(httpCrypto.randomUUID, undefined);
  assert.match(newItemId("person", httpCrypto), /^person-[0-9a-f]{16}$/);
  assert.match(newItemId("screen", httpCrypto), /^screen-[0-9a-f]{16}$/);
});

test("reorder preserves targets and never wraps", () => {
  const original = ["light.kitchen", "room:bedroom", "climate.home"];
  assert.deepEqual(moveItem(original, "climate.home", -1), ["light.kitchen", "climate.home", "room:bedroom"]);
  assert.deepEqual(moveItem(original, "light.kitchen", -1), original);
  assert.deepEqual(moveItem(original, "missing", 1), original);
  assert.deepEqual(original, ["light.kitchen", "room:bedroom", "climate.home"]);
});
