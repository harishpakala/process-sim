<script setup lang="ts">
import { computed } from 'vue'

type Sample = { simulation_seconds?: number; value?: number }
type Pair = { before?: Sample | null; after?: Sample | null }
type Command = { simulation_seconds?: number; fault_id?: string; action?: string }
const props = defineProps<{ command?: Command | null; measurements: Record<string, Pair> }>()
const points = computed(() => {
 const rows: {key:string; time:number; label:string; value?:number; kind:'sample'|'command'}[] = []
 for (const [signal, pair] of Object.entries(props.measurements || {})) {
  for (const phase of ['before','after'] as const) {
   const sample = pair?.[phase]
   if (typeof sample?.simulation_seconds === 'number' && Number.isFinite(sample.simulation_seconds))
    rows.push({key:signal+phase,time:sample.simulation_seconds,label:signal+' '+phase,value:sample.value,kind:'sample'})
  }
 }
 if (typeof props.command?.simulation_seconds === 'number' && Number.isFinite(props.command.simulation_seconds))
  rows.push({key:'command',time:props.command.simulation_seconds,label:(props.command.fault_id || 'Fault')+' '+(props.command.action || 'operator command'),kind:'command'})
 return rows.sort((a,b)=>a.time-b.time || a.key.localeCompare(b.key))
})
const bounds = computed(()=>{
 const times=points.value.map(p=>p.time)
 const min=Math.min(...times),max=Math.max(...times)
 return {min,max,span:Math.max(max-min,1)}
})
function percent(time:number){return 4+92*(time-bounds.value.min)/bounds.value.span}
</script>

<template>
 <section v-if="points.length" class="timeline" aria-label="Recorded simulation timeline">
  <h3>Recorded simulation timeline</h3>
  <p class="note">Positions reflect simulation timestamps. Connecting or ordering samples does not establish causality.</p>
  <div class="track" aria-hidden="true">
   <div v-for="point in points" :key="point.key" class="tick" :class="point.kind" :style="{left:percent(point.time)+'%'}"></div>
  </div>
  <div class="entries">
   <div v-for="point in points" :key="point.key" class="entry">
    <span class="marker" :class="point.kind"></span>
    <strong>{{point.time}} s</strong>
    <span>{{point.label}}</span>
    <span v-if="point.kind==='sample'">{{point.value ?? 'Value not recorded'}}</span>
    <span v-else>Recorded command, not proof of activation</span>
   </div>
  </div>
  <p v-if="!points.some(p=>p.kind==='command')" class="note">Command timestamp not returned in this answer's evidence.</p>
 </section>
</template>

<style scoped>
.timeline{display:grid;gap:12px;border-top:1px solid #334a62;padding-top:15px}.timeline h3{font-size:14px;margin:0}.note{font-size:12px;color:#a9bfd0;margin:0}.track{position:relative;height:24px;border-bottom:2px solid #657b92;margin:8px 8px 0}.tick{position:absolute;bottom:-5px;width:10px;height:10px;border-radius:50%;background:#79b8ff;transform:translateX(-50%)}.tick.command{height:18px;width:4px;border-radius:2px;background:#fbbf24;bottom:-9px}.entries{display:grid;gap:6px}.entry{display:grid;grid-template-columns:12px 65px minmax(100px,1fr) minmax(100px,1fr);gap:8px;align-items:center;font-size:12px;overflow-wrap:anywhere}.marker{width:8px;height:8px;border-radius:50%;background:#79b8ff}.marker.command{background:#fbbf24}@media(max-width:600px){.entry{grid-template-columns:12px 52px 1fr}.entry span:last-child{grid-column:3}}
</style>
