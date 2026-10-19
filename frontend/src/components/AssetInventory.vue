<script setup lang="ts">
import { computed, ref, watch, onMounted, onUnmounted } from 'vue'
import EngineeringRdfGraph from './EngineeringRdfGraph.vue'
import { Factory, Search, Network, Package } from 'lucide-vue-next'
import { selectTriples, KG_TYPE, KG_VOCAB, localName, type Triple } from '../lib/sparql'
import AssetStatusKnowledgeGraph from './AssetStatusKnowledgeGraph.vue'

type AssetRecord = { id: string; fields: Record<string, string> }
const assetType = 'https://example.org/assetinventory/Asset'
const assetNS = 'https://example.org/assetinventory/'
const productNS = 'https://example.org/productcatalog/'
const productType = 'https://example.org/productcatalog/Product'
type LiveSnapshot = {simulation:{Running:boolean;TimeHours:number};measurements:number[];manipulatedVariables:number[]}
type LiveFault = {fault_id:string;fault_type:string;target:string;status:string}
const live = ref<LiveSnapshot|null>(null)
const liveFaults = ref<LiveFault[]>([])
const liveError = ref('')
let liveTimer:ReturnType<typeof setInterval>|undefined
async function refreshLive(){
 try{
  const [h,f]=await Promise.all([fetch('/api/simulation/history'),fetch('/api/simulation/faults')])
  const history=await h.json(),faults=await f.json()
  if(!h.ok||!history.snapshot)throw new Error(history.error||'Simulation unavailable')
  live.value=history.snapshot
  liveFaults.value=f.ok?faults.faults:[]
  liveError.value=f.ok?'':'Fault listing unavailable'
 }catch(e){live.value=null;liveFaults.value=[];liveError.value=e instanceof Error?e.message:String(e)}
}
onMounted(()=>{void refreshLive();liveTimer=setInterval(()=>void refreshLive(),4000)})
onUnmounted(()=>{if(liveTimer)clearInterval(liveTimer)})
function signalValue(reference:string){
 const match=reference.toUpperCase().match(/(?:^|[^A-Z])X(MEAS|MV)[-_]?(\d+)(?!\d)/)
 if(!match||!live.value)return null
 const index=Number(match[2])-1
 const values=match[1]==='MEAS'?live.value.measurements:live.value.manipulatedVariables
 return index>=0&&index<values.length?{name:'X'+match[1]+(index+1),value:values[index]}:null
}
const selectedSignal=computed(()=>selected.value?signalValue(selected.value.fields.OperationalReference||selected.value.fields.OperationalSignalIRI||''):null)
const relatedFaults=computed(()=>selectedSignal.value?liveFaults.value.filter(f=>f.target.toUpperCase()===selectedSignal.value?.name):[])
const runtimeStatus=computed(()=>{
 if(!live.value)return 'Unknown'
 if(relatedFaults.value.some(f=>f.status==='active'))return 'Signal fault active'
 return live.value.simulation.Running?'Running (signal not verified)':'Stopped'
})

