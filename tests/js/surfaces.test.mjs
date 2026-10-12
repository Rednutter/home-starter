import { test } from "node:test";
import assert from "node:assert/strict";
import { moveItem } from "../../home_starter/server/homestarter/static/surfaces.js";

test("reorder preserves targets and never wraps", () => {
  const original = ["light.kitchen", "room:bedroom", "climate.home"];
  assert.deepEqual(moveItem(original, "climate.home", -1), ["light.kitchen", "climate.home", "room:bedroom"]);
  assert.deepEqual(moveItem(original, "light.kitchen", -1), original);
  assert.deepEqual(moveItem(original, "missing", 1), original);
  assert.deepEqual(original, ["light.kitchen", "room:bedroom", "climate.home"]);
});
