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
const selectedReasoningTab = ref<'overview'|'evidence'>('overview')
const selectedEventId = ref('')
const reasoningEvents = computed(() => reasoning.value?.R04.events ?? [])
const selectedEvent = computed(() => reasoningEvents.value.find(event => event.eventId === selectedEventId.value) ?? reasoningEvents.value[0] ?? null)
const eventDelta = computed(() => selectedEvent.value?.beforeMean != null && selectedEvent.value?.afterMean != null
 ? selectedEvent.value.afterMean - selectedEvent.value.beforeMean : null)
const eventPercent = computed(() => eventDelta.value != null && selectedEvent.value?.beforeMean
 ? eventDelta.value / Math.abs(selectedEvent.value.beforeMean) * 100 : null)
const eventSecond = computed(() => selectedEvent.value ? selectedEvent.value.simulationTimeHours * 3600 : null)
const reasoningSummary = computed(() => [
 {id:'R01',label:'Engineering to observations',status:reasoning.value?.R01.status ?? 'unavailable'},
 {id:'R02',label:'Reverse traceability',status:reasoning.value?.R02.status ?? 'unavailable'},
 {id:'R03',label:'Cross-domain shared signal',status:reasoning.value?.R03.status ?? 'unavailable'},
 {id:'R04',label:'Recorded-command comparison',status:reasoning.value?.R04.status ?? 'unavailable'},
 {id:'R05',label:'Combined association',status:reasoning.value?.R05.status ?? 'unavailable'}
])
const completeCount = computed(() => reasoningSummary.value.filter(item => item.status === 'complete').length)
const eventChart = computed(() => {
 const event = selectedEvent.value
 const samples = (response.value?.result?.observations ?? [])
  .filter(p => Number.isFinite(p.simulationTimeHours) && Number.isFinite(p.value))
  .map(p => ({second:p.simulationTimeHours * 3600,value:p.value}))
  .sort((a,b) => a.second-b.second)
 if (!event || !samples.length) return null
 const t=event.simulationTimeHours*3600
 const window=event.windowSeconds || 30
 const visible=samples.filter(p => p.second >= t-window && p.second <= t+window)
 if (!visible.length) return null
 const minV=Math.min(...visible.map(p=>p.value)),maxV=Math.max(...visible.map(p=>p.value))
 const padding=(maxV-minV || Math.max(Math.abs(minV),1))*0.12
 const low=minV-padding,high=maxV+padding
 const left=64,right=716,top=22,bottom=215
 const x=(second:number)=>left+(second-(t-window))/(2*window)*(right-left)
 const y=(value:number)=>bottom-(value-low)/(high-low)*(bottom-top)
 return {points:visible.map(p=>({...p,x:x(p.second),y:y(p.value)})),
  polyline:visible.map(p=>`${x(p.second)},${y(p.value)}`).join(' '),
  markerX:x(t),left,right,top,bottom,
  xTicks:[t-window,t-window/2,t,t+window/2,t+window].map(second=>({x:x(second),label:second.toFixed(0)})),
  yTicks:[0,1,2,3,4].map(i=>({y:bottom-(bottom-top)*i/4,label:(low+(high-low)*i/4).toFixed(2)}))}
})
watch(graph, () => { selectedReasoningTab.value='overview'; selectedEventId.value='' })
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
  <div v-if="historianMode === 'reasoning' && graphReady && graph" class="reasoning-dashboard">
   <div class="reasoning-header">
    <div><h3>Live reasoning overview</h3><p class="subdued">{{r01?.function.domain || 'Engineering'}} · {{r01?.function.localId || '—'}} → {{r01?.signal.signalId || '—'}}</p></div>
    <span class="reasoning-count" role="status">{{completeCount}} / 5 operators complete</span>
   </div>
   <div class="reasoning-metrics">
    <div><span>Observations</span><strong>{{r01?.observationCount ?? 0}}</strong></div>
    <div><span>Graph nodes</span><strong>{{graph.nodes.length}}</strong></div>
    <div><span>Graph edges</span><strong>{{graph.edges.length}}</strong></div>
   </div>
   <p class="subdued">Query-scoped virtual graph · not materialized · physical sensor binding {{r01?.provenance.physicalSensorBinding || 'NOT_VERIFIED'}}</p>
   <div class="reasoning-tabs" role="group" aria-label="Reasoning display">
    <button type="button" :class="selectedReasoningTab==='overview'?'primary':'secondary'" :aria-pressed="selectedReasoningTab==='overview'" @click="selectedReasoningTab='overview'">Visual overview</button>
    <button type="button" :class="selectedReasoningTab==='evidence'?'primary':'secondary'" :aria-pressed="selectedReasoningTab==='evidence'" @click="selectedReasoningTab='evidence'">Evidence explorer</button>
   </div>
   <template v-if="r01">
    <template v-if="selectedReasoningTab==='overview'">
     <section class="reasoning-card" aria-label="Engineering traceability">
      <h4>Engineering traceability</h4>
      <div class="mapping-domains">
       <div v-for="fn in reasoning!.R02.engineeringFunctions" :key="fn.id" class="mapping-node"><small>{{fn.domain}}</small><strong>{{fn.localId}}</strong></div>
      </div>
      <div class="mapping-connector">↓ Shared operational signal · asset {{r01.asset.identifier}}</div>
      <div class="mapping-signal"><strong>{{r01.signal.signalId}}</strong><span>{{r01.observationCount}} historian observations</span></div>
      <p class="subdued">Engineering association from GraphDB; physical identity is not verified.</p>
     </section>
     <section class="reasoning-card" aria-label="Recorded command and temporal comparison">
      <h4>Recorded command · temporal comparison</h4>
      <template v-if="reasoningEvents.length">
       <label v-if="reasoningEvents.length > 1" for="reasoning-event-choice">Recorded event</label>
       <select v-if="reasoningEvents.length > 1" id="reasoning-event-choice" v-model="selectedEventId">
        <option v-for="ev in reasoningEvents" :key="ev.eventId" :value="ev.eventId">{{(ev.simulationTimeHours*3600).toFixed(1)}} s · {{ev.action}} · {{ev.target || 'unknown target'}}</option>
       </select>
       <template v-if="selectedEvent">
        <div class="reasoning-event-header">
         <strong>{{selectedEvent.action}} · {{eventSecond?.toFixed(1)}} s</strong>
         <span :class="selectedEvent.relevance==='target_verified'?'reasoning-positive':'reasoning-caution'" role="status">{{selectedEvent.relevance==='target_verified'?'Exact target match':selectedEvent.relevance==='target_missing'?'Target missing':'Target mismatch'}}</span>
        </div>
        <p class="subdued">Command target {{selectedEvent.target || 'not recorded'}} · selected signal {{r01.signal.signalId}} · {{selectedEvent.faultId || 'Unknown fault'}} ({{selectedEvent.faultType || 'type unknown'}})</p>
        <div v-if="eventChart" class="reasoning-plot-scroll">
         <svg viewBox="0 0 760 270" role="img" :aria-label="'Signal values around recorded command at '+eventSecond+' seconds; vertical dashed line marks command time'">
          <g stroke="currentColor" opacity=".16"><line v-for="tick in eventChart.yTicks" :key="tick.y" :x1="eventChart.left" :x2="eventChart.right" :y1="tick.y" :y2="tick.y"/></g>
          <g fill="currentColor" font-size="12">
           <text v-for="tick in eventChart.xTicks" :key="tick.x" :x="tick.x" y="235" text-anchor="middle">{{tick.label}}</text>
           <text v-for="tick in eventChart.yTicks" :key="tick.y" x="57" :y="tick.y+4" text-anchor="end">{{tick.label}}</text>
           <text x="390" y="260" text-anchor="middle">Simulation time (seconds)</text>
          </g>
          <line :x1="eventChart.markerX" :x2="eventChart.markerX" :y1="eventChart.top" :y2="eventChart.bottom" stroke="#f59e0b" stroke-width="2" stroke-dasharray="6 5"/>
          <text :x="eventChart.markerX+6" y="17" fill="#fbbf24" font-size="12">Command</text>
          <polyline :points="eventChart.polyline" fill="none" stroke="#38bdf8" stroke-width="2.5" stroke-linejoin="round"/>
          <circle v-for="p in eventChart.points" :key="p.second" :cx="p.x" :cy="p.y" r="3" fill="#38bdf8"><title>{{p.second.toFixed(2)}} s · {{p.value}}</title></circle>
         </svg>
        </div>
        <p v-else class="subdued">No numeric observations available for the selected event window.</p>
        <div class="reasoning-metrics comparison-metrics">
         <div><span>Before mean · {{selectedEvent.beforeCount}} samples</span><strong>{{selectedEvent.beforeMean?.toFixed(4) ?? 'Unavailable'}}</strong></div>
         <div><span>After mean · {{selectedEvent.afterCount}} samples</span><strong>{{selectedEvent.afterMean?.toFixed(4) ?? 'Unavailable'}}</strong></div>
         <div><span>Mean difference</span><strong>{{eventDelta === null ? 'Unavailable' : (eventDelta >= 0 ? '+' : '') + eventDelta.toFixed(4)}}</strong><small v-if="eventPercent !== null">{{eventPercent >= 0 ? '+' : ''}}{{eventPercent.toFixed(2)}}%</small></div>
        </div>
        <p class="subdued">Equal {{selectedEvent.windowSeconds}}-second windows · {{selectedEvent.atCount}} observations exactly at the command time · descriptive association only, not causal evidence.</p>
       </template>
      </template>
      <p v-else class="subdued">No run-linked recorded commands available. {{reasoning!.R04.reason}}</p>
     </section>
     <section class="reasoning-card">
      <h4>Reasoning checks</h4>
      <div v-for="item in reasoningSummary" :key="item.id" class="reasoning-check">
       <span><strong>{{item.id}}</strong> · {{item.label}}</span>
       <span :class="item.status==='complete'?'reasoning-positive':'reasoning-caution'">{{item.status==='complete'?'✓ Complete':item.status.replaceAll('_',' ')}}</span>
      </div>
      <p v-if="reasoning!.R05.status!=='complete'" class="subdued" role="status">R05 not established: {{reasoning!.R05.reason}}. A descriptive R04 result does not establish target relevance.</p>
      <p v-else class="subdued">R05 combines cross-domain mapping with {{reasoning!.R05.temporalEvents?.length ?? 0}} qualifying exact-target recorded event(s).</p>
     </section>
    </template>
    <template v-else>
     <section class="reasoning-card">
      <h4>Engineering mapping evidence</h4>
      <p>{{r01.function.domain}} {{r01.function.localId}} → {{r01.signal.signalId}} · asset {{r01.asset.identifier}}</p>
      <details><summary>R01 source graph edges</summary><pre>{{JSON.stringify(r01.path,null,2)}}</pre></details>
      <details><summary>R02 reverse engineering paths</summary><pre>{{JSON.stringify(reasoning!.R02.engineeringFunctions,null,2)}}</pre></details>
      <details><summary>R03 cross-domain evidence</summary><pre>{{JSON.stringify(reasoning!.R03,null,2)}}</pre></details>
     </section>
     <section class="reasoning-card">
      <h4>Observation provenance ({{r01.observationCount}} records)</h4>
      <p class="subdued">Select an observation to inspect its graph edges and fingerprint.</p>
      <div class="evidence-scroll"><table class="evidence-table"><thead><tr><th>Second</th><th>Value</th><th>Observed at</th><th>Evidence</th></tr></thead>
       <tbody><tr v-for="item in visibleEvidence" :key="item.id"><td>{{((item.simulationTimeHours ?? 0)*3600).toFixed(3)}}</td><td>{{item.value}}</td><td>{{item.observedAt}}</td><td><details><summary>Inspect observation</summary><pre>{{JSON.stringify({id:item.id,path:item.path,contentFingerprint:item.contentFingerprint},null,2)}}</pre></details></td></tr></tbody>
      </table></div>
      <div class="evidence-pagination"><button type="button" class="secondary" :disabled="evidencePage===1" @click="evidencePage--">Previous</button><span>Page {{evidencePage}} of {{evidencePages}}</span><button type="button" class="secondary" :disabled="evidencePage===evidencePages" @click="evidencePage++">Next</button></div>
     </section>
     <section class="reasoning-card">
      <h4>Recorded-command provenance</h4>
      <details v-for="ev in reasoningEvents" :key="ev.eventId"><summary>{{ev.action}} at {{(ev.simulationTimeHours*3600).toFixed(1)}} s · {{ev.target || 'unknown target'}} · {{ev.status}}</summary><pre>{{JSON.stringify(ev,null,2)}}</pre></details>
      <details><summary>R05 combined evidence</summary><pre>{{JSON.stringify(reasoning!.R05,null,2)}}</pre></details>
     </section>
    </template>
   </template>
   <p v-else role="alert">Structured R01 reasoning is unavailable for this snapshot. Inspect the raw graph or backend log.</p>
   <details class="reasoning-raw"><summary>Full query-scoped graph JSON (advanced)</summary><pre>{{JSON.stringify(graph,null,2)}}</pre></details>
   <p class="subdued">Source-linked virtual reasoning · no physical sensor verification or causal attribution.</p>
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
.reasoning-dashboard { display:grid; gap:16px; margin-top:16px; min-width:0; }
.reasoning-header,.reasoning-event-header { display:flex; align-items:center; justify-content:space-between; gap:12px; flex-wrap:wrap; }
.reasoning-header h3,.reasoning-card h4 { margin:0 0 6px; }
.reasoning-count { border:1px solid #408a73; border-radius:20px; padding:7px 12px; color:#a7f3d0; font-weight:600; font-size:13px; }
.reasoning-metrics { display:grid; grid-template-columns:repeat(3,minmax(0,1fr)); gap:10px; }
.reasoning-metrics>div { display:flex; flex-direction:column; gap:5px; background:#14263b; border:1px solid #334a62; border-radius:10px; padding:14px; min-width:0; }
.reasoning-metrics span,.reasoning-metrics small { color:#b5c8d9; font-size:12px; }
.reasoning-metrics strong { font-size:22px; overflow-wrap:anywhere; }
.reasoning-tabs { display:flex; flex-wrap:wrap; gap:8px; }
.reasoning-card { border:1px solid #334a62; border-radius:12px; padding:16px; min-width:0; }
.mapping-domains { display:flex; flex-wrap:wrap; gap:12px; justify-content:center; }
.mapping-node,.mapping-signal { display:flex; flex-direction:column; align-items:center; gap:5px; background:#14263b; border:1px solid #3d5973; border-radius:10px; padding:13px 20px; }
.mapping-node small,.mapping-signal span { color:#b5c8d9; font-size:12px; }
.mapping-connector { text-align:center; color:#b5c8d9; font-size:12px; padding:14px 0; overflow-wrap:anywhere; }
.mapping-signal { margin:auto; max-width:300px; border-color:#408a73; }
.reasoning-plot-scroll { overflow-x:auto; width:100%; }
.reasoning-plot-scroll svg { display:block; width:100%; min-width:540px; }
.reasoning-positive { color:#86efac; font-weight:600; }
.reasoning-caution { color:#fbbf24; font-weight:600; }
.reasoning-check { display:flex; justify-content:space-between; align-items:center; gap:12px; padding:10px 0; border-bottom:1px solid #334a62; flex-wrap:wrap; }
.reasoning-card pre,.reasoning-raw pre { overflow:auto; max-height:350px; white-space:pre-wrap; overflow-wrap:anywhere; font-size:11px; }
.reasoning-card details { margin:10px 0; }
.reasoning-card summary { cursor:pointer; }
.reasoning-raw { min-width:0; }
@media(max-width:650px) { .reasoning-metrics { grid-template-columns:1fr; } .reasoning-metrics strong { font-size:19px; } }
</style>
