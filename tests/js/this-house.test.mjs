import test from "node:test";
import assert from "node:assert/strict";
import { devicesFor, pendingHouse } from "../../home_starter/server/homestarter/static/this-house.js";

test("placement queues operate on equipment records with separate attention", () => {
  const view = {devices:[{id:"one",name:"Example lamp",placed:true,needs_room:false,attention:false},{id:"two",name:"Example relay",placed:false,needs_room:true,attention:true},{id:"three",name:"Example speaker",placed:false,needs_room:true,attention:false}]};
  assert.deepEqual(devicesFor(view,"room").map(d=>d.id),["three","two"]);
  assert.deepEqual(devicesFor(view,"placed").map(d=>d.id),["one"]);
  assert.deepEqual(devicesFor(view,"attention").map(d=>d.id),["two"]);
  assert.equal(devicesFor(view,"all","missing").length,0);
});

test("a loaded registry is not a commissioned physical house", () => {
  const view={complete:true,expectation:{people:2,adults:1},structure_confirmed:false,counts:{expectation_matches:false,people_needing_review:3,needs_room:2,attention:1}};
  const pending=pendingHouse(view);
  assert.ok(pending.includes("Confirm 2 household members and 1 adults"));
  assert.ok(pending.includes("Compare floors and rooms with the physical house"));
  assert.ok(pending.includes("2 equipment records need a room"));
});
