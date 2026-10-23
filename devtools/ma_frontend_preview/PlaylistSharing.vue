<template>
  <section class="sharing-panel">
    <h1>Playlist sharing</h1>
    <p>Choose who owns a playlist and where it appears. A source account does not establish ownership.</p>
    <p role="status">{{ realMode ? 'Existing sharing is unchanged. Real playlist ownership remains unassigned until an explicit choice is approved.' : 'Fictional example only. Choices below remain in this tab and never change household or provider data.' }}</p>
    <label for="sharing-playlist">Playlist</label><select id="sharing-playlist" :disabled="realMode" v-model="playlist"><option value="one">Weekend favourites · example identity one</option><option value="two">Weekend favourites · example identity two</option></select>
    <label for="sharing-owner">Owner</label><select id="sharing-owner" :disabled="realMode" v-model="owner"><option value="">Unassigned</option><option v-for="person in people" :value="person.id" :key="person.id">{{ person.name }}</option></select>
    <fieldset :disabled="realMode"><legend>Appears in</legend><label><input type="radio" value="mine" v-model="visibility"> Mine</label><label><input type="radio" value="selected" v-model="visibility"> Selected people</label><label><input type="radio" value="house" v-model="visibility"> House · everyone</label></fieldset>
    <fieldset v-if="visibility === 'selected'"><legend>Selected people</legend><label v-for="person in people.filter(p=>p.id!=='house' && p.id!==owner)" :key="person.id"><input type="checkbox" :value="person.id" v-model="selected"> {{ person.name }}</label></fieldset>
    <button :disabled="realMode || !owner || visibility==='selected' && !selected.length" @click="preview">Preview fictional choice</button>
    <p role="status">{{ result }}</p>
    <p>Unknown ownership stays unassigned. Same-name playlists remain separate. Sharing catalogue metadata does not grant provider credentials or change playback allocation.</p>
  </section>
</template>
<script setup lang="ts">
import { ref, watch } from 'vue';
import { people, realMode, profile } from './context';
const playlist=ref('one'), owner=ref(''), visibility=ref('mine'), selected=ref<string[]>([]), result=ref('');
const drafts:Record<string,any>={};
watch([playlist,profile],()=>{ const d=drafts[profile.value+':'+playlist.value]; owner.value=d?.owner||''; visibility.value=d?.visibility||'mine'; selected.value=d?.selected||[]; result.value=''; });
watch([visibility,owner],()=>{selected.value=[];result.value='';});
function preview(){ if(realMode || !owner.value)return; drafts[profile.value+':'+playlist.value]={owner:owner.value,visibility:visibility.value,selected:[...selected.value]}; result.value='Fictional choice previewed in this tab. Nothing has been saved to the house.'; }
</script>