type HistoricalRun = {runId:string;startedAt:string;endedAt:string|null;sampleCount:number;faultEventCount:number}
type HistoricalPoint = {time:number;value:number;observedAt:string}
type AssetHistory = {status:string;signal?:string;signals:string[];points:HistoricalPoint[];faultEvents:{eventId:string;faultId:string;action:string;target:string;observedAt:string}[]}
const historicalRuns=ref<HistoricalRun[]>([])
const historicalRunId=ref('')
const historicalData=ref<AssetHistory|null>(null)
const historicalLoading=ref(false)
const runFaultEvents=ref<{event_id:string;fault_id:string;action:string;target:string;simulation_time_hours:number;observed_at:string}[]>([])
const replayIndex=ref(0)
const replayPlaying=ref(false)
let replayTimer:ReturnType<typeof setInterval>|undefined
onUnmounted(()=>{if(replayTimer)clearInterval(replayTimer)})
watch(replayPlaying,playing=>{if(replayTimer)clearInterval(replayTimer);if(playing)replayTimer=setInterval(()=>{const count=historicalData.value?.points.length||0;if(replayIndex.value>=count-1){replayPlaying.value=false;return}replayIndex.value++},250)})
const replayPoint=computed(()=>historicalData.value?.points[replayIndex.value]||null)
const chart=computed(()=>{const pts=historicalData.value?.points||[];if(!pts.length)return null;const times=pts.map(p=>p.time),values=pts.map(p=>p.value);const minT=Math.min(...times),maxT=Math.max(...times),minV=Math.min(...values),maxV=Math.max(...values);const x=(t:number)=>50+(t-minT)/(maxT-minT||1)*700;const y=(v:number)=>215-(v-minV)/(maxV-minV||1)*185;return {line:pts.map((p,i)=>`${i?'L':'M'}${x(p.time).toFixed(2)},${y(p.value).toFixed(2)}`).join(' '),minT,maxT,minV,maxV,x,y}})
const chartFaults=computed(()=>runFaultEvents.value.filter(e=>Number.isFinite(e.simulation_time_hours)&&chart.value&&e.simulation_time_hours>=chart.value.minT&&e.simulation_time_hours<=chart.value.maxT))
const historicalError=ref('')
async function loadHistoricalRuns(){
 try {
  const response=await fetch('/api/simulation/runs?limit=100')
  const data=await response.json()
  if(!response.ok)throw new Error(data.error||'Run discovery failed')
  historicalRuns.value=data.runs
  if(!historicalRuns.value.some(r=>r.runId===historicalRunId.value))historicalRunId.value=historicalRuns.value[0]?.runId||''
 }catch(e){historicalError.value=e instanceof Error?e.message:String(e)}
}
let historicalRequest=0
async function loadAssetHistory(){
 const request=++historicalRequest
 historicalData.value=null
 runFaultEvents.value=[]
 replayPlaying.value=false
 replayIndex.value=0
 historicalError.value=''
 if(!selected.value||!historicalRunId.value)return
 historicalLoading.value=true
 try {
  const params=new URLSearchParams({assetIri:selected.value.id,runId:historicalRunId.value,limit:'500'})
  const response=await fetch('/api/semantic/asset-history?'+params)
  const data=await response.json()
  if(!response.ok)throw new Error(data.error||'Historical query failed')
  if(request===historicalRequest){historicalData.value=data;const faultResponse=await fetch('/api/simulation/fault-events/history?'+new URLSearchParams({runId:historicalRunId.value,limit:'5000'}));const faultPayload=await faultResponse.json();if(!faultResponse.ok)throw new Error(faultPayload.error||'Fault timeline unavailable');if(request===historicalRequest)runFaultEvents.value=faultPayload.events}
 }catch(e){if(request===historicalRequest)historicalError.value=e instanceof Error?e.message:String(e)}
 finally{if(request===historicalRequest)historicalLoading.value=false}
}

const statusKeys = ['ModelingStatus', 'SimulationStatus', 'MonitoringStatus', 'FaultInjectionStatus', 'FaultDetectionStatus']
const triples = ref<Triple[]>([])
const domainGraphOpen = ref(false)
const loading = ref(false)
const error = ref('')
const query = ref('')
const selectedId = ref('')
const detailTab = ref<'Status' | 'Knowledge Graph'>('Status')

const assets = computed<AssetRecord[]>(() => {
  const ids = [...new Set(triples.value.filter(t => t.predicate === KG_TYPE && t.object === assetType).map(t => t.subject))]
  return ids.map(id => {
    const fields: Record<string, string> = { AssetId: id }
    const own = triples.value.filter(t => t.subject === id)
    for (const t of own) {
      if (t.predicate.startsWith(assetNS)) {
        if (t.predicate === assetNS + 'hasProductReference') fields.ProductReference = t.object
        else if (t.predicate === assetNS + 'hasOperationalReference') fields.OperationalSignalIRI = t.object
        else if (t.predicate === assetNS + 'hasAssetInventoryStatus') fields.StatusReference = t.object
        else { const key = localName(t.predicate).replace(/^has/, ''); if (key !== 'AssetId') fields[key] = t.object }
      }
    }
    if (fields.StatusReference) {
      for (const t of triples.value.filter(t => t.subject === fields.StatusReference && (t.predicate.startsWith(assetNS) || t.predicate.startsWith(productNS)))) {
        fields[localName(t.predicate)] = t.object
      }
    }
    if (!fields.OperationalReference && fields.OperationalSignalIRI) fields.OperationalReference = localName(fields.OperationalSignalIRI)
    return { id, fields }
  }).sort((a, b) => (a.fields.EquipmentTag || a.id).localeCompare(b.fields.EquipmentTag || b.id))
})
const products = computed<Record<string, Record<string, string>>>(() => {
  const result: Record<string, Record<string, string>> = {}
  const ids = [...new Set(triples.value.filter(t => t.predicate === KG_TYPE && t.object === productType).map(t => t.subject))]
  for (const id of ids) {
    const fields: Record<string, string> = {}
    for (const t of triples.value.filter(t => t.subject === id && t.predicate.startsWith(KG_VOCAB))) fields[localName(t.predicate)] = t.object
    result[id] = fields
  }
  return result
})
async function load() {
  loading.value = true
  error.value = ''
  try {
    const data = await selectTriples(`SELECT ?s ?p ?o WHERE {
      GRAPH ?g {
        { ?s a <${assetType}> ; ?p ?o . }
        UNION { ?s a <${productType}> ; ?p ?o . }
        UNION { ?s <${productNS}hasManufacturerPartNumber> ?part ; ?p ?o . }
      }
    } LIMIT 20000`)
    triples.value = data
    if (!assets.value.length) error.value = 'No lifted Asset resources found. Check the AssetInventory named graph and SPARQL query.'
  } catch (e) {
    triples.value = []
    error.value = e instanceof Error ? e.message : 'Unable to query GraphDB AAS.'
  } finally {
    loading.value = false
  }
}
watch(assets, list => {
  if (!list.some(a => a.id === selectedId.value)) selectedId.value = list[0]?.id || ''
}, { immediate: true })
void load()
const filtered = computed(() => {
  const term = query.value.trim().toLowerCase()
  return assets.value.filter(a => [a.id, ...Object.values(a.fields)].join(' ').toLowerCase().includes(term))
})
const selected = computed(() => filtered.value.find(a => a.id === selectedId.value) ?? filtered.value[0] ?? null)
watch([selectedId,historicalRunId],()=>{void loadAssetHistory()})
onMounted(()=>{void loadHistoricalRuns()})
watch(historicalRuns,()=>{void loadAssetHistory()})

