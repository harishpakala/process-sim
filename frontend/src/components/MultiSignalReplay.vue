<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'

type Point = {time:number;value:number;observedAt:string}
type Run = {runId:string;startedAt:string;sampleCount:number;faultEventCount:number}
type Fault = {event_id:string;fault_id:string;action:string;target:string;simulation_time_hours:number}
const signals = [...Array.from({length:41},(_,i)=>'XMEAS'+(i+1)),...Array.from({length:12},(_,i)=>'XMV'+(i+1))]
const selected = ref<string[]>(['XMEAS6','XMEAS7','XMEAS9'])
const runs = ref<Run[]>([])
const runId = ref('')
const series = ref<Record<string,Point[]>>({})
const faults = ref<Fault[]>([])
const loading = ref(false)
const error = ref('')
const limit = ref(2000)
const progress = ref(0)
const playing = ref(false)
const speed = ref(1)
let timer:ReturnType<typeof setInterval>|undefined
let requestId=0
const palette=['#0891b2','#7c3aed','#d97706','#059669','#db2777','#2563eb']
const available = computed(()=>selected.value.filter(s=>series.value[s]?.length))
const allTimes = computed(()=>[...new Set(available.value.flatMap(s=>series.value[s].map(p=>p.time)).filter(Number.isFinite))].sort((a,b)=>a-b))
const maxIndex = computed(()=>Math.max(0,allTimes.value.length-1))
const cursorTime = computed(()=>allTimes.value[Math.min(progress.value,maxIndex.value)]??0)
const timeBounds = computed(()=>({min:allTimes.value[0]??0,max:allTimes.value[allTimes.value.length-1]??1}))
const x = (time:number)=>55+(time-timeBounds.value.min)/(timeBounds.value.max-timeBounds.value.min||1)*690
function y(value:number,min:number,max:number){return 210-(value-min)/(max-min||1)*170}
function plot(signal:string){
 const pts=series.value[signal]||[]
 if(!pts.length)return null
 const vals=pts.map(p=>p.value)
 const min=Math.min(...vals),max=Math.max(...vals)
 return {min,max,path:pts.map((p,i)=>(i?'L':'M')+x(p.time).toFixed(2)+','+y(p.value,min,max).toFixed(2)).join(' ')}
}
function currentValue(signal:string){
 const pts=series.value[signal]||[]
 let lo=0,hi=pts.length
 while(lo<hi){const mid=(lo+hi)>>1;if(pts[mid].time<=cursorTime.value)lo=mid+1;else hi=mid}
 return lo?pts[lo-1]:null
}
const visibleFaults=computed(()=>faults.value.filter(f=>Number.isFinite(f.simulation_time_hours)&&f.simulation_time_hours>=timeBounds.value.min&&f.simulation_time_hours<=timeBounds.value.max))
async function loadRuns(){
 try{const r=await fetch('/api/simulation/runs?limit=100');const d=await r.json();if(!r.ok)throw Error(d.error||'Unable to load runs');runs.value=d.runs;if(!runs.value.some(x=>x.runId===runId.value))runId.value=runs.value[0]?.runId||''}
 catch(e){error.value=String(e)}
}
async function load(){
 const id=++requestId
 playing.value=false
 series.value={}
 faults.value=[]
 progress.value=0
 error.value=''
 if(!runId.value||!selected.value.length)return
 loading.value=true
 try{
  const results=await Promise.all(selected.value.map(async signal=>{
   const r=await fetch('/api/simulation/series?'+new URLSearchParams({runId:runId.value,signal,limit:String(limit.value)}))
   const d=await r.json()
   if(!r.ok)throw Error(signal+': '+(d.error||r.status))
   return [signal,(d.points as Point[]).filter(p=>Number.isFinite(p.time)&&Number.isFinite(p.value)).sort((a,b)=>a.time-b.time)] as const
  }))
  const fr=await fetch('/api/simulation/fault-events/history?'+new URLSearchParams({runId:runId.value,limit:'5000'}))
  const fd=await fr.json()
  if(!fr.ok)throw Error(fd.error||'Unable to load fault timeline')
  if(id===requestId){series.value=Object.fromEntries(results);faults.value=fd.events}
 }catch(e){if(id===requestId)error.value=String(e)}
 finally{if(id===requestId)loading.value=false}
}
function toggle(signal:string){selected.value=selected.value.includes(signal)?selected.value.filter(s=>s!==signal):[...selected.value,signal].slice(0,6)}
watch([runId,limit],()=>{void load()})
watch(selected,()=>{void load()})
watch(playing,v=>{
 if(timer)clearInterval(timer)
 if(v)timer=setInterval(()=>{if(progress.value>=maxIndex.value){playing.value=false;return}progress.value=Math.min(maxIndex.value,progress.value+speed.value)},200)
})
onMounted(()=>{void loadRuns()})
onUnmounted(()=>{if(timer)clearInterval(timer);requestId++})
</script>

