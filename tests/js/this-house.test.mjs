import test from "node:test";
import assert from "node:assert/strict";
import { devicesFor, pendingHouse, roomsByFloor } from "../../home_starter/server/homestarter/static/this-house.js";

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

test("reviewed coverage can be healthy without a single physical room", () => {
  const view={devices:[{id:"zone",name:"Shared zone",placed:false,multiroom:true,needs_room:false,attention:false}]};
  assert.deepEqual(devicesFor(view,"room"),[]);
  assert.deepEqual(devicesFor(view,"placed").map(d=>d.id),["zone"]);
});

test("room inspection uses native assignments and includes entity-only services", () => {
  const view={floors:[{floor_id:"upper",name:"Upper"}],areas:[{area_id:"room",name:"Kitchen",floor_id:"upper"},{area_id:"group",name:"Room group",kind:"group",floor_id:"upper"},{area_id:"unknown",name:"Unplaced",floor_id:"deleted"}],devices:[{id:"one",area_id:"room",entity_count:80},{id:"two",area_id:null}],services:[{entity_id:"calendar.example",area_id:"room"}]};
  const grouped=roomsByFloor(view);
  const kitchen=grouped[0].areas.find(a=>a.area_id==="room");
  assert.equal(kitchen.devices.length,1);
  assert.equal(kitchen.services.length,1);
  assert.equal(grouped[0].areas.find(a=>a.area_id==="group").kind,"group");
  assert.equal(grouped[1].name,"No floor assigned");
  assert.equal(roomsByFloor({...view,floors:[]})[0].areas.length,3);
  assert.deepEqual(roomsByFloor({...view,areas:[]}),[]);
});
