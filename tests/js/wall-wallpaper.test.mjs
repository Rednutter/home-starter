import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
const choose=new Function(readFileSync(new URL("../../home_starter/server/homestarter/static/wall-wallpaper.js",import.meta.url),"utf8")+"\nreturn wallWallpaper;")();
const periods=["morning","day","afternoon","evening","night"];
const catalogue=periods.flatMap(period=>Array.from({length:4},(_,n)=>({period,id:`${period}-${n}`})));
const at=(time)=>new Date(`2026-10-19T${time}:00+11:00`);
test("wallpaper changes only at household time-period boundaries",()=>{
 for(const [time,period] of [["04:59","night"],["05:00","morning"],["09:59","morning"],["10:00","day"],["13:59","day"],["14:00","afternoon"],["16:59","afternoon"],["17:00","evening"],["19:59","evening"],["20:00","night"]]) {
  const result=choose(at(time),"Australia/Sydney","wall",catalogue);
  assert.equal(result.period,period);assert.ok(result.id.startsWith(period+"-"));
 }
 assert.deepEqual(choose(at("05:00"),"Australia/Sydney","wall",catalogue),choose(at("09:59"),"Australia/Sydney","wall",catalogue));
 assert.deepEqual(choose(at("10:00"),"Australia/Sydney","wall",catalogue),choose(at("13:59"),"Australia/Sydney","wall",catalogue));
 assert.deepEqual(choose(at("20:00"),"Australia/Sydney","wall",catalogue),choose(new Date("2026-10-20T04:59:00+11:00"),"Australia/Sydney","wall",catalogue));
});
test("local seeded selection is stable after reload and draws from the whole pool",()=>{
 const used=new Set();
 for(let day=1;day<=31;day++) {
  const now=new Date(Date.UTC(2026,9,day,10));
  const result=choose(now,"Australia/Sydney","wall",catalogue);
  assert.deepEqual(result,choose(now,"Australia/Sydney","wall",catalogue));used.add(result.id);
 }
 assert.equal(used.size,4);
});
test("household timezone, not browser timezone, controls selection; invalid/missing assets fall back",()=>{
 assert.equal(choose(new Date("2026-10-19T09:00:00Z"),"Australia/Sydney","wall",catalogue).period,"night");
 assert.equal(choose(at("20:00"),"Australia/Sydney","wall",[]).id,null);
 assert.equal(choose(at("20:00"),"Australia/Sydney","wall",[{period:"night",id:"bad);url(https://example.invalid)"}]).id,null);
});
