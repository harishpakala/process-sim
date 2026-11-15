<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'

type DtwiseResult = {
 question: string; mode: string; sparql: string; executed: boolean;
 graph_mode: string; answer: Record<string, unknown>; plan: unknown
}
type BenchmarkQuestion = {id:string;category:string;question:string;version:string}
const benchmarkQuestions = ref<BenchmarkQuestion[]>([])
const category = ref('')
const benchmarkId = ref('')
const manifestError = ref('')
const selectableQuestions = computed(() => benchmarkQuestions.value.filter(q => q.category !== 'multi_domain_multi_hop'))
const categories = computed(() => [...new Set(selectableQuestions.value.map(q => q.category))])
const categoryQuestions = computed(() => selectableQuestions.value.filter(q => q.category === category.value))
const selectedBenchmark = computed(() => benchmarkQuestions.value.find(q => q.id === benchmarkId.value))
function selectCategory(next:string) {
 category.value = next
 benchmarkId.value = ''
}
function selectBenchmark(id:string) {
 benchmarkId.value = id
 const item = benchmarkQuestions.value.find(q => q.id === id)
 if (item) question.value = item.question
}
onMounted(async () => {
 try {
  const response = await fetch('/dtwise-benchmark-manifest.json', {cache:'no-store'})
  if (!response.ok) throw new Error('Benchmark manifest unavailable')
  const data:unknown = await response.json()
  if (!Array.isArray(data) || !data.every(item => item && typeof item.id === 'string' && typeof item.category === 'string' && typeof item.question === 'string'))
   throw new Error('Invalid benchmark manifest')
  benchmarkQuestions.value = data as BenchmarkQuestion[]
 } catch(e) { manifestError.value = e instanceof Error ? e.message : String(e) }
})
const verifiedExamples = [
 {id:'FI101_OPCUA_SIGNAL',label:'DEXPI → OPCUAConnectivity · FI_101 SignalName',question:'Find the OPCUAConnectivity SignalName for DEXPI InstrumentationFunction with localId FI_101, joining the DEXPI hasAssetIdentifier to the OPCUAConnectivity hasAssetIdentifier.'}
]
const verifiedExampleId = ref('')
function selectVerifiedExample(id:string) {
 verifiedExampleId.value = id
 const example = verifiedExamples.find(item => item.id === id)
 if (example) {
  question.value = example.question
  benchmarkId.value = ''
  result.value = null
  error.value = ''
 }
}
const joinAssistanceEnabled = ref(false)
const joinKeyConfirmed = ref(false)
const verifiedJoinKey = 'hasAssetIdentifier'
const shortFi101Question = 'Find the OPCUAConnectivity SignalName for DEXPI InstrumentationFunction with localId FI_101.'
const explicitFi101Question = 'Find the OPCUAConnectivity SignalName for DEXPI InstrumentationFunction with localId FI_101, joining the DEXPI hasAssetIdentifier to the OPCUAConnectivity hasAssetIdentifier.'
const joinAssistanceApplicable = computed(() => question.value.trim() === shortFi101Question)
const submittedDtwiseQuestion = computed(() =>
 joinAssistanceEnabled.value && joinKeyConfirmed.value && joinAssistanceApplicable.value
  ? explicitFi101Question : question.value.trim()
)
function useShortFi101Question() {
 question.value = shortFi101Question
 joinAssistanceEnabled.value = true
 joinKeyConfirmed.value = false
 benchmarkId.value = ''
 verifiedExampleId.value = ''
 result.value = null
 error.value = ''
}
const question = ref('')
const busy = ref(false)
const error = ref('')
const result = ref<DtwiseResult | null>(null)
type ResultRow = { entity?: unknown; value?: unknown; uri?: unknown; label?: unknown; [key: string]: unknown }
const rowKind = computed(() => Array.isArray(result.value?.answer?.values) ? 'values' :
                            Array.isArray(result.value?.answer?.entities) ? 'entities' : 'none')
