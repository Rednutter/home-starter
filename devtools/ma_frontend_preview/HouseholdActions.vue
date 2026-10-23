<template><section v-if="currentMedia" class="household-item-actions" aria-label="Selected audio actions"><strong>{{ currentMedia.name }}</strong><button :disabled="pending || selecting || occupied" @click="chooseMedia(currentMedia)">Play selection</button><button v-if="canQueue && session?.can_add" :disabled="pending || selecting" @click="chooseMedia(currentMedia,'queue_add')">Add to queue</button><button v-if="canQueue && session?.can_next" :disabled="pending || selecting" @click="chooseMedia(currentMedia,'queue_next')">Play next</button><button :disabled="pending || selecting" @click="save">Save to music favourites</button><span v-if="occupied">This speaker is occupied. Join listening or deliberately review takeover.</span></section></template>
<script setup lang="ts">
import {computed} from 'vue';
import {currentMedia,pending,selecting,occupied,session,chooseMedia,action} from './household';
const canQueue=computed(()=>currentMedia.value?.media_type==='track' && !(currentMedia.value.provider_mappings||[]).some((m:any)=>['spotify','audiobookshelf','audible','storytel'].includes(m.provider_domain)));
async function save(){if(!currentMedia.value?.household_id)await chooseMedia(currentMedia.value,'select_only');if(currentMedia.value?.household_id)await action('favorite',{item:currentMedia.value.household_id});}
</script>