const productTypeCount = computed(() => new Set(assets.value.map(a => a.fields.ProductReference).filter(ref => ref && products.value[ref])).size)
const signalCount = computed(() => assets.value.filter(a => a.fields.OperationalReference).length)
const readable = (s: string) => s.replace(/([a-z])([A-Z])/g, '$1 $2')
const statusLabel = (value: string) => readable(value || 'Unknown')
</script>
<template>
  <div class="graph-toolbar" style="display:flex;gap:8px;margin-bottom:12px"><button type="button" class="secondary" :aria-pressed="domainGraphOpen" @click="domainGraphOpen=!domainGraphOpen">{{ domainGraphOpen ? 'Show catalog details' : 'Domain Knowledge Graph' }}</button></div>
  <EngineeringRdfGraph v-if="domainGraphOpen" domain="assetinventory" />
  <template v-else>
 <section class="catalog asset-inventory">
  <p v-if="loading" role="status">Loading AssetInventory from GraphDB AAS…</p>
  <p v-if="error" role="alert" class="catalog-disclaimer">{{ error }} <button class="secondary" type="button" @click="load">Retry</button></p>
  <div class="metric-grid">
   <div class="metric"><Factory :size="18"/><small>ASSET INSTANCES</small><strong>{{ assets.length }}</strong></div>
   <div class="metric"><Network :size="18"/><small>OPERATIONAL SIGNALS</small><strong>{{ signalCount }}</strong></div>
   <div class="metric"><Package :size="18"/><small>PRODUCT TYPES</small><strong>{{ productTypeCount }}</strong></div>
  </div>
  <div class="catalog-layout">
   <section class="panel catalog-list">
    <div class="panel-title"><div><h2>Asset explorer</h2><p>GraphDB AAS · simulated engineering assets</p></div><span class="pill">{{ filtered.length }} / {{ assets.length }}</span></div>
    <label class="search"><Search :size="16"/><input v-model="query" aria-label="Search assets" placeholder="Search tags, signals, assets..."/></label>
    <button v-if="query" class="secondary" type="button" @click="query=''">Clear search</button>
    <div class="catalog-results">
     <button v-for="asset in filtered" :key="asset.id" class="asset-row catalog-item" :class="{highlight:selected?.id===asset.id}" @click="selectedId=asset.id;detailTab='Status'">
      <span class="asset-icon"><Factory :size="17"/></span><span><strong>{{ asset.fields.EquipmentTag || localName(asset.id) }}</strong><small>{{ asset.fields.AssetName || 'Unnamed simulated asset' }}</small><small>{{ asset.fields.AssetType || 'SimulatedAsset' }}</small></span>
     </button>
     <p v-if="!filtered.length && !loading" class="empty">No matching assets in the KG.</p>
    </div>
   </section>
   <section class="panel catalog-detail" v-if="selected">
    <div class="panel-title"><div><h2>{{ selected.fields.AssetName || localName(selected.id) }}</h2><p>{{ selected.fields.EquipmentTag || localName(selected.id) }} · {{ selected.fields.AssetType || 'SimulatedAsset' }}</p></div><span class="pill">KG ASSET</span></div>
    <div class="tabs"><button :class="{selected:detailTab==='Status'}" @click="detailTab='Status'">Asset status</button><button :class="{selected:detailTab==='Knowledge Graph'}" @click="detailTab='Knowledge Graph'">Knowledge graph</button></div>
    <AssetStatusKnowledgeGraph v-if="detailTab==='Knowledge Graph'" :key="selected.id" :asset="selected" />
    <template v-else>
     <h2 class="catalog-section-title">Live operational state</h2>
     <div class="catalog-properties">
      <div class="catalog-property"><span>Runtime status</span><strong>{{runtimeStatus}}</strong></div>
      <div class="catalog-property"><span>Simulator time</span><span>{{live?live.simulation.TimeHours.toFixed(3)+' h':'Unavailable'}}</span></div>
      <div class="catalog-property"><span>Mapped OPC UA signal</span><span>{{selectedSignal?.name||'Not mapped / unverified'}}</span></div>
      <div class="catalog-property"><span>Live signal value</span><strong>{{selectedSignal?selectedSignal.value.toFixed(3):'—'}}</strong></div>
      <div class="catalog-property"><span>Direct signal faults</span><span>{{relatedFaults.filter(f=>f.status==='active').length}}</span></div>
     </div>
     <p v-if="liveError" class="catalog-disclaimer">{{liveError}}</p>
     <p class="catalog-disclaimer">Runtime status describes simulator state and directly matched signal faults only. No asset-level process alarm limits or process-disturbance impact mapping have been validated.</p>

     <h2 class="catalog-section-title">Historical operational state</h2>
     <div class="catalog-properties">
      <div class="catalog-property"><label for="asset-history-run">Simulation run</label>
       <select id="asset-history-run" v-model="historicalRunId">
        <option value="">Select a run</option>
        <option v-for="run in historicalRuns" :key="run.runId" :value="run.runId">{{new Date(run.startedAt).toLocaleString()}} · {{run.sampleCount}} samples · {{run.faultEventCount}} faults</option>
       </select>
      </div>
      <div class="catalog-property"><span>Run ID</span><span class="catalog-wrap">{{historicalRunId||'None'}}</span></div>
     </div>
     <button class="secondary" type="button" @click="loadHistoricalRuns">Refresh runs</button>
     <p v-if="historicalLoading" role="status">Loading historical measurements…</p>
     <p v-if="historicalError" role="alert" class="catalog-disclaimer">{{historicalError}}</p>
     <template v-if="historicalData">
      <div class="catalog-properties">
       <div class="catalog-property"><span>Mapping status</span><strong>{{historicalData.status}}</strong></div>
       <div class="catalog-property"><span>Resolved signal</span><span>{{historicalData.signal||historicalData.signals.join(', ')||'Unmapped'}}</span></div>
       <div class="catalog-property"><span>Retrieved measurements</span><strong>{{historicalData.points.length}}</strong></div>
       <div class="catalog-property"><span>Direct signal fault events</span><strong>{{historicalData.faultEvents.length}}</strong></div>
      </div>
      <p v-if="historicalData.status!=='mapped'" class="catalog-disclaimer">No unique historical signal mapping exists for this asset.</p>
      <template v-else>
       <p v-if="!historicalData.points.length" class="catalog-disclaimer">No measurements found for this asset in the selected run.</p>
       <template v-if="chart">
        <h2 class="catalog-section-title">Historical trend and run fault timeline</h2>
        <svg viewBox="0 0 780 265" role="img" :aria-label="'Historical trend for '+historicalData.signal" style="width:100%;height:auto;border:1px solid var(--border,#d6dce3);border-radius:8px">
         <line x1="50" y1="215" x2="750" y2="215" stroke="currentColor" opacity=".45"/>
         <line x1="50" y1="30" x2="50" y2="215" stroke="currentColor" opacity=".45"/>
         <path :d="chart.line" fill="none" stroke="#0c8797" stroke-width="2"/>
         <g v-for="event in chartFaults" :key="event.event_id">
          <line :x1="chart.x(event.simulation_time_hours)" y1="30" :x2="chart.x(event.simulation_time_hours)" y2="215" :stroke="event.action==='inject'?'#d97706':'#7c3aed'" stroke-dasharray="5 4" stroke-width="2"/>
          <title>{{event.action}} · {{event.fault_id}} · {{event.target}} · {{event.simulation_time_hours.toFixed(4)}} h</title>
         </g>
         <circle v-if="replayPoint" :cx="chart.x(replayPoint.time)" :cy="chart.y(replayPoint.value)" r="5" fill="#0c8797" stroke="white" stroke-width="2"/>
         <text x="50" y="245" font-size="13" fill="currentColor">{{chart.minT.toFixed(3)}} h</text>
         <text x="750" y="245" text-anchor="end" font-size="13" fill="currentColor">{{chart.maxT.toFixed(3)}} h</text>
         <text x="55" y="25" font-size="13" fill="currentColor">{{chart.maxV.toFixed(2)}}</text>
         <text x="55" y="208" font-size="13" fill="currentColor">{{chart.minV.toFixed(2)}}</text>
        </svg>
        <div style="display:flex;gap:12px;align-items:center;flex-wrap:wrap;margin:10px 0">
         <button type="button" class="secondary" @click="replayPlaying=!replayPlaying">{{replayPlaying?'Pause':'Play'}} replay</button>
         <input type="range" min="0" :max="Math.max(0,historicalData.points.length-1)" v-model.number="replayIndex" aria-label="Replay sample index" style="flex:1;min-width:120px"/>
         <span v-if="replayPoint">{{replayPoint.time.toFixed(4)}} h · {{replayPoint.value.toFixed(4)}}</span>
        </div>
        <p class="catalog-disclaimer">Orange dashed lines: fault injections. Purple: clearing events. These are run-level events, not verified causes of changes in this signal. Events outside the displayed measurement window are listed below.</p>
        <div v-for="event in runFaultEvents" :key="event.event_id" class="catalog-property"><span>{{event.action}} · {{event.fault_id}} · {{event.target}}</span><span>{{event.simulation_time_hours.toFixed(4)}} h</span></div>
       </template>
       <div v-else style="max-height:240px;overflow:auto">
        <table style="width:100%;text-align:left"><thead><tr><th>Simulation time (h)</th><th>Value</th><th>Observed at</th></tr></thead>
         <tbody><tr v-for="(point,index) in historicalData.points" :key="index"><td>{{point.time.toFixed(4)}}</td><td>{{point.value.toFixed(4)}}</td><td>{{new Date(point.observedAt).toLocaleString()}}</td></tr></tbody>
        </table>
       </div>
       <p v-if="!historicalData.faultEvents.length" class="catalog-disclaimer">No directly targeted signal fault events recorded. Process-disturbance impacts are not inferred.</p>
       <div v-for="event in historicalData.faultEvents" :key="event.eventId" class="catalog-property"><span>{{event.action}} · {{event.faultId}}</span><span>{{new Date(event.observedAt).toLocaleString()}}</span></div>
      </template>
     </template>
     <h2 class="catalog-section-title">Engineering lifecycle status (GraphDB)</h2>
     <div class="catalog-properties">
      <div v-for="key in statusKeys" :key="key" class="catalog-property"><span>{{ readable(key) }}</span><span>{{ statusLabel(selected.fields[key]) }}</span></div>
     </div>
     <h2 class="catalog-section-title">Product catalog</h2>
     <div class="catalog-properties" v-if="selected.fields.ProductReference && products[selected.fields.ProductReference]">
      <div class="catalog-property"><span>Manufacturer</span><span>{{ products[selected.fields.ProductReference].ManufacturerName || 'Not assigned' }}</span></div>
      <div class="catalog-property"><span>Part number</span><span>{{ products[selected.fields.ProductReference].ManufacturerPartNumber || 'Not assigned' }}</span></div>
      <div class="catalog-property"><span>Product RDF IRI</span><span class="catalog-wrap">{{ selected.fields.ProductReference }}</span></div>
     </div>
     <p v-else class="catalog-disclaimer">No matching product type is defined in the KG for this simulated asset.</p>
     <h2 class="catalog-section-title">Engineering & identification</h2>
     <div class="catalog-properties">
      <div v-for="(value,key) in Object.fromEntries(Object.entries(selected.fields).filter(([key]) => !statusKeys.includes(key)))" :key="key" class="catalog-property"><span>{{ readable(String(key)) }}</span><span class="catalog-wrap">{{ value || 'Not assigned' }}</span></div>
     </div>
     <p class="catalog-disclaimer">Engineering associations are RDF references, not evidence of verified physical installation. GraphDB lifecycle status is engineering metadata; live operational state is calculated separately and is not written to GraphDB.</p>
    </template>
   </section>
  </div>
  <p class="catalog-disclaimer">AssetInventory list, counters, statuses, product references and KG visualization are queried from GraphDB repository AAS. Live OPC UA status is shown separately where an existing operational signal reference can be resolved.</p>
 </section>
  </template>
</template>
