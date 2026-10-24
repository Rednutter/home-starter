import { ref } from "vue";
export const profile = ref("house");
export const generation = ref(0);
export const readStatus = ref("");
export const switching = ref(false);
export const viewPreferences: Record<string, Record<string, unknown>> = {};
export const readFailures = new Map<string, string>();
export function clearReadFailures() { readFailures.clear(); readStatus.value = ""; }
export const releaseMode = import.meta.env.MODE === "household-release";
export const realMode = releaseMode || import.meta.env.MODE === "real-readonly";
export const booting = ref(realMode);
export const previewNotes = ref("");
export const people = ref([{ id: "house", name: "House" }, { id: "alex", name: "Alex" }, { id: "sam", name: "Sam" }, { id: "casey", name: "Casey" }, { id: "jamie", name: "Jamie" }, { id: "riley", name: "Riley" }]);
