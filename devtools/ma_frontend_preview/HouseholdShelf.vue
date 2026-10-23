<template><section class="discovery-panel"><h1>{{ kind==='episodes'?'Podcast episodes':kind==='books'?'Audiobooks':'Ambient' }}</h1><p v-if="kind==='books'">{{ listening?.audiobooks?.message || 'Choose a person to keep book progress separate.' }}</p><p v-else-if="kind!=='episodes'">Background sounds for rest and focus. Choose a sound, then a speaker. Timers are available in playback controls.</p><p v-if="!rows.length">Nothing is currently available for this profile.</p><DiscoveryGrid :items="cards" :disabled="pending" :subtitle="kind==='books'?'Resume audiobook':kind==='episodes'?'Podcast episode':'Ambient sound'" @choose="choose" /></section></template>
<script setup lang="ts">
import {computed} from 'vue';
import {listening,pending,action} from './household';
import DiscoveryGrid from './DiscoveryGrid.vue';
const props=defineProps<{kind:string}>();
const rows=computed(()=>props.kind==='books'?(listening.value?.books||[]):props.kind==='episodes'?(listening.value?.library||[]).filter((r:any)=>r.kind==='podcast_episode'):(listening.value?.channels||[]).filter((r:any)=>r.category==='ambient'));
const cards=computed(()=>rows.value.map((r:any)=>({item_id:r.id,uri:r.id,name:r.title,media_type:props.kind==='books'?'audiobook':props.kind==='episodes'?'podcast_episode':'radio',provider:'household',metadata:{images:[]}})));
function choose(item:any){void action(props.kind==='books'?'resume':'play_item',{item:item.item_id});}
</script>
