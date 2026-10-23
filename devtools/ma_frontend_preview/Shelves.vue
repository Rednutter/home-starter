<template><ItemsListing :key="profile + shelf" :title="shelf === 'recent' ? 'Recently played' : 'Favourites'" :path="'household-' + profile + '-' + shelf" itemtype="tracks" :show-provider="false" :load-items="load" :allow-key-hooks="false" :show-search-button="true" :restore-state="true" /></template>
<script setup lang="ts">
import ItemsListing from "@/components/ItemsListing.vue";
import api from "@/plugins/api";
import { profile } from "./context";
const props = defineProps<{ shelf: string }>();
const load = () => api.sendCommand<any[]>("household/" + props.shelf);
</script>
