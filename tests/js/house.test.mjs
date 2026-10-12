import test from "node:test";
import assert from "node:assert/strict";
import { PREPARATION, EXTRA_THINGS, CATEGORIES, visibleDevices } from "../../home_starter/server/homestarter/static/house.js";

test("preparation is household-specific and optional", () => {
  assert.ok(PREPARATION.some(x => x.includes("wall switches")));
  assert.ok(PREPARATION.some(x => x.includes("phones and tablets")));
  assert.ok(PREPARATION.some(x => x.includes("deliberately no longer use")));
});
test("forgotten hardware suggestions are possibilities", () => {
  assert.equal(EXTRA_THINGS.length, 12);
  assert.ok(EXTRA_THINGS[0][1].startsWith("Possible uses:"));
});
test("inventory filters devices rather than unrelated findings", () => {
  const inventory = { devices: [{id:"one",name:"Hall light",status:"fine"},{id:"two",name:"Plug",status:"unknown"}],
    findings: [{category:"needs_room",device_ids:["two"]}] };
  assert.deepEqual(visibleDevices(inventory, "fine", "Hall").map(d => d.id), ["one"]);
  assert.deepEqual(visibleDevices(inventory, "needs_room", "").map(d => d.id), ["two"]);
  assert.equal(visibleDevices(inventory, "all", "missing").length, 0);
  assert.equal(CATEGORIES.offline, "Possibly offline");
});