<template>
<section class="panel" style="padding:22px">
 <h2>Synchronized Multi-Signal Replay</h2>
 <p>Compare up to six recorded process signals on a shared simulation-time cursor. Each chart uses its own value scale.</p>
 <div style="display:flex;flex-wrap:wrap;gap:14px;align-items:center;margin:16px 0">
  <label>Simulation run <select v-model="runId"><option v-for="r in runs" :key="r.runId" :value="r.runId">{{new Date(r.startedAt).toLocaleString()}} · {{r.sampleCount}} samples · {{r.faultEventCount}} faults</option></select></label>
  <label>Samples per signal <select v-model.number="limit"><option :value="500">500</option><option :value="2000">2000</option><option :value="5000">5000</option></select></label>
  <button class="secondary" type="button" @click="loadRuns">Refresh runs</button>
 </div>
 <details><summary>Choose signals ({{selected.length}}/6)</summary>
  <div style="display:flex;flex-wrap:wrap;gap:10px;padding:12px 0">
   <label v-for="s in signals" :key="s" style="white-space:nowrap"><input type="checkbox" :checked="selected.includes(s)" :disabled="!selected.includes(s)&&selected.length>=6" @change="toggle(s)"/> {{s}}</label>
  </div>
 </details>
 <p v-if="loading" role="status">Loading historical measurements…</p>
 <p v-if="error" role="alert" style="color:#b91c1c">{{error}}</p>
 <template v-if="allTimes.length">
  <div style="display:flex;gap:12px;align-items:center;flex-wrap:wrap;margin:20px 0">
   <button type="button" class="secondary" @click="playing=!playing">{{playing?'Pause':'Play'}} replay</button>
   <input type="range" min="0" :max="maxIndex" v-model.number="progress" aria-label="Shared simulation time" style="flex:1;min-width:180px"/>
   <label>Speed <select v-model.number="speed"><option :value="1">1×</option><option :value="3">3×</option><option :value="10">10×</option></select></label>
   <strong>{{cursorTime.toFixed(4)}} h</strong>
  </div>
  <div v-for="(s,i) in available" :key="s" style="margin:20px 0;border-top:1px solid #d1d5db;padding-top:12px">
   <strong :style="{color:palette[i%palette.length]}">{{s}}</strong> · {{series[s].length}} points · Current: {{currentValue(s)?.value.toFixed(4)??'—'}}
   <svg v-if="plot(s)" viewBox="0 0 780 285" :aria-label="s+' historical trend'" role="img" style="display:block;width:100%;max-height:280px">
    <text x="400" y="278" text-anchor="middle" font-size="14" font-weight="600" fill="currentColor">Simulation time (hours)</text>
    <text x="16" y="125" text-anchor="middle" transform="rotate(-90 16 125)" font-size="14" font-weight="600" fill="currentColor">Signal value ({{s}})</text>
    <line x1="55" y1="210" x2="745" y2="210" stroke="currentColor" opacity=".35"/>
    <line x1="55" y1="40" x2="55" y2="210" stroke="currentColor" opacity=".35"/>
    <path :d="plot(s)!.path" fill="none" :stroke="palette[i%palette.length]" stroke-width="2"/>
    <line v-for="f in visibleFaults" :key="f.event_id" :x1="x(f.simulation_time_hours)" y1="40" :x2="x(f.simulation_time_hours)" y2="210" :stroke="f.action==='inject'?'#d97706':'#7c3aed'" stroke-dasharray="5 4" stroke-width="2"/>
    <line :x1="x(cursorTime)" y1="40" :x2="x(cursorTime)" y2="210" stroke="#dc2626" stroke-width="2"/>
    <text x="58" y="32" font-size="13" fill="currentColor">{{plot(s)!.max.toFixed(3)}}</text>
    <text x="58" y="204" font-size="13" fill="currentColor">{{plot(s)!.min.toFixed(3)}}</text>
    <text x="55" y="235" font-size="13" fill="currentColor">{{timeBounds.min.toFixed(3)}} h</text>
    <text x="745" y="235" text-anchor="end" font-size="13" fill="currentColor">{{timeBounds.max.toFixed(3)}} h</text>
   </svg>
  </div>
  <h3>Run-level fault timeline</h3>
  <p>Orange = injection; purple = clearing; red = shared replay cursor. Fault events are temporal markers, not verified causal attribution.</p>
  <p v-if="!faults.length">No recorded fault events for this run.</p>
  <div v-for="f in faults" :key="f.event_id" style="padding:8px 0;border-bottom:1px solid #d1d5db">{{f.simulation_time_hours.toFixed(4)}} h · {{f.action}} · {{f.fault_id}} · {{f.target}}</div>
  <p style="font-size:12px;opacity:.75;margin-top:12px">For large runs, each signal shows the most recent requested samples. Charts share simulation time but do not interpolate values between measurements.</p>
 </template>
 <p v-else-if="!loading&&!error">Choose a run and signals with recorded measurements.</p>
</section>
</template>
