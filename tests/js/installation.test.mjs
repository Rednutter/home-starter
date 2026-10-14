import test from "node:test";
import assert from "node:assert/strict";
import { launchMode } from "../../home_starter/server/homestarter/static/installation.js";

test("only explicit persisted setup state selects first-run versus returning launch", () => {
  assert.equal(launchMode({ first_run: true }), "first-run");
  assert.equal(launchMode({ first_run: false }), "existing");
  assert.equal(launchMode(null), "unknown");
  assert.equal(launchMode({}), "unknown");
  assert.equal(launchMode({ dashboards: [], music: { installed: false } }), "unknown");
  assert.equal(launchMode({ first_run: "false" }), "unknown");
});
