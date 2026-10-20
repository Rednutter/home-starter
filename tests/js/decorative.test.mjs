import test from "node:test";
import assert from "node:assert/strict";
import {readFileSync} from "node:fs";
const choose=new Function(readFileSync("home_starter/server/homestarter/static/decorative.js","utf8")+"\nreturn decorationStyle;")();
test("discoveries use the full local pool and remain stable through a period and midnight",()=>{
 const at=s=>new Date("2026-10-20T"+s+":00+11:00");
 assert.equal(choose(at("06:00"),"Australia/Sydney","child"),choose(at("09:59"),"Australia/Sydney","child"));
 assert.equal(choose(at("20:00"),"Australia/Sydney","child"),choose(new Date("2026-10-21T04:59:00+11:00"),"Australia/Sydney","child"));
 const used=new Set();for(let n=0;n<1000;n++)used.add(choose(new Date(at("06:00").getTime()+n*86400000),"Australia/Sydney","child"));
 assert.equal(used.size,42);
 assert.notEqual(choose(at("06:00"),"Australia/Sydney","child"),choose(at("06:00"),"Australia/Sydney","other-child"));
});
