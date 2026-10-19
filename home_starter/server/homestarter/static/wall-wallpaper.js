// One local wallpaper per household time period, stable across refresh/midnight.
const wallWallpaper=(now,timeZone,surface,catalogue=[])=>{
 const parts=Object.fromEntries(new Intl.DateTimeFormat("en-CA",{timeZone,year:"numeric",month:"2-digit",day:"2-digit",hour:"2-digit",hourCycle:"h23"}).formatToParts(now).map(p=>[p.type,p.value]));
 const hour=Number(parts.hour);
 const period=hour<5||hour>=20?"night":hour<10?"morning":hour<14?"day":hour<17?"afternoon":"evening";
 const day=new Date(Date.UTC(Number(parts.year),Number(parts.month)-1,Number(parts.day))-(hour<5?86400000:0)).toISOString().slice(0,10);
 const pool=catalogue.filter(row=>row.period===period&&/^[a-z][a-z0-9-]{0,63}$/.test(row.id));
 if(!pool.length)return {period,id:null};
 let seed=2166136261;
 for(const character of `${surface}|${period}|${day}`)seed=Math.imul(seed^character.charCodeAt(0),16777619)>>>0;
 return {period,id:pool[seed%pool.length].id};
};
