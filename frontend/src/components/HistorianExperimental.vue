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
const queryStyle = ref('historian')
const queryStyles = [
 {value:'historian', label:'Historian values'},
 {value:'show', label:'Show readings'},
 {value:'plot', label:'Plot trend'},
 {value:'behave', label:'How did it behave?'},
 {value:'chart', label:'Chart measurements'}
]
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
 const subject = `${entity} with LocalID ${selectedLocalId.value}`
 const run = `simulation run ${selectedRun.value}`
 const time = interval.trim()
 switch (queryStyle.value) {
  case 'show': return `Show historical readings for ${subject} in ${run}, ${time}.`
  case 'plot': return `Plot recorded measurements of ${subject} for ${run}, ${time}.`
  case 'behave': return `How did ${subject} behave during ${run}, ${time}?`
  case 'chart': return `Chart historical measurements for ${subject} in ${run}, ${time}.`
  default: return `Get historian values for ${subject} for ${run}, ${time}.`
 }
}
function updateGeneratedQuestion() {
 const next = generatedQuestion()
 if (question.value === '' || question.value === lastGeneratedQuestion) {
  question.value = next
 }
 lastGeneratedQuestion = next
}
watch([selectedRun, selectedDomain], () => { void loadFunctions() })
watch([selectedRun, selectedDomain, selectedLocalId, startSeconds, endSeconds, queryStyle], updateGeneratedQuestion)
onMounted(() => { void loadRuns() })


async function run() {
 error.value = ''
 response.value = null
 if (question.value.trim().length < 5) {
  error.value = 'Enter a question to continue.'
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
  <div class="panel-title"><div><h2>Ask DTWise — Simulation Historian / VTKG</h2><p>Benchmark stage 09 · B33–B37 · parameterized simulation test cases</p></div><span class="pill">PREVIEW</span></div>
  <p>Ask about engineering information or explore recorded simulation data in your own words.</p>
  <p>Need a hand getting started? Choose a simulation run and instrument below, then pick a suggested way to ask. You can also type your own question at any time.</p>
  <div class="experiment-fields">
   <div class="experiment-field"><label for="historian-experiment-run">Simulation run (optional)</label>
   <select id="historian-experiment-run" v-model="selectedRun" :disabled="discoveryBusy">
    <option value="">Select simulation run</option>
    <option v-for="runId in runs" :key="runId" :value="runId">{{runId}}</option>
   </select>
   <button class="experiment-refresh" type="button" :disabled="discoveryBusy" @click="loadRuns">Refresh runs</button></div>
   <div class="experiment-field"><label for="historian-experiment-domain">Source (optional)</label>
   <select id="historian-experiment-domain" v-model="selectedDomain">
    <option value="DEXPI">DEXPI</option><option value="ECAD">ECAD</option>
   </select></div>
   <div class="experiment-field"><label for="historian-experiment-localid">Instrument / LocalID (optional)</label>
   <select id="historian-experiment-localid" v-model="selectedLocalId" :disabled="!selectedRun || discoveryBusy">
    <option value="">Select LocalID</option>
    <option v-for="item in functions" :key="item.engineering_function" :value="item.engineering_function">{{item.engineering_function}}</option>
   </select></div>
   <div class="experiment-field"><label for="historian-experiment-style">How would you like to ask?</label>
   <select id="historian-experiment-style" v-model="queryStyle"><option v-for="style in queryStyles" :key="style.value" :value="style.value">{{style.label}}</option></select></div>
   <div class="experiment-field"><label for="historian-experiment-start">From simulation second (optional)</label>
   <input id="historian-experiment-start" v-model="startSeconds" type="number" min="0" step="any" placeholder="No lower bound" /></div>
   <div class="experiment-field"><label for="historian-experiment-end">To simulation second (optional)</label>
   <input id="historian-experiment-end" v-model="endSeconds" type="number" min="0" step="any" placeholder="No upper bound" /></div>
   <p class="experiment-wide" v-if="discoveryError" role="alert">{{discoveryError}}</p>
   <p class="subdued experiment-wide">These suggestions are here to help, not to limit what you can ask. Edit the question freely. Leave the time fields empty to see the complete available run.</p>
  </div>
  <p class="subdued">Benchmark configuration: {{queryStyles.findIndex(item => item.value === queryStyle) + 33 < 38 ? 'B' + (queryStyles.findIndex(item => item.value === queryStyle) + 33) : '—'}} (question-style grouping, provisional) · {{selectedDomain}} · run {{selectedRun || 'not selected'}} · LocalID {{selectedLocalId || 'not selected'}} · {{startSeconds || 'start'}} to {{endSeconds || 'end'}} simulation seconds. Each run, instrument and time-window selection is a distinct test case. The B33–B37 style mapping is provisional until checked against the original VTKG benchmark definitions.</p>
  <label class="experiment-question-label" for="historian-experiment-question">Your question</label>
  <textarea id="historian-experiment-question" v-model="question" rows="4" class="experiment-question" placeholder="Ask a question about an instrument, simulation run, or engineering relationship…" />
  <div style="margin-top:12px"><button class="primary" :disabled="busy" @click="run">{{busy ? 'Finding answer…' : 'Ask DTWise'}}</button></div>
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
   <h3>Query details</h3>
   <details><summary>View how DTWise interpreted your question</summary><pre style="overflow:auto;white-space:pre-wrap">{{JSON.stringify(response.plan, null, 2)}}</pre></details>
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
