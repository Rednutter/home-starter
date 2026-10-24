<template>
  <section class="discovery-panel">
    <header class="discovery-heading"><h1>{{ category==='radio'?'Radio':'Podcasts' }}</h1>
      <form @submit.prevent="search()"><label class="sr-only" for="discovery-search">{{ category==='radio'?'Find a station':'Find a podcast' }}</label><input id="discovery-search" v-model="query" maxlength="120" :placeholder="category==='radio'?'Find a station or place':'Find a show or topic'" /><button :disabled="loading">Search</button><button v-if="searchedQuery" type="button" @click="query='';search()">Browse</button></form>
    </header>
    <p role="status">{{ error || (loading?'Loading suggestions…':states.some(s=>s.state==='unavailable')?'Some sources are unavailable. Available suggestions are shown.':'') }}</p>
    <section v-for="section in sections" :key="section.title" class="discovery-section">
      <h2>{{ section.title }}</h2><p v-if="section.description">{{ section.description }}</p>
      <DiscoveryGrid :items="section.items" :disabled="!releaseMode || pending || selecting || !!compatibilityNotice" @choose="chooseMedia" />
    </section>
    <nav v-if="total>24" aria-label="Discovery pages"><button :disabled="loading || offset===0" @click="movePage(-24)">Previous</button><span>{{ offset+1 }}–{{ Math.min(total,offset+items.length) }} of {{ total }}</span><button :disabled="loading || offset+24>=total" @click="movePage(24)">Next</button></nav>
    <p v-if="!loading && searched && !items.length">No suggestions are available for this profile from the current sources. Search remains available; nothing has been added to your library.</p>
    <details v-if="note || states.length"><summary>About these suggestions</summary><p>{{ note }}</p><p v-if="region">Region: {{ region }}</p><p>{{ states.map(s=>(sourceNames[s.source]||s.source)+': '+s.state).join(' · ') }}</p></details>
  </section>
</template>
<script setup lang="ts">
import { computed, ref, watch, onUnmounted } from 'vue';
import api from '@/plugins/api';
import { profile,releaseMode,compatibilityNotice } from './context';
import {pending,selecting,chooseMedia} from './household';
import DiscoveryGrid from './DiscoveryGrid.vue';
const props=defineProps<{category:string}>();
const query=ref(''),searchedQuery=ref(''),loading=ref(false),searched=ref(false),error=ref(''),note=ref(''),region=ref(''),items=ref<any[]>([]),states=ref<any[]>([]);
const offset=ref(0),total=ref(0);
const sourceNames:Record<string,string>={radiobrowser:'Radio directory',abc_radio_network:'ABC',tunein:'TuneIn',radioparadise:'Radio Paradise',itunes_podcasts:'Podcast directory'};
const sections=computed(()=>{
 const page=items.value;
 if(searchedQuery.value)return [{title:'Search results',items:page}];
 const groups=props.category==='radio'?[
  {title:'Around the Border',test:(r:any)=>r.household_discovery?.local,description:'Stations with verified regional identities.'},
  {title:'Across Australia',test:(r:any)=>!r.household_discovery?.local && r.household_discovery?.country==='AU',description:''},
  {title:'More stations',test:(r:any)=>!r.household_discovery?.local && r.household_discovery?.country!=='AU',description:''}
 ]:[
  {title:'From your listening',test:(r:any)=>r.household_discovery?.recommendation_basis==='your-saved-podcast',description:''},
  {title:'Popular shows',test:(r:any)=>r.household_discovery?.recommendation_basis!=='your-saved-podcast',description:'Suggestions from the podcast directory. These are not subscriptions or personal favourites.'}
 ];
 return groups.map(g=>({...g,items:page.filter(g.test)})).filter(g=>g.items.length);
});
let version=0;
async function search(reset=true,pageOffset=offset.value){
 const current=++version;loading.value=true;searched.value=true;error.value='';
 const requested=query.value,requestedOffset=reset?0:pageOffset;
 try{
  const result=await api.sendCommand<any>('household/discovery',{category:props.category,query:requested,offset:requestedOffset,limit:24});
  if(current!==version)return;
  items.value=result.items;offset.value=result.offset??requestedOffset;total.value=result.total??result.items.length;
  searchedQuery.value=requested.trim();states.value=result.sources;note.value=result.note;region.value=result.region||'';
 }catch{if(current===version)error.value='Suggestions are temporarily unavailable. Try again; no library or playback changes were made.';}
 finally{if(current===version)loading.value=false;}
}
function movePage(delta:number){if(loading.value)return;void search(false,Math.max(0,offset.value+delta));}
watch([()=>props.category,profile],()=>{version++;query.value='';searchedQuery.value='';items.value=[];states.value=[];error.value='';note.value='';region.value='';offset.value=0;total.value=0;void search();},{immediate:true});
onUnmounted(()=>version++);
</script>