const rows = computed<ResultRow[]>(() => {
 const answer = result.value?.answer
 const items = rowKind.value === 'values' ? answer?.values :
               rowKind.value === 'entities' ? answer?.entities : []
 return (Array.isArray(items) ? items : []).map(item =>
  item !== null && typeof item === 'object' && !Array.isArray(item)
   ? item as ResultRow : {value: item})
})
const primaryColumn = computed(() => rowKind.value === 'entities' ? 'Entity label' : 'Signal Name / Value')
const secondaryColumn = computed(() => rowKind.value === 'entities' ? 'Entity URI' : 'Signal Mapping / Entity')
function primaryValue(row: ResultRow): unknown {
 return rowKind.value === 'entities' ? row.label : row.value
}
function secondaryValue(row: ResultRow): unknown {
 return rowKind.value === 'entities' ? row.uri : row.entity
}
function display(value: unknown): string {
 return typeof value === 'string' ? value : value == null ? '—' : JSON.stringify(value)
}
function entityLabel(value: unknown): string {
 const text = display(value)
 if (typeof value !== 'string') return text
 const clean = text.replace(/^<|>$/g, '')
 const tail = clean.split('/').filter(Boolean).pop()
 return tail || clean
}
async function ask() {
 result.value = null
 error.value = ''
 if (joinAssistanceEnabled.value && !joinAssistanceApplicable.value) {
  error.value = 'Join assistance is currently supported only for the exact FI_101 DEXPI → OPCUAConnectivity question.'
  return
 }
 if (joinAssistanceEnabled.value && !joinKeyConfirmed.value) {
  error.value = 'Confirm the hasAssetIdentifier join key before submitting.'
  return
 }
 const text = submittedDtwiseQuestion.value
 if (text.length < 5 || text.length > 1000) {
  error.value = 'Enter a question between 5 and 1000 characters'
  return
 }
 busy.value = true
 try {
  const response = await fetch('/api/ai/dtwise/answer', {
   method: 'POST',
   headers: {'Content-Type': 'application/json'},
   body: JSON.stringify({question: text})
  })
  const data = await response.json()
  if (!response.ok) throw new Error(data.error || 'DTwise query failed')
  result.value = data as DtwiseResult
 } catch (e) {
  error.value = e instanceof Error ? e.message : String(e)
 } finally {
  busy.value = false
 }
}

