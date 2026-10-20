// Stable pseudo-random discovery per screen/daypart, including midnight continuity.
const decorationStyle=(now,timeZone,surface)=>{
 const parts=Object.fromEntries(new Intl.DateTimeFormat("en-CA",{timeZone,year:"numeric",month:"2-digit",day:"2-digit",hour:"2-digit",hourCycle:"h23"}).formatToParts(now).map(p=>[p.type,p.value]));
 const hour=Number(parts.hour),period=hour<5||hour>=20?"night":hour<10?"morning":hour<14?"day":hour<17?"afternoon":"evening";
 const day=new Date(Date.UTC(Number(parts.year),Number(parts.month)-1,Number(parts.day))-(hour<5?86400000:0)).toISOString().slice(0,10);
 let seed=2166136261;
 for(const c of `${surface}|${period}|${day}|discovery`)seed=Math.imul(seed^c.charCodeAt(0),16777619)>>>0;
 const index=seed%42;
 if(index>=40)return `--hs-decor-image:var(--hs-decor-${index===40?"saucer":"owl"});--hs-decor-size:contain;--hs-decor-position:center`;
 return `--hs-decor-image:var(--hs-decor-atlas);--hs-decor-size:800% 500%;--hs-decor-position:${index%8*100/7}% ${Math.floor(index/8)*100/4}%`;
};
