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
type DirectResult = {runId:string;signalId:string;observations:Array<{simulationTimeHours:number;value:number;observedAt:string}>;observationCount:number;truncated:boolean;source:string}
const directResult = ref<DirectResult | null>(null)
type GraphNode = {id:string;type:string;localId?:string;domain?:string;signalId?:string;identifier?:string;runId?:string;simulationTimeHours?:number;value?:number;observedAt?:string;identityScope?:string;contentFingerprint?:string;source?:string}
type GraphEdge = {source:string;target:string;predicate:string}
type GraphContext = {nodes:GraphNode[];edges:GraphEdge[];capabilities:Record<string,boolean>}
const graph = computed(()=>response.value?.result?.vtkgStatus === 'constructed' ? response.value.result.vtkg as GraphContext : null)
const graphReady = computed(()=>!!graph.value && !busy.value)
type CrossDomainBridge = {status:string;joinKey?:{value?:string;verification?:string};operationalSignal?:string;engineeringFunctions?:Array<{domain?:string;localId?:string;mappingConfidence?:string}>;assetInventory?:{status:string;evidence?:unknown[]};productCatalog?:{status:string;evidence?:unknown[]};physicalSensorBinding?:string;interpretation?:string}
const crossDomainBridge = computed(() => (graph.value as (GraphContext & {crossDomainBridge?:CrossDomainBridge}) | null)?.crossDomainBridge ?? null)
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
const selectedSignal = ref('')
const knowledgeExpanded = ref(false)
const signalOptions = ref<string[]>([])
const measurementType = ref('')
const measurementTypes = ref<Array<{name:string;signal_count:number}>>([])
const signalDetails = ref<Record<string,{measurement_type:string;unit:string|null;verification_status:string}>>({})
const selectedSignalDetails = computed(() => signalDetails.value[selectedSignal.value])
const selectedSignalFunctions = computed(() => functions.value.filter(item => item.operational_signal === selectedSignal.value))
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

