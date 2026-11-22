<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
const historianMode = ref<'retrieval'|'reasoning'>('retrieval')

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
type GraphNode = {id:string;type:string;localId?:string;domain?:string;signalId?:string;identifier?:string;runId?:string;simulationTimeHours?:number;value?:number;observedAt?:string;identityScope?:string;contentFingerprint?:string;source?:string}
type GraphEdge = {source:string;target:string;predicate:string}
type GraphContext = {nodes:GraphNode[];edges:GraphEdge[];capabilities:Record<string,boolean>}
const graph = computed(()=>response.value?.result?.vtkgStatus === 'constructed' ? response.value.result.vtkg as GraphContext : null)
const graphReady = computed(()=>!!graph.value && !busy.value)
const evidencePage = ref(1)
const pageSize = 25
type ReasoningFunction = {id:string;domain?:string;localId?:string;path:Array<{source:string;predicate:string;target:string}>}
type ReasoningObservation = {id:string;simulationTimeHours?:number;value?:number;observedAt?:string;contentFingerprint?:string;path:Array<{source:string;predicate:string;target:string}>}
type ReasoningResult = {
 R01:{status:string;function:{id:string;domain:string;localId:string};signal:{id:string;signalId:string};run:{id:string;runId:string};asset:{id:string;type:string;identifier:string};path:Array<{source:string;predicate:string;target:string}>;observationCount:number;observations:ReasoningObservation[];provenance:Record<string,string|boolean>};
 R02:{status:string;signalId:string;observationCount:number;engineeringFunctions:ReasoningFunction[];scope:string};
 R03:{status:string;sharedSignal:string;engineeringFunctions:ReasoningFunction[];domainsPresent:string[];interpretation:string};
 R04:{status:string;reason:string;interpretation?:string;events?:Array<{eventId:string;action:string;simulationTimeHours:number;beforeCount:number;atCount:number;afterCount:number;beforeMean:number|null;afterMean:number|null;status:string;relevance:string;target?:string;faultId?:string;faultType?:string;eventSource?:string;windowSeconds:number;windowBeforeSeconds:number[];windowAfterSeconds:number[];beforeObservationIds:string[];afterObservationIds:string[];path:{source:string;predicate:string;target:string}}>};R05:{status:string;reason?:string;interpretation?:string;sharedSignal?:string;engineeringFunctions?:ReasoningFunction[];temporalEvents?:unknown[];targetVerification?:string}
}
const reasoning = computed(() => (graph.value as (GraphContext & {reasoning?:ReasoningResult}) | null)?.reasoning ?? null)
const r01 = computed(() => reasoning.value?.R01.status === 'complete' ? reasoning.value.R01 : null)
const evidencePages = computed(() => Math.max(1, Math.ceil((r01.value?.observations.length ?? 0) / pageSize)))
const visibleEvidence = computed(() => r01.value?.observations.slice((evidencePage.value-1)*pageSize,evidencePage.value*pageSize) ?? [])
watch(graph, () => { evidencePage.value = 1 })

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
watch([selectedRun,selectedDomain,selectedLocalId,startSeconds,endSeconds,question],()=>{
 response.value=null
 historianMode.value='retrieval'
})


