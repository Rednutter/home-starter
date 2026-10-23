<template>
  <section class="sharing-panel discovery-panel">
    <h1>{{ category==='radio'?'Discover Radio':'Find Podcasts' }}</h1>
    <p>{{ category==='radio'?'Local where confirmed, then Australian and English-language stations.':'Search shows across the configured podcast catalogue.' }}</p>
    <form @submit.prevent="search"><label>Search<input v-model="query" maxlength="120" :placeholder="category==='radio'?'Station or place':'Show or topic'" /></label><button :disabled="loading">{{ loading?'Searching…':'Search' }}</button></form>
    <p v-if="category==='podcast'">General suggestions use the configured trending catalogue. Missing language metadata is labelled; personal context uses only your own saved show identities.</p>
    <button v-if="category==='podcast'" type="button" :disabled="loading" @click="query='';search()">General trending</button>
    <p role="status">{{ error || (states.some(s=>s.state==='unavailable')?'Some sources are unavailable. Available results are shown.':'') }}</p>
    <details v-if="note || states.length"><summary>Catalogue coverage</summary><p>{{ note }}</p><p v-if="region">Configured region: {{ region }}</p><p>{{ states.map(s=>(sourceNames[s.source]||s.source)+': '+s.state).join(' · ') }}</p></details>
    <ul class="discovery-list"><li v-for="item in items.slice(offset,offset+24)" :key="item.uri"><strong>{{ item.name }}</strong><span>{{ item.household_discovery?.recommendation_basis==='your-saved-podcast'?'From your saved listening':item.household_discovery?.label || (item.media_type==='radio'?'Radio station':'Podcast show') }}</span><button v-if="releaseMode" :disabled="pending || selecting" @click="chooseMedia(item)">{{ item.media_type==='podcast'?'Choose episode':'Play' }}</button><button v-else disabled>Read-only preview</button></li></ul>
    <nav v-if="items.length" aria-label="Discovery pages"><button :disabled="offset===0" @click="offset=Math.max(0,offset-24)">Previous</button><span> {{ offset+1 }}–{{ Math.min(items.length,offset+24) }} of {{ items.length }} </span><button :disabled="offset+24>=items.length" @click="offset+=24">Next</button></nav>
    <p v-if="!loading && searched && !items.length">No matching results from available sources. Try a different search; your saved library is unchanged.</p>
  </section>
</template>
<script setup lang="ts">
import { ref, watch, onUnmounted } from 'vue';
import api from '@/plugins/api';
import { profile,releaseMode } from './context';
import {pending,selecting,chooseMedia} from './household';
const props=defineProps<{category:string}>();
const query=ref(''),loading=ref(false),searched=ref(false),error=ref(''),note=ref(''),region=ref(''),items=ref<any[]>([]),states=ref<any[]>([]);
const offset=ref(0);
const sourceNames:Record<string,string>={radiobrowser:'Radio directory',abc_radio_network:'ABC',tunein:'TuneIn',radioparadise:'Radio Paradise',itunes_podcasts:'Podcast directory'};
watch(items,()=>offset.value=0);
let version=0;
async function search(){const current=++version;loading.value=true;searched.value=true;error.value='';items.value=[];states.value=[];try{const result=await api.sendCommand<any>('household/discovery',{category:props.category,query:query.value});if(current!==version)return;items.value=result.items;states.value=result.sources;note.value=result.note;region.value=result.region||'';}catch{if(current===version)error.value='Discovery is unavailable. Your saved library and household playback are unchanged.';}finally{if(current===version)loading.value=false;}}
watch([()=>props.category,profile],()=>{version++;query.value='';items.value=[];states.value=[];error.value='';note.value='';region.value='';loading.value=false;searched.value=false;});
onUnmounted(()=>version++);
</script>