async function loadSignals() {
 const run = selectedRun.value
 selectedSignal.value = ''
 signalOptions.value = []
 discoveryError.value = ''
 if (!run) return
 discoveryBusy.value = true
 try {
  const r = await fetch('/api/ai/vtkg/historian/signals?run_id=' + encodeURIComponent(run) + (measurementType.value ? '&measurement_type=' + encodeURIComponent(measurementType.value) : ''))
  const data = await r.json()
  if (!r.ok) throw new Error(data.error || 'Signal discovery failed')
  if (selectedRun.value === run) {
   signalOptions.value = data.signals.map((s:{signal_id:string}) => s.signal_id)
   signalDetails.value = Object.fromEntries(data.signals.map((s:{signal_id:string;measurement_type:string;unit:string|null;verification_status:string}) => [s.signal_id, s]))
  }
 } catch (e) {
  if (selectedRun.value === run) discoveryError.value = e instanceof Error ? e.message : String(e)
 } finally {
  discoveryBusy.value = false
 }
}
function generatedQuestion(): string {
 if (!selectedRun.value || !selectedSignal.value) return ''
 const interval = startSeconds.value !== '' && endSeconds.value !== ''
  ? ` between simulation seconds ${startSeconds.value} and ${endSeconds.value}`
  : startSeconds.value !== '' ? ` from simulation second ${startSeconds.value} onward`
  : endSeconds.value !== '' ? ` up to simulation second ${endSeconds.value}`
  : ' for all simulation times'
 return `Get historian values for SignalName ${selectedSignal.value} in simulation run ${selectedRun.value},${interval}.`
}
function updateGeneratedQuestion() {
 const next = generatedQuestion()
 if (question.value === '' || question.value === lastGeneratedQuestion) question.value = next
 lastGeneratedQuestion = next
}
async function loadMeasurementTypes() {
 try {
  const r = await fetch('/api/ai/vtkg/historian/measurement-types')
  const data = await r.json()
  if (!r.ok) throw new Error(data.error || 'Measurement type discovery failed')
  measurementTypes.value = data.measurement_types
 } catch (e) { discoveryError.value = e instanceof Error ? e.message : String(e) }
}
watch([selectedRun,measurementType], () => { void loadSignals() })
watch([selectedRun, selectedSignal, startSeconds, endSeconds], updateGeneratedQuestion)
onMounted(() => { void loadRuns(); void loadMeasurementTypes() })
watch([selectedRun, selectedSignal, startSeconds, endSeconds], () => {
 directResult.value = null
 response.value = null
 knowledgeExpanded.value = false
})
async function run() {
 error.value = ''
 directResult.value = null
 response.value = null
 if (!selectedRun.value || !selectedSignal.value) {
  error.value = 'Select a simulation run and SignalName.'
  return
 }
 const start = startSeconds.value === '' ? null : Number(startSeconds.value)
 const end = endSeconds.value === '' ? null : Number(endSeconds.value)
 if ([start,end].some(v => v !== null && (!Number.isFinite(v) || v < 0)) || (start !== null && end !== null && start > end)) {
  error.value = 'Enter a valid nonnegative simulation-time range.'
  return
 }
 const snapshot = JSON.stringify([selectedRun.value,selectedSignal.value,startSeconds.value,endSeconds.value])
 busy.value = true
 try {
  const r = await fetch('/api/ai/vtkg/historian/signal-values', {
   method: 'POST', headers: {'Content-Type':'application/json'},
   body: JSON.stringify({run_id:selectedRun.value,signal_id:selectedSignal.value,start_simulation_seconds:start,end_simulation_seconds:end})
  })
  const body = await r.json()
  if (!r.ok) throw new Error(body.error || 'Historian retrieval failed')
  if (snapshot === JSON.stringify([selectedRun.value,selectedSignal.value,startSeconds.value,endSeconds.value])) directResult.value = body as DirectResult
 } catch (e) {
  error.value = e instanceof Error ? e.message : String(e)
 } finally { busy.value = false }
}
type TraceNode = {id:string;label:string;subtitle:string;kind:'function'|'asset'|'signal'|'run'|'observations';x:number;y:number;source?:GraphNode}
type TraceLink = {source:string;target:string;label:string;virtual:boolean}
const traceSelection = ref('')
const traceLinkSelection = ref('')
const traceZoom = ref(1)
const tracePan = ref({x:0,y:0})
const traceDragging = ref<{x:number;y:number;panX:number;panY:number}|null>(null)
const traceOperator = ref('all')
const traceGraph = computed(() => {
 const r=r01.value
 if (!r) return {nodes:[] as TraceNode[],links:[] as TraceLink[]}
 const functions=reasoning.value?.R02.engineeringFunctions ?? []
 const nodes:TraceNode[] = functions.map((fn,i)=>({
  id:fn.id,label:`${fn.domain || 'Engineering'} · ${fn.localId || 'unknown'}`,
  subtitle:'Engineering function',kind:'function' as const,
  x:Math.max(110,350-(functions.length-1)*105+i*210),y:65,
  source:graph.value?.nodes.find(node=>node.id===fn.id)
 }))
 nodes.push(
  {id:r.asset.id,label:r.asset.identifier.split('/').pop() || r.asset.identifier,subtitle:'Shared asset identifier',kind:'asset',x:350,y:185,source:graph.value?.nodes.find(n=>n.id===r.asset.id)},
  {id:r.signal.id,label:r.signal.signalId,subtitle:'Operational signal',kind:'signal',x:350,y:305,source:graph.value?.nodes.find(n=>n.id===r.signal.id)},
  {id:r.run.id,label:'Simulation run',subtitle:r.run.runId.slice(0,13)+'…',kind:'run',x:130,y:425,source:graph.value?.nodes.find(n=>n.id===r.run.id)},
  {id:'observation-group',label:`${r.observationCount} observations`,subtitle:'TimescaleDB · signal_samples',kind:'observations',x:540,y:425}
 )
 const links:TraceLink[]=[]
 // R01/R02 graph paths are virtual reasoning edges, not raw GraphDB predicates.
 for (const fn of functions) {
  links.push({source:fn.id,target:r.asset.id,label:'shared asset ID',virtual:true})
 }
 links.push({source:r.asset.id,target:r.signal.id,label:'mapping association',virtual:true})
 links.push({source:r.run.id,target:r.signal.id,label:'hasSignal',virtual:true})
 links.push({source:r.signal.id,target:'observation-group',label:'observesSignal',virtual:true})
 return {nodes,links}
})
const selectedTraceLink = computed(()=>traceGraph.value.links.find(link=>link.source+'|'+link.target===traceLinkSelection.value) ?? null)
const traceLinkExplanation = computed(()=>{
 const link=selectedTraceLink.value
 const r=r01.value
 if (!link || !r) return null
 const source=traceGraph.value.nodes.find(n=>n.id===link.source)
 const target=traceGraph.value.nodes.find(n=>n.id===link.target)
 const fn=reasoning.value?.R02.engineeringFunctions.find(item=>item.id===link.source)
 const paths=[...(fn?.path ?? []),...r.path].filter(edge=>edge.source===link.source || edge.target===link.target)
 if (link.target===r.asset.id) return {title:'Engineering function → shared asset',meaning:`The engineering function ${source?.label ?? ''} is associated with asset identifier ${r.asset.identifier}. This is a cross-source join key, not proof that two engineering records refer to the same physical sensor.`,evidence:fn?.path ?? [],source:'GraphDB engineering mappings; query-scoped virtual projection',limitation:'Physical binding NOT_VERIFIED.'}
 if (link.source===r.asset.id) return {title:'Shared asset → operational signal',meaning:`The shared asset identifier links the engineering mapping to operational signal ${r.signal.signalId}. This is an inferred semantic association assembled from source mappings, not a direct GraphDB triple.`,evidence:r.path,source:'GraphDB OPC UA connectivity mapping and VTKG projection',limitation:'OPC UA mapping may be provisional; physical sensor identity is not verified.'}
 if (link.source===r.run.id) return {title:'Simulation run → signal',meaning:`The selected run ${r.run.runId} contains recorded observations for ${r.signal.signalId}.`,evidence:paths,source:'Historian retrieval and query-scoped run graph',limitation:'A run association does not imply engineering or physical identity.'}
 return {title:'Signal → historian observations',meaning:`The virtual graph links ${r.signal.signalId} to ${r.observationCount} source-linked observations. Each observation has its own identity, time, value and provenance fingerprint.`,evidence:r.observations.slice(0,2).flatMap(o=>o.path),source:'TimescaleDB signal_samples; VTKG observation projection',limitation:'The grouped node summarizes observations; it is not a materialized RDF collection.'}
})
const selectedTraceNode = computed(()=>traceGraph.value.nodes.find(node=>node.id===traceSelection.value) ?? null)
const selectedTracePaths = computed(()=>{
 const id=traceSelection.value
 if (!id || !r01.value) return []
 const paths=[...r01.value.path,...(reasoning.value?.R02.engineeringFunctions ?? []).flatMap(fn=>fn.path)]
 return paths.filter(edge=>edge.source===id || edge.target===id)
})
const traceVisibleLinks = computed(()=>traceGraph.value.links.filter(link=>{
 if (traceOperator.value==='all') return true
 if (traceOperator.value==='R01') return link.target===r01.value?.signal.id || link.target==='observation-group' || link.source===r01.value?.run.id
 if (traceOperator.value==='R02'||traceOperator.value==='R03') return link.target===r01.value?.asset.id || link.target===r01.value?.signal.id
 return true
}))
function traceReset() {traceZoom.value=1;tracePan.value={x:0,y:0};traceSelection.value='';traceLinkSelection.value='';traceOperator.value='all'}
function tracePointerDown(event:PointerEvent) {
 if (event.button!==0 || (event.target as Element).closest('[data-trace-node], [data-trace-link]')) return
 traceDragging.value={x:event.clientX,y:event.clientY,panX:tracePan.value.x,panY:tracePan.value.y}
 ;(event.currentTarget as Element).setPointerCapture(event.pointerId)
}
function tracePointerMove(event:PointerEvent) {
 if (!traceDragging.value) return
 const svg=event.currentTarget as SVGSVGElement
 const rect=svg.getBoundingClientRect()
 tracePan.value={x:traceDragging.value.panX+(event.clientX-traceDragging.value.x)*700/rect.width,y:traceDragging.value.panY+(event.clientY-traceDragging.value.y)*510/rect.height}
}
function tracePointerUp() {traceDragging.value=null}
watch(graph,traceReset)

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
const selectedReasoningExplanation = ref('R01')
const reasoningInterpretations = computed(()=>{
 const r=reasoning.value, one=r01.value, event=selectedEvent.value
 if (!r || !one) return []
 const fns=r.R02.engineeringFunctions.map(fn=>`${fn.domain} ${fn.localId}`).join(' and ')
 const exact=event?.relevance==='target_verified'
 const delta=event?.beforeMean != null && event.afterMean != null ? event.afterMean-event.beforeMean : null
 return [
 {id:'R01',question:'Which engineering function leads to these readings?',conclusion:`${one.function.domain} ${one.function.localId} is associated with operational signal ${one.signal.signalId}; ${one.observationCount} historian observations are reachable through the virtual graph.`,evidence:`GraphDB engineering mapping, run ${one.run.runId}, and ${one.observationCount} source-linked observation paths.`,limit:'This is a semantic association, not verified physical sensor identity.'},
 {id:'R02',question:'Can we trace backward from the signal?',conclusion:`Starting from ${one.signal.signalId}, the graph identifies ${r.R02.engineeringFunctions.length} engineering function(s): ${fns || 'none'}.`,evidence:'Reverse traversal of the engineering-to-signal associations in this query-scoped snapshot.',limit:'Only mappings present in this retrieved snapshot are covered.'},
 {id:'R03',question:'Do engineering domains converge on one signal?',conclusion:r.R03.status==='complete' ? `The engineering domains ${r.R03.domainsPresent.join(' and ')} share the operational signal ${r.R03.sharedSignal}.` : 'The available graph does not establish a cross-domain shared signal.',evidence:`${r.R03.engineeringFunctions.length} engineering functions; domain evidence: ${r.R03.domainsPresent.join(', ') || 'none'}.`,limit:'Shared signal identifiers do not prove physical instrument equivalence.'},
 {id:'R04',question:'What changed around the recorded command?',conclusion:event ? `A recorded ${event.action} command at ${(event.simulationTimeHours*3600).toFixed(1)} s targets ${event.target || 'an unspecified signal'}. ${exact?'Its target matches the selected signal.':'Its target is not verified as the selected signal.'} ${delta===null?'The before/after mean difference is unavailable.':`The descriptive mean difference is ${delta>=0?'+':''}${delta.toFixed(4)}.`}` : 'No comparable recorded command is available.',evidence:event ? `${event.beforeCount} before and ${event.afterCount} after observations in ${event.windowSeconds}-second windows; ${event.atCount} observations at the exact event time.` : r.R04.reason,limit:'Temporal proximity and matching targets do not establish causation.'},
 {id:'R05',question:'Can cross-domain and temporal evidence be combined?',conclusion:r.R05.status==='complete' ? `The shared-signal engineering association and ${r.R05.temporalEvents?.length ?? 0} qualifying exact-target recorded command(s) form one source-linked explanation.` : `Combined evidence is not established: ${r.R05.reason || 'requirements not met'}.`,evidence:`R03: ${r.R03.status}; R04: ${r.R04.status}; exact-target evidence required for R05.`,limit:'This is an evidence-linked association, not proof of a physical fault or causal mechanism.'}
 ].map(item=>({...item,status:r[item.id as keyof ReasoningResult].status}))
})
const activeReasoningInterpretation = computed(()=>reasoningInterpretations.value.find(item=>item.id===selectedReasoningExplanation.value) ?? reasoningInterpretations.value[0] ?? null)
const completeCount = computed(() => reasoningSummary.value.filter(item => item.status === 'complete').length)
const eventChart = computed(() => {
 const event = selectedEvent.value
 const samples = (directResult.value?.observations ?? response.value?.result?.observations ?? [])
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
  <div class="panel-title"><div><h2>Simulation Historian · Engineering Knowledge Explorer</h2><p>Benchmark stage 09 · B33–B37 · parameterized simulation test cases</p></div><span class="pill">PREVIEW</span></div>
  <p v-if="!directResult" class="subdued">Start with a run and SignalName to inspect measurements. Explore the engineering knowledge graph separately when you need cross-domain context.</p>
  <div class="historian-unified-query">
  <p v-if="!directResult">Start with recorded signals and simulation time; engineering context can be explored separately.</p>
  <p v-if="!directResult">SignalNames and values are retrieved directly from TimescaleDB, without a DEXPI or ECAD LocalID.</p>
  <div class="experiment-fields">
   <div class="experiment-field"><label for="historian-experiment-run">Simulation run (optional)</label>
   <select id="historian-experiment-run" v-model="selectedRun" :disabled="discoveryBusy">
    <option value="">Select simulation run</option>
    <option v-for="runId in runs" :key="runId" :value="runId">{{runId}}</option>
   </select>
   <button class="experiment-refresh" type="button" :disabled="discoveryBusy" @click="loadRuns">Refresh runs</button></div>
   <div class="experiment-field"><label for="historian-measurement-type">Measurement Type</label>
   <select id="historian-measurement-type" v-model="measurementType"><option value="">All types</option><option v-for="type in measurementTypes" :key="type.name" :value="type.name">{{type.name}} ({{type.signal_count}})</option></select></div>
   <div class="experiment-field"><label for="historian-experiment-signal">SignalName</label>
   <select id="historian-experiment-signal" v-model="selectedSignal" :disabled="!selectedRun || discoveryBusy"><option value="">Select signal</option><option v-for="signal in signalOptions" :key="signal" :value="signal">{{signal}}</option></select></div>
   <div class="experiment-field"><label for="historian-experiment-start">From simulation second (optional)</label>
   <input id="historian-experiment-start" v-model="startSeconds" type="number" min="0" step="any" placeholder="No lower bound" /></div>
   <div class="experiment-field"><label for="historian-experiment-end">To simulation second (optional)</label>
   <input id="historian-experiment-end" v-model="endSeconds" type="number" min="0" step="any" placeholder="No upper bound" /></div>
   <p v-if="selectedSignalDetails" class="subdued experiment-wide">Classification: {{selectedSignalDetails.measurement_type}} · Unit: {{selectedSignalDetails.unit || 'not verified'}} · Status: {{selectedSignalDetails.verification_status}}</p>
   <p class="experiment-wide" v-if="discoveryError" role="alert">{{discoveryError}}</p>
   <p class="subdued experiment-wide">SignalNames and measurement classifications come directly from TimescaleDB. Unclassified means no verified type is available. Leave time fields empty for all simulation times; retrieval is capped at 5,000 rows.</p>
  </div>
  <p class="subdued">Run {{selectedRun || 'not selected'}} · Signal {{selectedSignal || 'not selected'}} · {{startSeconds || 'start'}} to {{endSeconds || 'end'}} simulation seconds.</p>
  <label class="experiment-question-label" for="historian-experiment-question">Your question</label>
  <textarea id="historian-experiment-question" v-model="question" rows="2" class="experiment-question" readonly aria-label="Generated historian query" />
  <div style="margin-top:12px"><button class="primary" :disabled="busy || !selectedRun || !selectedSignal" @click="run">{{busy ? 'Retrieving…' : 'Retrieve historian measurements'}}</button></div>
  <p v-if="error" role="alert" style="color:#b91c1c">{{error}}</p>
  <template v-if="directResult">
   <h3>Historian result · {{directResult.signalId}}</h3>
   <p>{{directResult.observationCount}} observations · {{directResult.source}} <span v-if="directResult.truncated">· Showing first 5,000 rows; narrow the time range for more.</span></p>
   <div v-if="experimentalChart" class="vtkg-chart">
    <div class="vtkg-chart-scroll">
     <svg viewBox="0 0 780 295" role="img" :aria-label="'Historian time-series for '+directResult.signalId">
      <g stroke="currentColor" opacity="0.22"><line v-for="tick in experimentalChart.yTicks" :key="'direct-grid-'+tick.y" :x1="experimentalChart.left" :x2="experimentalChart.right" :y1="tick.y" :y2="tick.y"/></g>
      <polyline :points="experimentalChart.polyline" fill="none" stroke="#38bdf8" stroke-width="2.5"/>
      <g fill="currentColor" font-size="12"><text v-for="tick in experimentalChart.xTicks" :key="'direct-x-'+tick.x" :x="tick.x" y="263" text-anchor="middle">{{tick.label}} s</text><text v-for="tick in experimentalChart.yTicks" :key="'direct-y-'+tick.y" x="64" :y="tick.y+4" text-anchor="end">{{tick.label}}</text></g>
     </svg>
    </div>
   </div>
   <p v-else class="subdued">No numeric observations available to graph.</p>
   <p class="subdued">Engineering knowledge is not queried during historian retrieval. VTKG signal-first exploration requires a separate backend integration.</p>
  </template>
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
   <div v-if="graphReady" class="explore-knowledge-action"><p class="subdued">Historian data retrieved. Engineering context is available when you want to investigate the selected signal.</p><button type="button" class="primary" :aria-expanded="knowledgeExpanded" @click="knowledgeExpanded=!knowledgeExpanded">{{knowledgeExpanded ? 'Hide engineering knowledge' : 'Explore engineering knowledge & R01–R05'}}</button><span class="subdued">{{graph?.nodes.length}} virtual nodes · {{graph?.edges.length}} edges</span></div>
   <p v-else-if="response.result.vtkgStatus==='unavailable'" role="status">Historian retrieval succeeded; VTKG construction unavailable.</p>
   <h3>Query details</h3>
   <details><summary>View how DTWise interpreted your question</summary><pre style="overflow:auto;white-space:pre-wrap">{{JSON.stringify(response.plan, null, 2)}}</pre></details>
  </template>
  </div>
  <section v-if="knowledgeExpanded && crossDomainBridge" class="reasoning-card cross-domain-bridge" aria-label="Cross-domain reasoning bridge">
   <div class="trace-heading"><div><h3>Cross-domain → temporal reasoning</h3><p class="subdued">One evidence chain across engineering semantics and recorded behavior.</p></div><span class="pill">{{crossDomainBridge.status === 'partial' ? 'PARTIAL BRIDGE' : 'ENRICHMENT UNAVAILABLE'}}</span></div>
   <div class="bridge-steps">
    <div class="bridge-step"><small>Engineering design</small><strong>{{(crossDomainBridge.engineeringFunctions || []).map(f => (f.domain || 'Engineering') + ' ' + (f.localId || '—')).join(' · ') || 'Not resolved'}}</strong><span>GraphDB semantic associations</span></div>
    <div class="bridge-arrow" aria-hidden="true">→</div>
    <div class="bridge-step"><small>Shared asset identifier</small><strong>{{crossDomainBridge.joinKey?.value || 'Not available'}}</strong><span>Semantic join · not physical identity</span></div>
    <div class="bridge-arrow" aria-hidden="true">→</div>
    <div class="bridge-step"><small>Operational signal</small><strong>{{crossDomainBridge.operationalSignal || 'Not available'}}</strong><span>Historian observations &amp; recorded commands</span></div>
   </div>
   <div class="bridge-source-status"><div><strong>Asset Inventory</strong><span>{{crossDomainBridge.assetInventory?.status === 'NOT_RESOLVED' ? 'Relationship not yet resolved' : crossDomainBridge.assetInventory?.status || 'Not available'}}</span></div><div><strong>Product Catalog</strong><span>{{crossDomainBridge.productCatalog?.status === 'NOT_RESOLVED' ? 'Relationship not yet resolved' : crossDomainBridge.productCatalog?.status || 'Not available'}}</span></div></div>
   <p class="trace-limitation">The shared identifier supports semantic traceability. It does not verify a physical sensor or a catalog product. Unresolved source joins are shown explicitly.</p>
   <details><summary>Technical bridge evidence</summary><pre>{{JSON.stringify(crossDomainBridge,null,2)}}</pre></details>
  </section>
  <div v-if="knowledgeExpanded && graphReady" class="unified-section-heading"><h3>Engineering graph &amp; reasoning</h3><p class="subdued">Interpret the same query through traceability, temporal evidence, and R01–R05 checks.</p></div>
  <div v-if="knowledgeExpanded && graphReady && graph" class="reasoning-dashboard">
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
     <section class="reasoning-card trace-card" aria-label="Interactive engineering traceability">
      <div class="trace-heading"><div><h4>Engineering traceability</h4><p class="subdued">Select a node to inspect its evidence. Drag the canvas to pan.</p></div>
       <div class="trace-controls">
        <label for="trace-path-filter">Highlight</label>
        <select id="trace-path-filter" v-model="traceOperator"><option value="all">All associations</option><option value="R01">R01 · Observations</option><option value="R02">R02 · Reverse trace</option><option value="R03">R03 · Cross-domain</option><option value="R04">R04 · Recorded event</option><option value="R05">R05 · Combined</option></select>
        <button type="button" class="secondary" aria-label="Zoom out" @click="traceZoom=Math.max(.6,traceZoom-.2)">−</button>
        <button type="button" class="secondary" aria-label="Zoom in" @click="traceZoom=Math.min(2,traceZoom+.2)">+</button>
        <button type="button" class="secondary" @click="traceReset">Reset</button>
       </div>
      </div>
      <div class="trace-layout">
       <div class="trace-canvas">
        <svg viewBox="0 0 700 510" role="group" aria-label="Interactive semantic association diagram" @pointerdown="tracePointerDown" @pointermove="tracePointerMove" @pointerup="tracePointerUp" @pointercancel="tracePointerUp">
         <g :transform="`translate(${350+tracePan.x} ${255+tracePan.y}) scale(${traceZoom}) translate(-350 -255)`">
          <g v-for="(link,index) in traceVisibleLinks" :key="index" data-trace-link role="button" tabindex="0" :aria-label="'Explain '+link.label" :aria-pressed="traceLinkSelection===link.source+'|'+link.target" class="trace-link-hit" @click="traceLinkSelection=link.source+'|'+link.target;traceSelection=''" @keydown.enter.prevent="traceLinkSelection=link.source+'|'+link.target;traceSelection=''" @keydown.space.prevent="traceLinkSelection=link.source+'|'+link.target;traceSelection=''">
           <template v-if="traceGraph.nodes.find(n=>n.id===link.source) && traceGraph.nodes.find(n=>n.id===link.target)">
            <line :x1="traceGraph.nodes.find(n=>n.id===link.source)!.x" :stroke-width="12" stroke="transparent" class="trace-hit-line" :y1="traceGraph.nodes.find(n=>n.id===link.source)!.y+24" :x2="traceGraph.nodes.find(n=>n.id===link.target)!.x" :y2="traceGraph.nodes.find(n=>n.id===link.target)!.y-24"/><line :x1="traceGraph.nodes.find(n=>n.id===link.source)!.x" :y1="traceGraph.nodes.find(n=>n.id===link.source)!.y+24" :x2="traceGraph.nodes.find(n=>n.id===link.target)!.x" :y2="traceGraph.nodes.find(n=>n.id===link.target)!.y-24" :class="['trace-edge',selectedTraceNode && link.source!==selectedTraceNode.id && link.target!==selectedTraceNode.id?'trace-muted':'',traceLinkSelection===link.source+'|'+link.target?'trace-edge-selected':'']"/>
            <text :x="(traceGraph.nodes.find(n=>n.id===link.source)!.x+traceGraph.nodes.find(n=>n.id===link.target)!.x)/2+7" :y="(traceGraph.nodes.find(n=>n.id===link.source)!.y+traceGraph.nodes.find(n=>n.id===link.target)!.y)/2-5" class="trace-edge-label">{{link.label}}</text>
           </template>
          </g>
          <g v-for="node in traceGraph.nodes" :key="node.id" data-trace-node tabindex="0" role="button" :aria-label="'Inspect '+node.label" :aria-pressed="traceSelection===node.id" :transform="`translate(${node.x} ${node.y})`" class="trace-node" @click="traceSelection=node.id;traceLinkSelection=''" @keydown.enter.prevent="traceSelection=node.id;traceLinkSelection=''" @keydown.space.prevent="traceSelection=node.id;traceLinkSelection=''">
           <rect x="-92" y="-28" width="184" height="56" rx="10" :class="['trace-node-box','trace-'+node.kind,traceSelection===node.id?'trace-selected':'']"/>
           <text text-anchor="middle" y="-5" class="trace-node-label">{{node.label.length>23?node.label.slice(0,21)+'…':node.label}}</text>
           <text text-anchor="middle" y="13" class="trace-node-subtitle">{{node.subtitle.length>27?node.subtitle.slice(0,25)+'…':node.subtitle}}</text>
          </g>
         </g>
        </svg>
       </div>
       <aside class="trace-inspector" aria-live="polite">
        <template v-if="selectedTraceLink && traceLinkExplanation">
         <h5>{{traceLinkExplanation.title}}</h5>
         <p>{{traceLinkExplanation.meaning}}</p>
         <p class="subdued"><strong>Evidence source:</strong> {{traceLinkExplanation.source}}</p>
         <p class="trace-limitation"><strong>Boundary:</strong> {{traceLinkExplanation.limitation}}</p>
         <details><summary>Inspect supporting graph paths</summary><pre>{{JSON.stringify(traceLinkExplanation.evidence,null,2)}}</pre></details>
        </template>
        <template v-else-if="selectedTraceNode">
         <h5>{{selectedTraceNode.label}}</h5>
         <p class="subdued">{{selectedTraceNode.subtitle}}</p>
         <dl><dt>Virtual node ID</dt><dd><code>{{selectedTraceNode.id}}</code></dd>
          <template v-if="selectedTraceNode.source"><dt>Node type</dt><dd>{{selectedTraceNode.source.type}}</dd><dt>Source metadata</dt><dd><pre>{{JSON.stringify(selectedTraceNode.source,null,2)}}</pre></dd></template>
         </dl>
         <details v-if="selectedTracePaths.length"><summary>Reasoning source paths ({{selectedTracePaths.length}})</summary><pre>{{JSON.stringify(selectedTracePaths,null,2)}}</pre></details>
         <template v-if="selectedTraceNode.kind==='asset'"><p>GraphDB shared asset identifier: <code>{{r01.asset.identifier}}</code></p></template>
         <template v-if="selectedTraceNode.kind==='signal'"><p>{{r01.observationCount}} observations associated with {{r01.signal.signalId}}.</p><button type="button" class="secondary" @click="selectedReasoningTab='evidence'">Inspect observations</button></template>
         <template v-if="selectedTraceNode.kind==='observations'"><button type="button" class="secondary" @click="selectedReasoningTab='evidence'">Open observation evidence</button></template>
         <template v-if="selectedTraceNode.kind==='function'"><details><summary>GraphDB-derived engineering association</summary><pre>{{JSON.stringify(reasoning!.R02.engineeringFunctions.find(fn=>fn.id===selectedTraceNode!.id)?.path ?? [],null,2)}}</pre></details></template>
        </template>
        <template v-else><h5>Inspect an entity</h5><p class="subdued">Choose a node or a connecting line to learn what it means, where its evidence comes from, and what it does not prove.</p></template>
       </aside>
      </div>
      <div class="trace-legend"><strong>Click a line to explain its meaning.</strong><span>● Engineering function</span><span>● Shared asset</span><span>● Operational signal</span><span>— Virtual reasoning association</span></div>
      <p class="subdued">The lines summarize query-scoped reasoning associations, not direct source RDF triples. Source paths are available in the inspector. Physical sensor identity is NOT_VERIFIED.</p>
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
      <div class="reasoning-interpretation">
       <h5>What does this reasoning mean?</h5>
       <div class="interpretation-pills" role="group" aria-label="Explain reasoning operator">
        <button v-for="item in reasoningInterpretations" :key="item.id" type="button" :class="selectedReasoningExplanation===item.id?'primary':'secondary'" :aria-pressed="selectedReasoningExplanation===item.id" @click="selectedReasoningExplanation=item.id">{{item.id}}</button>
       </div>
       <template v-if="activeReasoningInterpretation">
        <h5>{{activeReasoningInterpretation.question}}</h5>
        <p>{{activeReasoningInterpretation.conclusion}}</p>
        <p><strong>Evidence:</strong> {{activeReasoningInterpretation.evidence}}</p>
        <p class="trace-limitation"><strong>What it does not prove:</strong> {{activeReasoningInterpretation.limit}}</p>
        <button type="button" class="secondary" @click="traceOperator=activeReasoningInterpretation.id">Highlight in graph: {{activeReasoningInterpretation.id}}</button>
       </template>
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
 </section>
</template>

<style scoped>
.unified-section-heading { margin:24px 0 12px; padding-top:16px; border-top:1px solid #334a62; }\n.unified-ready { color:#86efac; }
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
.trace-heading { display:flex; justify-content:space-between; align-items:flex-start; gap:14px; flex-wrap:wrap; }
.trace-controls { display:flex; gap:6px; align-items:center; flex-wrap:wrap; }
.trace-controls label { font-size:12px; color:#b5c8d9; }
.trace-controls select { max-width:180px; background:#14263b; color:#eaf4ff; border:1px solid #3d5973; border-radius:7px; padding:7px; }
.trace-controls button { min-width:32px; }
.trace-layout { display:grid; grid-template-columns:minmax(0,2fr) minmax(210px,1fr); gap:12px; margin-top:12px; }
.trace-canvas { background:#0c192a; border:1px solid #334a62; border-radius:12px; overflow:hidden; touch-action:none; cursor:grab; }
.trace-canvas:active { cursor:grabbing; }
.trace-canvas svg { display:block; width:100%; min-height:360px; }
.trace-edge { stroke:#8ba5c0; stroke-width:1.8; stroke-dasharray:5 4; }
.trace-edge-label { fill:#9fb5c9; font-size:10px; }
.trace-muted { opacity:.18; }
.trace-node { cursor:pointer; outline:none; }
.trace-node:focus-visible .trace-node-box { stroke:#fff; stroke-width:3; }
.trace-node-box { fill:#1a3551; stroke:#6387ac; stroke-width:1.6; }
.trace-asset { fill:#33334c; stroke:#a7a3d2; }
.trace-signal { fill:#154d47; stroke:#44ad98; }
.trace-run,.trace-observations { fill:#283b4e; stroke:#8aa1b8; }
.trace-selected { stroke:#fbbf24; stroke-width:3; }
.trace-node-label { fill:#f0f8ff; font-size:13px; font-weight:600; pointer-events:none; }
.trace-node-subtitle { fill:#b5c8d9; font-size:10px; pointer-events:none; }
.trace-inspector { background:#14263b; border:1px solid #334a62; border-radius:10px; padding:12px; min-width:0; overflow-wrap:anywhere; }
.trace-inspector h5 { margin:0 0 6px; font-size:15px; }
.trace-inspector dt { font-size:11px; color:#b5c8d9; margin-top:10px; }
.trace-inspector dd { margin:4px 0; font-size:12px; }
.trace-inspector code { overflow-wrap:anywhere; }
.trace-inspector pre { max-height:200px; }
.trace-legend { display:flex; flex-wrap:wrap; gap:12px; font-size:11px; color:#b5c8d9; margin-top:10px; }
@media(max-width:800px) { .trace-layout { grid-template-columns:minmax(0,1fr); } }
.trace-link-hit { cursor:pointer; outline:none; }
.trace-link-hit:focus-visible .trace-edge,.trace-edge-selected { stroke:#fbbf24; stroke-width:3.5; stroke-dasharray:none; }
.trace-hit-line { pointer-events:stroke; }
.trace-limitation { border-left:3px solid #d6a14a; padding:8px 10px; background:rgba(184,138,66,.10); font-size:13px; }
.reasoning-interpretation { border-top:1px solid #334a62; margin-top:14px; padding-top:14px; }
.reasoning-interpretation h5 { font-size:15px; margin:10px 0; }
.interpretation-pills { display:flex; flex-wrap:wrap; gap:7px; }
.cross-domain-bridge { margin:20px 0; }
.bridge-steps { display:flex; align-items:stretch; gap:8px; margin:14px 0; }
.bridge-step { flex:1; min-width:0; background:#14263b; border:1px solid #334a62; border-radius:10px; padding:12px; display:flex; flex-direction:column; gap:8px; overflow-wrap:anywhere; }
.bridge-step small { color:#b5c8d9; }
.bridge-step strong { font-size:13px; }
.bridge-step span { color:#b5c8d9; font-size:11px; }
.bridge-arrow { align-self:center; color:#86efac; font-size:22px; }
.bridge-source-status { display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:10px; margin:12px 0; }
.bridge-source-status > div { border:1px dashed #63768b; border-radius:8px; padding:12px; display:flex; flex-direction:column; gap:6px; }
.bridge-source-status span { color:#fbbf24; font-size:12px; }
@media(max-width:760px) { .bridge-steps { flex-direction:column; } .bridge-arrow { transform:rotate(90deg); } .bridge-source-status { grid-template-columns:1fr; } }
.explore-knowledge-action { margin:18px 0; padding:16px; border:1px solid #4b667c; border-radius:12px; display:flex; flex-wrap:wrap; align-items:center; gap:12px; }
.explore-knowledge-action p { flex-basis:100%; margin:0; }
</style>
