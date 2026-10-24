<template>
  <v-app>
    <div class="household-shell" :class="{'household-production':releaseMode}">
      <aside class="library-rail" aria-label="Household library">
        <a class="household-brand" href="#/artists">Household<span>Audio</span></a>
        <label for="preview-profile">Listening profile</label>
        <select id="preview-profile" :disabled="booting || switching || pending || selecting" :value="profile" @change="changeProfile(($event.target as HTMLSelectElement).value)">
          <option v-for="person in people" :value="person.id" :key="person.id">{{ person.name }}</option>
        </select>
        <p class="rail-label">YOUR LIBRARY</p>
        <nav aria-label="Collections">
          <RouterLink v-for="link in links" :to="link.to" :key="link.to" :class="{ selected: route.path.startsWith(link.to) }"><span aria-hidden="true">{{ link.icon }}</span>{{ link.label }}</RouterLink>
        </nav>
        <RouterLink v-if="!releaseMode" to="/playlist-sharing">Playlist sharing</RouterLink>
        <RouterLink v-if="!releaseMode" to="/discover-radio">Discover Radio</RouterLink>
        <RouterLink v-if="!releaseMode" to="/find-podcasts">Find Podcasts</RouterLink>
        <p v-if="!releaseMode" class="preview-label">Component preview<br><span>{{ realMode ? 'Real metadata. Read only.' : 'Fictional music. Read only.' }}</span></p>
      </aside>
      <main class="library-main">
        <header class="library-context">
          <div class="history-buttons"><button aria-label="Back" @click="router.back()">‹</button><button aria-label="Forward" @click="router.forward()">›</button></div>
          <div><strong>{{ profile === 'house' ? 'House music' : selectedName + '’s music' }}</strong><span>{{ profile === 'house' ? 'Shared music collections · personal books and podcasts stay separate' : 'Your own collection · switching profiles does not change playback' }}</span></div>
          <span v-if="!releaseMode" class="preview-badge">{{ realMode ? 'REAL METADATA · READ ONLY' : 'READ-ONLY PREVIEW' }}</span>
        </header>
        <p class="source-caption">{{ realMode ? previewNotes : 'Combined catalogue categories · exact-identity deduplication · fictional ownership mappings' }}</p>
        <p v-if="readStatus" role="status" class="read-error">{{ readStatus }}</p>
        <p v-if="compatibilityNotice" role="status" class="compatibility-notice">{{ compatibilityNotice }}</p>
        <HouseholdActions v-if="releaseMode && !booting" />
        <p v-if="booting" role="status">Connecting your media sources…</p>
        <p v-else-if="realMode && !people.length" role="status">{{ previewNotes }}</p>
        <div v-else-if="!switching" class="native-library content-section" :key="profile + generation"><RouterView /></div>
        <p v-else role="status">Opening your collection…</p>
      </main>
      <HouseholdPlayer v-if="releaseMode" />
      <footer v-else class="persistent-player" aria-label="Now playing">
        <div class="player-art" aria-hidden="true">♫</div><div class="player-copy"><strong>Nothing playing in this preview</strong><span>Live speakers and personal progress are disconnected</span></div>
        <div class="transport"><button disabled aria-label="Previous">|‹</button><button disabled aria-label="Play">▶</button><button disabled aria-label="Next">›|</button></div>
        <button class="outputs" disabled>Choose speakers <span>Unavailable in read-only preview</span></button>
      </footer>
    </div>
  </v-app>
</template>
<script setup lang="ts">
import { computed, nextTick, watch } from "vue";
import { useRoute } from "vue-router";
import router from "@/plugins/router";
import { store } from "@/plugins/store";
import HouseholdPlayer from './HouseholdPlayer.vue';
import HouseholdActions from './HouseholdActions.vue';
import {currentMedia,pending,selecting} from './household';
import { profile, generation, readStatus, switching, viewPreferences, clearReadFailures, realMode, releaseMode, people, previewNotes, booting, compatibilityNotice } from "./context";
const route = useRoute();
watch(() => route.fullPath, () => { generation.value++; clearReadFailures();currentMedia.value=null; });
const selectedName = computed(() => people.value.find(p => p.id === profile.value)?.name || "House");
const links = [{ to: "/recent", label: "Recently played", icon: "◷" }, { to: "/favourites", label: "Favourites", icon: "♡" }, { to: "/playlists", label: "Playlists", icon: "≡" }, { to: "/artists", label: "Artists", icon: "♧" }, { to: "/albums", label: "Albums", icon: "▧" }, { to: "/tracks", label: "Songs", icon: "♫" },...(releaseMode?[{to:'/discover-radio',label:'Radio',icon:'◉'},{to:'/find-podcasts',label:'Podcasts',icon:'◷'},{to:'/ambient',label:'Ambient',icon:'≈'},{to:'/audiobooks',label:'Audiobooks',icon:'▤'}]:[])];
async function changeProfile(value: string) {
  if (switching.value || pending.value || selecting.value || !people.value.some(p => p.id === value)) return;
  switching.value = true; generation.value++;
  await nextTick(); // Native unmount saves the OLD profile's list/filter state.
  if (store.currentUser) viewPreferences[profile.value] = JSON.parse(JSON.stringify(store.currentUser.preferences));
  profile.value = value; store.prevState = undefined; clearReadFailures();
  if (store.currentUser) { store.currentUser.user_id = "fictional-" + value; store.currentUser.preferences = viewPreferences[value] || {}; }
  const root = links.find(link => route.path.startsWith(link.to))?.to || "/artists";
  await router.replace(root);
  switching.value = false;
}
</script>