type HistorianResult = {engineeringFunction:string;mapping:{operational_signal:string;asset_identifier:string};observationCount:number;truncated:boolean;observations:Array<{simulationTimeHours:number;value:number;observedAt:string}>}
const hRuns = ref<string[]>([]), hRun = ref(''), hDomain = ref('DEXPI'), hFunction = ref(''), hQuestion = ref('')
const hFunctions = ref<Array<{engineering_function:string;operational_signal:string;sample_count:number}>>([])
const hStart = ref(''), hEnd = ref(''), hError = ref(''), hBusy = ref(false), hResult = ref<HistorianResult|null>(null)
async function hLoadRuns() {
 try {
  const r = await fetch('/api/ai/vtkg/historian/runs'), data = await r.json()
  if (!r.ok) throw Error(data.error || 'Run discovery failed')
  hRuns.value = data.runs
 } catch(e) { hError.value = String(e) }
}
async function hLoadFunctions() {
 hFunction.value = ''; hQuestion.value = ''; hFunctions.value = []; hResult.value = null
 if (!hRun.value) return
 try {
  const r = await fetch('/api/ai/vtkg/historian/functions?run_id=' + encodeURIComponent(hRun.value) + '&domain=' + encodeURIComponent(hDomain.value)), data = await r.json()
  if (!r.ok) throw Error(data.error || 'Function discovery failed')
  hFunctions.value = data.functions
 } catch(e) { hError.value = String(e) }
}
function hSelectFunction() {
 hQuestion.value = hFunction.value ? `For the ${hDomain.value} engineering element with LocalId ${hFunction.value}, identify its corresponding OPCUAConnectivity SignalName using the shared hasAssetIdentifier, then retrieve all recorded values from TimescaleDB.` : ''
 hResult.value = null
}
async function hAsk() {
 hResult.value = null; hError.value = ''
 const start = hStart.value === '' ? null : Number(hStart.value)
 const end = hEnd.value === '' ? null : Number(hEnd.value)
 if ((start !== null && (!Number.isFinite(start) || start < 0)) || (end !== null && (!Number.isFinite(end) || end < 0)) || (start !== null && end !== null && start > end)) {
  hError.value = 'Invalid simulation-time interval'; return
 }
 hBusy.value = true
 try {
  const r = await fetch('/api/ai/vtkg/historian/answer', {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({
   question:hQuestion.value,engineering_function:hFunction.value,run_id:hRun.value,domain:hDomain.value,start_simulation_seconds:start,end_simulation_seconds:end
  })})
  const data = await r.json()
  if (!r.ok) throw Error(data.error || 'Historian query failed')
  hResult.value = data
 } catch(e) { hError.value = String(e) }
 finally { hBusy.value = false }
}
const hChart = computed(() => {
 const samples = (hResult.value?.observations ?? [])
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
onMounted(hLoadRuns)
</script>

<template>
 <div style="display:grid;gap:16px">
  <section class="panel">
   <div class="panel-title">
    <div><h2>TEP NEXUS — DTwise Engineering Query</h2><p>Frozen DTwise planner · read-only GraphDB execution</p></div>
   </div>
   <div class="custom-query">
    <label for="benchmark-category">Benchmark category</label>
    <select id="benchmark-category" :value="category" @change="selectCategory(($event.target as HTMLSelectElement).value)">
     <option value="">Select a category</option>
     <option v-for="item in categories" :key="item" :value="item">{{item}}</option>
    </select>
    <label for="benchmark-question">Benchmark question</label>
    <select id="benchmark-question" :value="benchmarkId" :disabled="!category" @change="selectBenchmark(($event.target as HTMLSelectElement).value)">
     <option value="">Select a question</option>
     <option v-for="item in categoryQuestions" :key="item.id" :value="item.id">{{item.id}} — {{item.question}}</option>
    </select>
    <p v-if="manifestError" role="status" style="color:#b45309">{{manifestError}}. Manual questions remain available.</p>
    <p v-if="selectedBenchmark?.id === 'B27'" role="status" style="color:#b45309">B27 was previously rejected because a required join key was not established.</p>
    <p v-if="selectedBenchmark && Number(selectedBenchmark.id.slice(1)) >= 48" class="subdued">This question is in the manifest; its live pass/fail status has not been confirmed here.</p>
    <p class="subdued">Benchmark questions are drawn from the B01–B60 manifest; untested multi-domain multi-hop cases are excluded. Inclusion does not mean every listed question passed validation.</p>
    <label for="dtwise-verified-example">Additional verified cross-domain query (separate from frozen benchmark)</label>
    <select id="dtwise-verified-example" :value="verifiedExampleId" @change="selectVerifiedExample(($event.target as HTMLSelectElement).value)">
     <option value="">Select a verified cross-domain example</option>
     <option v-for="item in verifiedExamples" :key="item.id" :value="item.id">{{item.label}}</option>
    </select>
    <p class="subdued">FI_101 → XMEAS1 was confirmed in a CLI GraphDB execution supplied by the operator. This example does not modify the frozen B01–B60 manifest.</p>
    <div class="join-assistance">
     <button type="button" @click="useShortFi101Question">Use short FI_101 question with join assistance</button>
     <label for="dtwise-join-assistance"><input id="dtwise-join-assistance" type="checkbox" v-model="joinAssistanceEnabled" /> Enable explicit join assistance (FI_101 only)</label>
     <template v-if="joinAssistanceEnabled">
      <p class="subdued">Supported only for the exact short FI_101 question. No automatic join inference; the frozen planner remains unchanged.</p>
      <p v-if="!joinAssistanceApplicable" role="alert" style="color:#b45309">This question does not match the verified FI_101 short question. Disable assistance or use the button above.</p>
      <label for="dtwise-join-confirm"><input id="dtwise-join-confirm" type="checkbox" v-model="joinKeyConfirmed" :disabled="!joinAssistanceApplicable" /> I confirm joining DEXPI {{verifiedJoinKey}} to OPCUAConnectivity {{verifiedJoinKey}}</label>
      <label for="dtwise-expanded-question">Question submitted to frozen DTwise (read-only)</label>
      <textarea id="dtwise-expanded-question" :value="submittedDtwiseQuestion" readonly rows="4" />
     </template>
    </div>
    <label for="dtwise-question">Engineering question (editable)</label>
    <textarea id="dtwise-question" v-model="question" maxlength="1000" rows="4"
      placeholder="List OPCUAconnectivity SignalNames." @keydown.ctrl.enter="ask" />
    <p class="subdued">Results come from the frozen DTwise pipeline. No alternative planner or automatic fallback.</p>
   </div>
   <button class="primary" type="button" :disabled="busy || question.trim().length < 5 || (joinAssistanceEnabled && (!joinAssistanceApplicable || !joinKeyConfirmed))" @click="ask">
    {{busy ? 'Executing DTwise query…' : 'Ask DTwise'}}
   </button>
   <p v-if="error" role="alert" style="color:#b45309">{{error}}</p>
  </section>
  <section class="panel">
   <div class="panel-title"><div><h2>VTKG — Semantic historian query</h2><p>DEXPI / ECAD → OPCUAConnectivity → TimescaleDB · read-only</p></div></div>
   <form class="custom-query" @submit.prevent="hAsk">
    <label for="h-run">Simulation run (required; TimescaleDB)</label>
    <select id="h-run" v-model="hRun" required @change="hLoadFunctions"><option value="">Select run</option><option v-for="run in hRuns" :key="run" :value="run">{{run}}</option></select>
    <button type="button" @click="hLoadRuns">Refresh runs</button>
    <label for="h-domain">Engineering domain</label>
    <select id="h-domain" v-model="hDomain" @change="hLoadFunctions"><option value="DEXPI">DEXPI</option><option value="ECAD">ECAD</option></select>
    <label for="h-function">LocalId (verified for selected run)</label>
    <select id="h-function" v-model="hFunction" required :disabled="!hRun" @change="hSelectFunction"><option value="">Select LocalId</option><option v-for="item in hFunctions" :key="item.engineering_function" :value="item.engineering_function">{{item.engineering_function}}</option></select>
    <label for="h-question">Natural-language question (editable)</label>
    <textarea id="h-question" v-model="hQuestion" required maxlength="1000" rows="4" />
    <label for="h-start">Start simulation seconds (optional)</label>
    <input id="h-start" v-model="hStart" type="number" min="0" step="any" placeholder="No lower bound" />
    <label for="h-end">End simulation seconds (optional)</label>
    <input id="h-end" v-model="hEnd" type="number" min="0" step="any" placeholder="No upper bound" />
    <p class="subdued">Empty bounds retrieve the entire series. One bound applies an open-ended filter. Live hasAssetIdentifier join; physical sensor binding NOT_VERIFIED.</p>
    <button class="primary" type="submit" :disabled="hBusy || !hRun || !hFunction">{{hBusy ? 'Retrieving…' : 'Query historian'}}</button>
    <p v-if="hError" role="alert">{{hError}}</p>
   </form>
   <div v-if="hResult" class="result-section">
    <div v-if="hChart" class="vtkg-chart">
     <div class="vtkg-chart-scroll">
      <svg viewBox="0 0 780 295" role="img" :aria-label="'Historian time-series graph for ' + hResult.engineeringFunction">
       <g stroke="currentColor" opacity="0.22" stroke-width="1">
        <line v-for="tick in hChart.yTicks" :key="'grid-'+tick.y" :x1="hChart.left" :x2="hChart.right" :y1="tick.y" :y2="tick.y" />
       </g>
       <g stroke="currentColor" stroke-width="1.5">
        <line :x1="hChart.left" :y1="hChart.top" :x2="hChart.left" :y2="hChart.bottom" />
        <line :x1="hChart.left" :y1="hChart.bottom" :x2="hChart.right" :y2="hChart.bottom" />
       </g>
       <g fill="currentColor" font-size="12">
        <text v-for="tick in hChart.xTicks" :key="'x-'+tick.x" :x="tick.x" y="261" text-anchor="middle">{{tick.label}}</text>
        <text v-for="tick in hChart.yTicks" :key="'y-'+tick.y" x="64" :y="tick.y+4" text-anchor="end">{{tick.label}}</text>
        <text x="400" y="287" text-anchor="middle">Simulation time (seconds)</text>
        <text x="16" y="132" text-anchor="middle" transform="rotate(-90 16 132)">Recorded value</text>
       </g>
       <polyline v-if="hChart.points.length > 1" :points="hChart.polyline" fill="none" stroke="#38bdf8" stroke-width="2.5" stroke-linejoin="round" stroke-linecap="round" />
       <circle v-for="(point,i) in hChart.points" :key="i" :cx="point.x" :cy="point.y" r="2.5" fill="#38bdf8">
        <title>{{point.seconds.toFixed(2)}} s · {{point.value}}</title>
       </circle>
      </svg>
     </div>
    </div>
    <p v-else class="subdued">No numeric observations available to graph.</p>
   </div>
  </section>
  <section v-if="result" class="panel result-panel">
   <div class="panel-title">
    <div><h2>Engineering result</h2><p>{{result.question}}</p></div>
    <span class="pill">{{result.executed ? 'Executed' : 'Not executed'}}</span>
   </div>
   <div class="result-section">
    <h3>Structured answer</h3>
    <p class="subdued">GraphDB result via frozen DTwise · not independently verified</p>
    <p v-if="result.answer.truncated_possible" role="status">Results may be truncated by the query limit.</p>
    <p v-if="result.answer.count !== undefined">Reported count: {{result.answer.count}}</p>
    <div v-if="rows.length" class="table-scroll">
     <table class="evidence-table">
      <thead><tr><th>#</th><th>{{primaryColumn}}</th><th>{{secondaryColumn}}</th></tr></thead>
      <tbody><tr v-for="(row,i) in rows" :key="i">
       <td>{{i+1}}</td>
       <td class="mono">{{display(primaryValue(row))}}</td>
       <td class="mono"><span :title="display(secondaryValue(row))">{{entityLabel(secondaryValue(row))}}</span>
        <details v-if="secondaryValue(row) != null" class="detail-toggle"><summary>Full URI</summary><span class="full-id">{{display(row.entity)}}</span></details>
       </td>
      </tr></tbody>
     </table>
    </div>
    <p v-else class="subdued">No tabular rows returned. See full structured answer below.</p>
    <details class="detail-toggle"><summary>Full structured answer</summary><pre>{{JSON.stringify(result.answer,null,2)}}</pre></details>
   </div>
   <div class="result-section"><details class="detail-toggle"><summary>Generated SPARQL</summary><pre>{{result.sparql}}</pre></details></div>
   <div class="result-section">
    <h3>Planner and provenance</h3>
    <p class="subdued">Mode: {{result.mode}} · Graph scope: {{result.graph_mode}}</p>
    <details class="detail-toggle"><summary>Frozen planner output</summary><pre>{{JSON.stringify(result.plan,null,2)}}</pre></details>
   </div>
  </section>
 </div>
</template>

<style scoped>
.vtkg-source-trace{display:grid;gap:10px;padding:12px;border:1px solid #334a62;border-radius:8px}.vtkg-source-trace h3{margin:0}.vtkg-trace-steps{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:10px}.vtkg-trace-steps>div{display:grid;align-content:start;gap:6px;padding:10px;border:1px solid #334a62;border-radius:7px}.vtkg-trace-steps span{font-weight:600;overflow-wrap:anywhere}.vtkg-trace-steps small{opacity:.8;overflow-wrap:anywhere}

.vtkg-chart{display:grid;gap:8px}.vtkg-chart h3{margin:0}.vtkg-chart-scroll{overflow-x:auto}.vtkg-chart svg{display:block;width:100%;min-width:520px;height:auto;max-height:370px}

.mode-switch{display:flex;gap:8px;flex-wrap:wrap;margin:12px 0}.custom-query{display:grid;gap:10px;margin:12px 0}.custom-query textarea{width:100%;box-sizing:border-box;padding:12px;border:1px solid #334a62;border-radius:8px;background:#0c192a;color:#eaf4ff;font:inherit;resize:vertical}.example-list{display:grid;gap:8px}.example-list strong{font-size:12px}.example-button{text-align:left;white-space:normal;padding:9px 12px}
.result-panel{display:grid;gap:16px}.result-panel pre{white-space:pre-wrap;overflow-wrap:anywhere;max-height:480px;overflow:auto}.result-section{border-top:1px solid #334a62;padding-top:15px;display:grid;gap:9px}.result-section h3{font-size:14px;margin:0}.answer-text{white-space:pre-wrap;overflow-wrap:anywhere;line-height:1.65}.section-heading{display:flex;align-items:center;justify-content:space-between;gap:12px}.table-scroll{overflow-x:auto}.evidence-table{width:100%;border-collapse:collapse;font-size:12px;text-align:left}.evidence-table th,.evidence-table td{padding:10px;border-bottom:1px solid #334a62;vertical-align:top}.evidence-table th{color:#a9bfd0;font-weight:600}.full-id{display:block;overflow-wrap:anywhere;font-size:10px;opacity:.75;margin-top:3px}.mono{font-family:ui-monospace,SFMono-Regular,Consolas,monospace;overflow-wrap:anywhere}.event-summary{display:grid;gap:7px;padding:12px;border:1px solid #334a62;border-radius:8px}.event-summary small{color:#a9bfd0}.source-row{font-size:12px;margin:0}.detail-toggle{font-size:12px;overflow:hidden}.detail-toggle summary{cursor:pointer}.detail-toggle pre{white-space:pre-wrap;overflow-wrap:anywhere;max-height:420px;overflow:auto;font-size:11px}.spec-block{padding:12px 0}.result-notice{padding:12px;border:1px solid #b45309;border-radius:8px}.result-section ul{margin:0;padding-left:22px}.result-section li{margin:6px 0}
select{padding:10px;border:1px solid #657b92;border-radius:7px;background:#101820;color:#fff;max-width:100%;width:100%;color-scheme:dark}
select option,select optgroup{background:#101820;color:#fff}
select:focus-visible{outline:2px solid #79b8ff;outline-offset:2px}
select:disabled{opacity:.6;cursor:not-allowed}
</style>
