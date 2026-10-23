<template><section class="sharing-panel"><h1>{{ kind==='episodes'?'Podcast episodes':kind==='books'?'Audiobooks':'Ambient' }}</h1><p v-if="kind==='books'">{{ listening?.audiobooks?.message || 'Choose a person to keep book progress separate.' }}</p><p v-if="!rows.length">Nothing is currently available for this profile.</p><ul class="discovery-list"><li v-for="item in rows" :key="item.id"><strong>{{ item.title }}</strong><button :disabled="pending" @click="action(kind==='books'?'resume':'play_item',{item:item.id})">{{ kind==='books'?'Resume':'Play' }}</button></li></ul></section></template>
<script setup lang="ts">
import {computed} from 'vue';
import {listening,pending,action} from './household';
const props=defineProps<{kind:string}>();
const rows=computed(()=>props.kind==='books'?(listening.value?.books||[]):props.kind==='episodes'?(listening.value?.library||[]).filter((r:any)=>r.kind==='podcast_episode'):(listening.value?.channels||[]).filter((r:any)=>r.category==='ambient'));
</script>
