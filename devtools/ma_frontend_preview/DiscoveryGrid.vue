<template>
  <div class="discovery-grid" @error.capture="imageFailed">
    <EditorialMediaCard v-for="item in items" :key="item.uri" :item="item" fluid show-checkboxes
      :disabled="disabled" :aria-disabled="disabled" :aria-label="item.name + (item.media_type==='podcast'?' — choose episode':' — choose playback')"
      @select="$emit('choose',item)">
      <template #subtitle>{{ item.household_discovery?.recommendation_basis==='your-saved-podcast'?'From your listening':item.household_discovery?.label || subtitle }}</template>
    </EditorialMediaCard>
  </div>
</template>
<script setup lang="ts">
import EditorialMediaCard from '@/components/discover/EditorialMediaCard.vue';
defineProps<{items:any[],disabled?:boolean,subtitle?:string}>();
defineEmits<{choose:[item:any]}>();
function imageFailed(event:Event){const image=event.target;if(image instanceof HTMLImageElement)image.hidden=true;}
</script>