async function run() {
 historianMode.value='retrieval'
 error.value = ''
 response.value = null
 if (question.value.trim().length < 5) {
  error.value = 'Enter a question to continue.'
  return
 }
 const submittedQuestion=question.value
 const submittedContext=JSON.stringify([selectedRun.value,selectedDomain.value,selectedLocalId.value,startSeconds.value,endSeconds.value])
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
  if (question.value===submittedQuestion && submittedContext===JSON.stringify([selectedRun.value,selectedDomain.value,selectedLocalId.value,startSeconds.value,endSeconds.value])) response.value = body as HistorianResponse
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
  <div class="historian-mode-switch" role="group" aria-label="Historian query mode">
   <button type="button" :class="historianMode === 'retrieval' ? 'primary' : 'secondary'" :aria-pressed="historianMode === 'retrieval'" @click="historianMode='retrieval'">Historian Retrieval</button>
   <button type="button" :class="historianMode === 'reasoning' ? 'primary' : 'secondary'" :aria-pressed="historianMode === 'reasoning'"  :disabled="!graphReady" @click="historianMode='reasoning'">VTKG Reasoning</button>
  </div>
  <p v-if="!graphReady" class="subdued">Run a historian query to construct the VTKG and unlock live reasoning.</p>
  <div v-if="historianMode === 'reasoning' && graphReady && graph">
   <h3>Active VTKG context</h3>
   <p>{{graph.nodes.length}} nodes · {{graph.edges.length}} edges · query-scoped, not materialized</p>
   <template v-if="r01">
    <h3>R01 · Explainable engineering-to-observation association</h3>
    <p><strong>{{r01.function.domain}} · {{r01.function.localId}}</strong> → <strong>{{r01.signal.signalId}}</strong> ← <strong>{{r01.observationCount}} observations</strong></p>
    <p>Run: <code>{{r01.run.runId}}</code> · Asset reference: <code>{{r01.asset.identifier}}</code></p>
    <p role="status">R01 validated {{r01.observationCount}} observation paths against the historian response.</p>
    <h4>Graph evidence and provenance</h4>
    <ol><li v-for="edge in r01.path" :key="edge.source+edge.predicate+edge.target"><code>{{edge.source}}</code> <strong>—{{edge.predicate}}→</strong> <code>{{edge.target}}</code></li></ol>
    <p class="subdued">Engineering mapping: {{r01.provenance.engineeringMapping}} · Observations: {{r01.provenance.observations}} · Physical sensor binding: {{r01.provenance.physicalSensorBinding}} · Not materialized in GraphDB.</p>
    <details><summary>Supporting observation evidence ({{r01.observationCount}} records)</summary>
     <p>Each observation has explicit observesSignal and belongsToRun edges. Select an observation identity to inspect its graph path.</p>
     <div class="evidence-scroll"><table class="evidence-table"><thead><tr><th>Simulation second</th><th>Value</th><th>Observed at</th><th>Graph evidence</th></tr></thead>
      <tbody><tr v-for="item in visibleEvidence" :key="item.id"><td>{{((item.simulationTimeHours ?? 0)*3600).toFixed(3)}}</td><td>{{item.value}}</td><td>{{item.observedAt}}</td><td><details><summary>{{item.id.split('/').pop()}}</summary><p v-for="edge in item.path" :key="edge.predicate"><code>{{edge.source}} —{{edge.predicate}}→ {{edge.target}}</code></p><p>Content fingerprint: <code>{{item.contentFingerprint}}</code></p></details></td></tr></tbody>
     </table></div>
     <div class="evidence-pagination"><button type="button" class="secondary" :disabled="evidencePage===1" @click="evidencePage--">Previous</button><span>Page {{evidencePage}} of {{evidencePages}}</span><button type="button" class="secondary" :disabled="evidencePage===evidencePages" @click="evidencePage++">Next</button></div>
    </details>
    <h3>R02 · Reverse engineering traceability</h3>
    <p>{{reasoning!.R02.engineeringFunctions.length}} engineering function(s) mapped to {{r01.signal.signalId}} within this query-scoped graph.</p>
    <ul><li v-for="fn in reasoning!.R02.engineeringFunctions" :key="fn.id"><strong>{{fn.domain}} · {{fn.localId}}</strong> —mapsToSignal→ {{r01.signal.signalId}} <details><summary>Show source edge</summary><pre>{{JSON.stringify(fn.path,null,2)}}</pre></details></li></ul>
    <p class="subdued">{{reasoning!.R02.scope}}</p>
    <h3>R03 · Cross-domain shared signal</h3>
    <template v-if="reasoning!.R03.status==='complete'"><p role="status">DEXPI and ECAD functions are both associated with {{reasoning!.R03.sharedSignal}}.</p><ul><li v-for="fn in reasoning!.R03.engineeringFunctions" :key="fn.id">{{fn.domain}} · {{fn.localId}}</li></ul></template>
    <p v-else>Insufficient cross-domain evidence in this snapshot. Domains found: {{reasoning!.R03.domainsPresent.join(', ') || 'none'}}.</p>
    <p class="subdued">{{reasoning!.R03.interpretation}}</p>
    <h3>R04 · Recorded-command temporal comparison</h3>
    <template v-if="reasoning!.R04.events?.length">
     <p role="status"><strong>R04: temporal calculation {{reasoning!.R04.status === 'complete' ? 'available' : 'insufficient'}}.</strong> A completed calculation does not establish that the command targets {{reasoning!.R01.signal.signalId}} or caused a change.</p>
     <div v-for="event in reasoning!.R04.events" :key="event.eventId">
      <p><strong>{{event.action}}</strong> · event {{event.eventId}} · simulation second {{(event.simulationTimeHours*3600).toFixed(3)}} · temporal calculation: {{event.status}}</p>
      <p class="command-relevance" :class="event.relevance === 'target_verified' ? 'command-relevance-matched' : 'command-relevance-unverified'" role="status"><strong>{{event.relevance === 'target_verified' ? 'Exact target match' : event.relevance === 'target_missing' ? 'Target not recorded — relevance unknown' : 'Target mismatch — signal relevance not established'}}</strong> · Command target: {{event.target || 'not recorded'}} · Selected signal: {{reasoning!.R01.signal.signalId}}</p>
      <p>Fault: {{event.faultId || 'not recorded'}} ({{event.faultType || 'unknown'}}) · Source: {{event.eventSource || 'not recorded'}}</p>
      <p>Windows: {{event.windowBeforeSeconds.join('–')}} s before; {{event.windowAfterSeconds.join('–')}} s after ({{event.windowSeconds}} seconds per side).</p>
      <p>Before: {{event.beforeCount}} observations, mean {{event.beforeMean ?? 'unavailable'}} · At event: {{event.atCount}} · After: {{event.afterCount}} observations, mean {{event.afterMean ?? 'unavailable'}}</p>
      <details><summary>Show event provenance and selected observation IDs</summary><pre>{{JSON.stringify({commandEdge:event.path,beforeObservationIds:event.beforeObservationIds,afterObservationIds:event.afterObservationIds},null,2)}}</pre></details>
     </div>
    </template>
    <p v-if="reasoning!.R04.status!=='complete'">Insufficient evidence: {{reasoning!.R04.reason}}</p>
    <p class="subdued">{{reasoning!.R04.interpretation}}</p>
    <h3>R05 · Combined cross-domain and temporal association</h3>
    <template v-if="reasoning!.R05.status==='complete'">
     <p role="status">Cross-domain mappings and exact-target recorded-command evidence are linked for signal {{reasoning!.R05.sharedSignal}}.</p>
     <p>{{reasoning!.R05.engineeringFunctions?.map(fn => fn.domain+' · '+fn.localId).join(' / ')}}</p>
     <p>Qualified recorded events: {{reasoning!.R05.temporalEvents?.length}} · Target verification: {{reasoning!.R05.targetVerification}}</p>
     <p class="subdued">{{reasoning!.R05.interpretation}}</p>
    </template>
    <p v-else role="status"><strong>R05 not established.</strong> {{reasoning!.R05.reason}} R04 may still report a valid descriptive comparison for an unrelated command.</p>
   </template>
   <p v-else role="alert">Structured R01 reasoning is unavailable for this snapshot. Inspect the graph or backend log; a node count alone is not a reasoning result.</p>
   <details><summary>Inspect full query-scoped graph JSON</summary><pre style="overflow:auto;max-height:320px">{{JSON.stringify(graph, null, 2)}}</pre></details>
   <p class="subdued">R04/R05 are enabled only with run-linked recorded commands and sufficient temporal evidence. No physical causation is inferred.</p>
  </div>
  <div v-show="historianMode === 'retrieval'">
  <p v-if="!response">Ask about engineering information or explore recorded simulation data in your own words.</p>
  <p v-if="!response">Need a hand getting started? Choose a simulation run and instrument below, then pick a suggested way to ask. You can also type your own question at any time.</p>
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
   <p v-if="graphReady" style="color:#4ade80">VTKG constructed · {{graph?.nodes.length}} nodes · {{graph?.edges.length}} edges. <button type="button" class="secondary" @click="historianMode='reasoning'">Explore VTKG Reasoning</button></p>
   <p v-else-if="response.result.vtkgStatus==='unavailable'" role="status">Historian retrieval succeeded; VTKG construction unavailable.</p>
   <h3>Query details</h3>
   <details><summary>View how DTWise interpreted your question</summary><pre style="overflow:auto;white-space:pre-wrap">{{JSON.stringify(response.plan, null, 2)}}</pre></details>
  </template>
  </div>
 </section>
</template>

<style scoped>
.historian-mode-switch { display:flex; flex-wrap:wrap; gap:8px; margin:12px 0; }
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
 .evidence-scroll { overflow-x:auto; max-width:100%; }
.evidence-table { width:100%; border-collapse:collapse; font-size:13px; }
.evidence-table th,.evidence-table td { padding:9px; border-bottom:1px solid #334a62; text-align:left; white-space:nowrap; }
.evidence-table code { font-size:11px; }
.evidence-pagination { display:flex; align-items:center; gap:12px; margin:12px 0; }
.command-relevance { padding: 10px 12px; border: 1px solid; border-radius: 6px; }
.command-relevance-matched { border-color: #408a73; background: rgba(64,138,115,.10); }
.command-relevance-unverified { border-color: #b88a42; background: rgba(184,138,66,.12); }
</style>
