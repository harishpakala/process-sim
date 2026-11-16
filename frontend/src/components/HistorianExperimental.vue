<script setup lang="ts">
import { computed, ref } from 'vue'

type HistorianResponse = {
 mode: string
 plan: {
  domain: string
  engineering_function: string
  run_id: string
  start_simulation_seconds: number | null
  end_simulation_seconds: number | null
  shacl_evidence: unknown
 }
 result: {
  engineeringFunction?: string
  mapping?: {operational_signal?: string; asset_identifier?: string}
  observationCount?: number
  observations?: Array<{simulationTimeHours:number; value:number; observedAt:string}>
  [key: string]: unknown
 }
}
const question = ref('')
const busy = ref(false)
const error = ref('')
const response = ref<HistorianResponse | null>(null)

async function run() {
 error.value = ''
 response.value = null
 if (question.value.trim().length < 5) {
  error.value = 'Enter a historian question.'
  return
 }
 busy.value = true
 try {
  const r = await fetch('/api/ai/vtkg/historian/experimental/answer', {
   method: 'POST',
   headers: {'Content-Type':'application/json'},
   body: JSON.stringify({question: question.value.trim()})
  })
  const body = await r.json()
  if (!r.ok) throw new Error(body.error || 'Experimental historian query failed')
  response.value = body as HistorianResponse
 } catch (e) {
  error.value = e instanceof Error ? e.message : String(e)
 } finally {
  busy.value = false
 }
}
const experimentalChart = computed(() => {
 const samples = (response.value?.result?.observations ?? [])
  .filter(p => Number.isFinite(p.simulationTimeHours) && Number.isFinite(p.value))
  .map(p => ({seconds:p.simulationTimeHours * 3600,value:p.value}))
  .sort((a,b) => a.seconds - b.seconds)
 if (!samples.length) return null
 const left=72,right=728,top=18,bottom=242
 const minX=samples[0]!.seconds,maxX=samples[samples.length-1]!.seconds
 const minV=Math.min(...samples.map(p=>p.value)),maxV=Math.max(...samples.map(p=>p.value))
 const pad=(maxV-minV || Math.max(Math.abs(minV),1))*0.08
 const low=minV-pad,high=maxV+pad
 const x=(v:number)=>left+(v-minX)/(maxX-minX||1)*(right-left)
 const y=(v:number)=>bottom-(v-low)/(high-low)*(bottom-top)
 return {points:samples.map(p=>({...p,x:x(p.seconds),y:y(p.value)})),
  polyline:samples.map(p=>`${x(p.seconds)},${y(p.value)}`).join(' '),
  left,right,top,bottom,
  xTicks:[0,1,2,3,4].map(i=>({x:left+(right-left)*i,label:(minX+(maxX-minX)*i/4).toFixed(1)})),
  yTicks:[0,1,2,3,4].map(i=>({y:bottom-(bottom-top)*i/4,label:(low+(high-low)*i/4).toFixed(2)}))}
})
</script>

<template>
 <section class="panel">
  <div class="panel-title"><h2>Historian Experimental — Natural Language</h2><span class="pill">ISOLATED EXPERIMENT</span></div>
  <p>Ask a free-text historian question. The experiment validates SHACL schema evidence and reuses the existing VTKG Historian executor. Existing Historian Queries remain unchanged.</p>
  <p>For this first prototype, include DEXPI or ECAD, exactly one LocalID, and the full simulation run UUID. Time bounds are optional.</p>
  <label for="historian-experiment-question">Historian question</label>
  <textarea id="historian-experiment-question" v-model="question" rows="4" style="width:100%;margin-top:8px" placeholder="Get historian values for the DEXPI InstrumentationFunction with LocalID FI_101 for simulation run 00000000-0000-0000-0000-000000000001, between simulation seconds 100 and 300." />
  <div style="margin-top:12px"><button class="primary" :disabled="busy" @click="run">{{busy ? 'Running…' : 'Run experimental query'}}</button></div>
  <p v-if="error" role="alert" style="color:#b91c1c">{{error}}</p>
  <template v-if="response">
   <h3>Validated query plan</h3>
   <pre style="overflow:auto;white-space:pre-wrap">{{JSON.stringify(response.plan, null, 2)}}</pre>
   <h3>Historian result</h3>
    <div v-if="experimentalChart" class="vtkg-chart">
     <div class="vtkg-chart-scroll">
      <svg viewBox="0 0 780 295" role="img" :aria-label="'Historian time-series graph for ' + response.result.engineeringFunction || response.plan.engineering_function">
       <g stroke="currentColor" opacity="0.22" stroke-width="1">
        <line v-for="tick in experimentalChart.yTicks" :key="'grid-'+tick.y" :x1="experimentalChart.left" :x2="experimentalChart.right" :y1="tick.y" :y2="tick.y" />
       </g>
       <g stroke="currentColor" stroke-width="1.5">
        <line :x1="experimentalChart.left" :y1="experimentalChart.top" :x2="experimentalChart.left" :y2="experimentalChart.bottom" />
        <line :x1="experimentalChart.left" :y1="experimentalChart.bottom" :x2="experimentalChart.right" :y2="experimentalChart.bottom" />
       </g>
       <g fill="currentColor" font-size="12">
        <text v-for="tick in experimentalChart.xTicks" :key="'x-'+tick.x" :x="tick.x" y="261" text-anchor="middle">{{tick.label}}</text>
        <text v-for="tick in experimentalChart.yTicks" :key="'y-'+tick.y" x="64" :y="tick.y+4" text-anchor="end">{{tick.label}}</text>
        <text x="400" y="287" text-anchor="middle">Simulation time (seconds)</text>
        <text x="16" y="132" text-anchor="middle" transform="rotate(-90 16 132)">Recorded value</text>
       </g>
       <polyline v-if="experimentalChart.points.length > 1" :points="experimentalChart.polyline" fill="none" stroke="#38bdf8" stroke-width="2.5" stroke-linejoin="round" stroke-linecap="round" />
       <circle v-for="(point,i) in experimentalChart.points" :key="i" :cx="point.x" :cy="point.y" r="2.5" fill="#38bdf8">
        <title>{{point.seconds.toFixed(2)}} s · {{point.value}}</title>
       </circle>
      </svg>
     </div>
    </div>
    <p v-else class="subdued">No numeric observations available to graph.</p>
   <p>Function: {{response.result.engineeringFunction || response.plan.engineering_function}} · Signal: {{response.result.mapping?.operational_signal || '—'}} · Observations: {{response.result.observationCount ?? response.result.observations?.length ?? 0}}</p>
   <table v-if="response.result.observations?.length">
    <thead><tr><th>Simulation time (hours)</th><th>Value</th><th>Observed at</th></tr></thead>
    <tbody><tr v-for="(sample, index) in response.result.observations" :key="index"><td>{{sample.simulationTimeHours}}</td><td>{{sample.value}}</td><td>{{sample.observedAt}}</td></tr></tbody>
   </table>
   <p v-else>No observations returned.</p>
  </template>
 </section>
</template>
