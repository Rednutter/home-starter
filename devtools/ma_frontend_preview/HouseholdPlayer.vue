<template>
 <div v-if="notice" class="household-notice" role="status">{{ notice }}</div>
 <footer class="persistent-player" aria-label="Household playback">
  <div class="player-copy"><strong>{{ listening?.session?.player_id === selected?.player_id ? listening?.session?.title : selected?.name || 'Choose your audio' }}</strong><span>{{ session?.owner ? session.owner+' · ':'' }}{{ selected?.state || 'Choose a speaker' }}</span></div>
  <div class="transport"><button :disabled="pending || !session?.owned" @click="action('play')" aria-label="Resume">▶</button><button :disabled="pending || !session?.owned || !selected?.features?.includes('pause')" @click="action('pause')">Pause</button><button :disabled="pending || !session?.owned" @click="action('stop')">Stop</button><button :disabled="pending || !session?.owned || !selected?.features?.includes('next_previous')" @click="action('next')">Next</button></div>
  <button class="outputs" @click="drawer=!drawer">{{ selected?.name || 'Choose speakers' }} <span>Speakers · queue · timer</span></button>
 </footer>
 <section v-if="drawer" class="household-drawer" aria-label="Speakers and queue">
  <header><h2>Listening around the house</h2><button @click="drawer=false" aria-label="Close speakers and queue">Close</button></header>
  <p>Changing profile or selecting speakers does not interrupt playback.</p>
  <div class="speaker-choices"><label v-for="room in listening?.players || []" :key="room.entity_id"><input type="checkbox" :checked="speakers.includes(room.entity_id)" :disabled="pending || !room.available || !room.single" @change="toggle(room.entity_id)"><strong>{{ room.name }}</strong><span>{{ room.available?room.state:'Unavailable' }}</span></label></div>
  <p v-if="speakers.length>1" role="status">{{ listening?.grouping?.reason || 'Grouped playback is not implemented in the household service yet. Choose one speaker; separate unsynchronised streams will not be started.' }}</p>
  <button :disabled="pending || speakers.length!==1" @click="useSpeaker">Use selected speaker</button>
  <p v-if="session?.owner">{{ session.owner }} owns this queue. {{ session.joined?'You have joined listening.':'' }}</p>
  <div v-if="session?.owned" class="drawer-transport"><button :disabled="pending" @click="action('play')">Resume</button><button :disabled="pending || !selected?.features?.includes('pause')" @click="action('pause')">Pause</button><button :disabled="pending" @click="action('stop')">Stop</button><button :disabled="pending || !selected?.features?.includes('next_previous')" @click="action('next')">Next</button></div>
  <button v-if="session?.can_join" :disabled="pending" @click="action('queue_join',{session:session.revision})">Join listening</button>
  <button v-if="session?.can_takeover && !listening?.takeover" :disabled="pending" @click="action('queue_takeover_prepare',{session:session.revision})">Review takeover</button>
  <div v-if="listening?.takeover"><p>Take over this queue? Its contents stay; its sleep timer will be cleared. Personal progress stays separate.</p><button :disabled="pending" @click="action('queue_takeover',{session:session?.revision,confirmation:listening.takeover.confirmation})">Confirm takeover</button><button @click="action('queue_takeover_cancel')">Cancel</button></div>
  <p v-if="session?.issue || session?.edit_issue">{{ session.issue || session.edit_issue }}</p>
  <form v-if="session?.owned && selected?.features?.includes('volume_set')" @submit.prevent="action('volume',{value:volume})"><label>Volume (%)<input type="number" min="0" max="100" required v-model.number="volume"></label><button :disabled="pending">Apply volume</button></form>
  <label v-if="session?.owned">Sleep timer<select aria-label="Sleep timer" :disabled="pending" @change="action('sleep',{value:Number(($event.target as HTMLSelectElement).value)})"><option value="" disabled selected>Choose timer</option><option value="0">Off</option><option value="900">15 minutes</option><option value="1800">30 minutes</option><option value="3600">1 hour</option></select></label>
  <p v-if="listening?.sleep">A sleep timer is active for this session.</p>
  <ol aria-label="Selected room queue"><li v-for="row in session?.queue || []" :key="row.entry"><span>{{ row.title }}{{ row.current?' · playing':'' }}</span><button v-if="session.can_edit" :disabled="pending || !row.up" @click="action('queue_move',{entry:row.entry,value:-1,session:session.revision})">Up</button><button v-if="session.can_edit" :disabled="pending || !row.down" @click="action('queue_move',{entry:row.entry,value:1,session:session.revision})">Down</button><button v-if="session.can_edit" :disabled="pending || !row.remove" @click="action('queue_remove',{entry:row.entry,session:session.revision})">Remove</button></li></ol>
  <p v-if="!listening">Loading permitted household playback…</p>
 </section>
</template>
<script setup lang="ts">
import {ref} from 'vue';
import {listening,player,speakers,notice,pending,drawer,selected,session,action} from './household';
const volume=ref<number|undefined>();
function toggle(id:string){speakers.value=speakers.value.includes(id)?speakers.value.filter(v=>v!==id):[...speakers.value,id];player.value=speakers.value.length===1?speakers.value[0]:null;}
async function useSpeaker(){if(speakers.value.length!==1)return;player.value=speakers.value[0];await action('destination');}
</script>
