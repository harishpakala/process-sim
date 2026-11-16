<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'

type HistorianResponse = {
 mode: string
 intent?: string
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

type FunctionOption = {engineering_function: string; operational_signal: string; sample_count: number}
const runs = ref<string[]>([])
const selectedRun = ref('')
const selectedDomain = ref<'DEXPI' | 'ECAD'>('DEXPI')
const functions = ref<FunctionOption[]>([])
const selectedLocalId = ref('')
const discoveryBusy = ref(false)
const discoveryError = ref('')
const startSeconds = ref('')
const endSeconds = ref('')
let lastGeneratedQuestion = ''

async function loadRuns() {
 discoveryError.value = ''
 discoveryBusy.value = true
 try {
  const r = await fetch('/api/ai/vtkg/historian/runs')
  const data = await r.json()
  if (!r.ok) throw new Error(data.error || 'Run discovery failed')
  runs.value = data.runs
 } catch (e) {
  discoveryError.value = e instanceof Error ? e.message : String(e)
 } finally {
  discoveryBusy.value = false
 }
}

async function loadFunctions() {
 selectedLocalId.value = ''
 functions.value = []
 discoveryError.value = ''
 if (!selectedRun.value) return
 discoveryBusy.value = true
 try {
  const url = '/api/ai/vtkg/historian/functions?run_id=' +
    encodeURIComponent(selectedRun.value) + '&domain=' + encodeURIComponent(selectedDomain.value)
  const r = await fetch(url)
  const data = await r.json()
  if (!r.ok) throw new Error(data.error || 'LocalID discovery failed')
  functions.value = data.functions
 } catch (e) {
  discoveryError.value = e instanceof Error ? e.message : String(e)
 } finally {
  discoveryBusy.value = false
 }
}

function generatedQuestion(): string {
 if (!selectedRun.value || !selectedLocalId.value) return ''
 const entity = selectedDomain.value === 'DEXPI' ? 'DEXPI InstrumentationFunction' : 'ECAD Device'
 const interval = startSeconds.value !== '' && endSeconds.value !== ''
  ? ` between simulation seconds ${startSeconds.value} and ${endSeconds.value}`
  : startSeconds.value !== '' ? ` from simulation second ${startSeconds.value} onward`
  : endSeconds.value !== '' ? ` up to simulation second ${endSeconds.value}`
  : ' for all simulation times'
 return `Get historian values for the ${entity} with LocalID ${selectedLocalId.value} for simulation run ${selectedRun.value},${interval}.`
}
function updateGeneratedQuestion() {
 const next = generatedQuestion()
 if (question.value === '' || question.value === lastGeneratedQuestion) {
  question.value = next
 }
 lastGeneratedQuestion = next
}
watch([selectedRun, selectedDomain], () => { void loadFunctions() })
watch([selectedRun, selectedDomain, selectedLocalId, startSeconds, endSeconds], updateGeneratedQuestion)
onMounted(() => { void loadRuns() })


async function run() {
 error.value = ''
 response.value = null
 if (question.value.trim().length < 5) {
  error.value = 'Enter a historian question.'
  return
 }
 busy.value = true
 try {
  const context = selectedRun.value && selectedLocalId.value ? {
   domain: selectedDomain.value, engineering_function: selectedLocalId.value,
   run_id: selectedRun.value,
   start_simulation_seconds: startSeconds.value === '' ? null : Number(startSeconds.value),
   end_simulation_seconds: endSeconds.value === '' ? null : Number(endSeconds.value)
  } : undefined
  const r = await fetch('/api/ai/unified/experimental/answer', {
   method: 'POST',
   headers: {'Content-Type':'application/json'},
   body: JSON.stringify({question: question.value.trim(), ...(context ? {context} : {})})
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
  <div class="panel-title"><h2>Unified Query Experimental — Natural Language</h2><span class="pill">ISOLATED EXPERIMENT</span></div>
  <p>Ask an engineering or Historian question. The shared experimental router dispatches to the existing SHACL-grounded engineering planner or VTKG Historian executor. Existing query pages remain unchanged.</p>
  <p>For Historian questions, select a run, domain, and LocalID or include them explicitly in the question. Time bounds are optional. Engineering questions can be entered directly without selections.</p>
  <div class="experiment-fields">
   <div class="experiment-field"><label for="historian-experiment-run">Simulation run</label>
   <select id="historian-experiment-run" v-model="selectedRun" :disabled="discoveryBusy">
    <option value="">Select simulation run</option>
    <option v-for="runId in runs" :key="runId" :value="runId">{{runId}}</option>
   </select>
   <button class="experiment-refresh" type="button" :disabled="discoveryBusy" @click="loadRuns">Refresh runs</button></div>
   <div class="experiment-field"><label for="historian-experiment-domain">Engineering domain</label>
   <select id="historian-experiment-domain" v-model="selectedDomain">
    <option value="DEXPI">DEXPI</option><option value="ECAD">ECAD</option>
   </select></div>
   <div class="experiment-field"><label for="historian-experiment-localid">LocalID (verified for selected run)</label>
   <select id="historian-experiment-localid" v-model="selectedLocalId" :disabled="!selectedRun || discoveryBusy">
    <option value="">Select LocalID</option>
    <option v-for="item in functions" :key="item.engineering_function" :value="item.engineering_function">{{item.engineering_function}}</option>
   </select></div>
   <div class="experiment-field"><label for="historian-experiment-start">Start simulation seconds (optional)</label>
   <input id="historian-experiment-start" v-model="startSeconds" type="number" min="0" step="any" placeholder="No lower bound" /></div>
   <div class="experiment-field"><label for="historian-experiment-end">End simulation seconds (optional)</label>
   <input id="historian-experiment-end" v-model="endSeconds" type="number" min="0" step="any" placeholder="No upper bound" /></div>
   <p class="experiment-wide" v-if="discoveryError" role="alert">{{discoveryError}}</p>
   <p class="subdued experiment-wide">Selections help compose the question for testing. Only the editable natural-language question is submitted to the experimental planner.</p>
  </div>
  <label class="experiment-question-label" for="historian-experiment-question">Historian question</label>
  <textarea id="historian-experiment-question" v-model="question" rows="4" class="experiment-question" placeholder="Get historian values for the DEXPI InstrumentationFunction with LocalID FI_101 for simulation run 00000000-0000-0000-0000-000000000001, between simulation seconds 100 and 300." />
  <div style="margin-top:12px"><button class="primary" :disabled="busy" @click="run">{{busy ? 'Running…' : 'Run experimental query'}}</button></div>
  <p v-if="error" role="alert" style="color:#b91c1c">{{error}}</p>
  <template v-if="response">
   <h3>{{response.intent === "engineering_query" ? "Engineering result" : "Historian result"}}</h3>
   <template v-if="response.intent === 'engineering_query'">
    <pre style="overflow:auto;white-space:pre-wrap">{{JSON.stringify(response.result, null, 2)}}</pre>
   </template>
   <template v-else>
    <div v-if="experimentalChart" class="vtkg-chart">
     <div class="vtkg-chart-scroll">
      <svg viewBox="0 0 780 295" role="img" :aria-label="'Historian time-series graph for ' + (response.result.engineeringFunction || response.plan.engineering_function)">
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
   </template>
   <h3>Validated query plan</h3>
   <pre style="overflow:auto;white-space:pre-wrap">{{JSON.stringify(response.plan, null, 2)}}</pre>
  </template>
 </section>
</template>

<style scoped>
.experiment-fields {
 display: grid;
 grid-template-columns: repeat(2, minmax(0, 1fr));
 gap: 16px;
 margin: 20px 0;
}
.experiment-field { display: flex; flex-direction: column; gap: 8px; min-width: 0; }
.experiment-field label, .experiment-question-label { display: block; font-size: 13px; color: #c7d9ea; font-weight: 600; }
.experiment-field select, .experiment-field input, .experiment-question {
 display: block; width: 100%; max-width: 100%; min-width: 0;
 background: #0c192a; border: 1px solid #334a62; border-radius: 8px;
 color: #eaf4ff; padding: 10px; font: inherit;
}
.experiment-refresh { align-self: flex-start; padding: 7px 12px; border: 1px solid #334a62; border-radius: 8px; background: #172d42; color: #eaf4ff; }
.experiment-wide { grid-column: 1 / -1; }
.experiment-question { margin-top: 8px; resize: vertical; }
@media (max-width: 700px) { .experiment-fields { grid-template-columns: minmax(0, 1fr); } }
</style>
