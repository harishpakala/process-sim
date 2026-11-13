<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { selectTriples } from './lib/sparql'
import SimulationDashboard from './components/SimulationDashboard.vue'
import FaultManagement from './components/FaultManagement.vue'
import PaperAiQuery from './components/PaperAiQuery.vue'
import BenchmarkDiagnostics from './components/BenchmarkDiagnostics.vue'
import OntologyQ13Audit from './components/OntologyQ13Audit.vue'
import ProductCatalog from './components/ProductCatalog.vue'
import EngineeringBom from './components/EngineeringBom.vue'
import EngineeringVerificationWorkbench from './components/EngineeringVerificationWorkbench.vue'
import EngineeringRdfGraph from './components/EngineeringRdfGraph.vue'
import TraceabilityExplorer from './components/TraceabilityExplorer.vue'
import AssetInventory from './components/AssetInventory.vue'
import OpcuaConnectivity from './components/OpcuaConnectivity.vue'
import MultiSignalReplay from './components/MultiSignalReplay.vue'
import { Activity, Atom, BrainCircuit, ChevronDown, ChevronRight, CircuitBoard, Database, Factory, FlaskConical, GitBranch, LayoutDashboard, Network, Package, Play, RotateCcw, Search, Settings2, ShieldCheck, Workflow } from 'lucide-vue-next'
const sections = [
 {name:'ENGINEERING',items:['DEXPI Explorer','ECAD Explorer','Engineering BOM','Relationship Verification','Product Catalog']},
 {name:'SIMULATION',items:['Simulation Control','Plant Monitor','Signal Explorer','Multi-Signal Replay','Faults & Disturbances','Experiments']},
 {name:'ERP',items:['Asset Inventory','Material Master','Supplier Master','Procurement','Stock Inventory','Maintenance','Cost Management']},
 {name:'SYSTEM & SEMANTICS',items:['Traceability','Data Quality','Semantic Models','OPC UA Connectivity','Reports','Settings']}
]
const opened=ref<Record<string,boolean>>({'ENGINEERING':true,'SIMULATION':true,'ERP':false,'SYSTEM & SEMANTICS':false})
const active=ref('Overview')
const selected=ref('R-001')
const destinationId=ref('')
const navigationKey=ref(0)
function openRecord(destination: string, identifier: string) {
 navigate(destination)
 destinationId.value=identifier
 navigationKey.value++
 const group=sections.find(section=>section.items.includes(destination))
 if(group)opened.value[group.name]=true
}
const view=ref<'Engineering'|'Knowledge Graph'>('Engineering')
const demoRunning=ref(false)
const graphdbStatus=ref<'checking'|'connected'|'disconnected'>('checking')
const graphdbError=ref('')
async function checkGraphDB() {
 graphdbStatus.value='checking'
 graphdbError.value=''
 try {
  await selectTriples('SELECT ?s ?p ?o WHERE { GRAPH ?g { ?s ?p ?o } } LIMIT 1')
  graphdbStatus.value='connected'
 } catch(e) {
  graphdbStatus.value='disconnected'
  graphdbError.value=e instanceof Error?e.message:String(e)
 }
}
onMounted(()=>{void checkGraphDB()})
const search=ref('')
const assets=[{tag:'R-001',name:'Reactor',kind:'Equipment'},{tag:'C-001',name:'Condenser',kind:'Equipment'},{tag:'V-001',name:'Separator',kind:'Equipment'},{tag:'K-001',name:'Compressor',kind:'Equipment'},{tag:'S-001',name:'Stripper',kind:'Equipment'}]
const filtered=computed(()=>assets.filter(a=>(a.tag+' '+a.name).toLowerCase().includes(search.value.toLowerCase())))
const graphView=computed(()=>['DEXPI Explorer','ECAD Explorer'].includes(active.value))
function navigate(page:string){active.value=page;view.value='Engineering';destinationId.value=''}
</script>

<template>
 <div class="app">
  <aside class="sidebar">
   <div class="brand"><span class="brand-mark"><Atom :size="23"/></span><div><strong>TEP NEXUS</strong><small>SEMANTIC DIGITAL TWIN</small></div></div>
   <div class="nav-scroll">
    <div class="section-label">WORKSPACE</div>
    <button class="nav-item" :class="{current:active==='Overview'}" @click="navigate('Overview')"><LayoutDashboard :size="16"/> Overview</button>
    <button class="nav-item" :class="{current:active==='AI Query'}" @click="navigate('AI Query')"><BrainCircuit :size="16"/> AI Query</button>
    <button class="nav-item" :class="{current:active==='Benchmarks'}" @click="navigate('Benchmarks')"><FlaskConical :size="16"/> Benchmarks</button>
    <button class="nav-item" :class="{current:active==='Q13 Ontology Trace'}" @click="navigate('Q13 Ontology Trace')"><GitBranch :size="16"/> Q13 Ontology Trace</button>
    <div v-for="group in sections" :key="group.name" class="nav-group">
     <button class="section-toggle" @click="opened[group.name]=!opened[group.name]">{{group.name}}<ChevronDown v-if="opened[group.name]" :size="14"/><ChevronRight v-else :size="14"/></button>
     <template v-if="opened[group.name]"><button v-for="item in group.items" :key="item" class="nav-item nested" :class="{current:active===item}" @click="navigate(item)"><span class="nav-dot"/> {{item}}</button></template>
    </div>
   </div>
   <div class="sidebar-foot"><span class="status-dot amber"/> Offline preview</div>
  </aside>
  <main class="main">
   <header class="topbar"><div class="breadcrumb">TEP / <span>{{active}}</span></div><div class="top-actions"><span class="pill muted">PROTOTYPE</span><Settings2 :size="18"/></div></header>
   <div class="content">
    <div class="page-heading"><div><div class="eyebrow">INDUSTRIAL INTELLIGENCE WORKSPACE</div><h1>{{active}}</h1><p>Engineering, simulation and semantic knowledge in one workspace.</p></div><div class="offline"><span class="status-dot amber"/> GraphDB {{graphdbStatus}} · Simulation preview</div></div>
    <template v-if="active==='Overview'||active==='Plant Monitor'">
     <div class="metric-grid">
      <div class="metric"><Activity :size="18"/><small>SIMULATION</small><strong>{{demoRunning?'Preview running':'Not connected'}}</strong></div>
      <div class="metric"><Network :size="18"/><small>KNOWLEDGE GRAPH</small><strong :title="graphdbError">GraphDB · {{graphdbStatus==='connected'?'Connected':graphdbStatus==='checking'?'Checking…':'Not connected'}}</strong><button class="secondary" type="button" @click="checkGraphDB">Retry</button></div>
      <div class="metric"><Factory :size="18"/><small>ENGINEERING</small><strong>DEXPI / ECAD</strong></div>
      <div class="metric"><ShieldCheck :size="18"/><small>VALIDATION</small><strong>Not checked</strong></div>
     </div>
     <div class="two-column">
      <section class="panel plant"><div class="panel-title"><div><h2>Tennessee Eastman Process</h2><p>Equipment overview · illustrative schematic</p></div><span class="pill">ENGINEERING</span></div>
       <svg class="process" viewBox="0 0 640 270" role="img" aria-label="Illustrative equipment schematic; connections are not verified DEXPI piping">
        <g fill="none" stroke="#367b92" stroke-width="3" stroke-dasharray="7 7"><path d="M80 115 H560"/><path d="M505 90 V35 H130 V90"/></g>
        <g v-for="(a,i) in assets" :key="a.tag" class="vessel" @click="selected=a.tag" tabindex="0" role="button" @keydown.enter="selected=a.tag">
         <rect :x="45+i*116" y="88" width="78" height="70" rx="16" :class="{chosen:selected===a.tag}"/>
         <text :x="84+i*116" y="129" text-anchor="middle">{{a.tag}}</text>
         <text class="vessel-name" :x="84+i*116" y="184" text-anchor="middle">{{a.name}}</text>
        </g>
        <text class="diagram-note" x="320" y="240" text-anchor="middle">Conceptual layout only — no piping connectivity inferred</text>
       </svg>
       <div class="chips"><button v-for="a in assets" :key="a.tag" class="chip" :class="{picked:selected===a.tag}" @click="selected=a.tag">{{a.tag}}</button></div>
      </section>
      <section class="panel"><div class="panel-title"><h2>Asset explorer</h2><span class="pill">DEXPI</span></div><label class="search"><Search :size="16"/><input v-model="search" placeholder="Search equipment..." /></label><button v-for="a in filtered" :key="a.tag" class="asset-row" :class="{highlight:selected===a.tag}" @click="selected=a.tag"><span class="asset-icon"><Factory :size="16"/></span><span><strong>{{a.tag}}</strong><small>{{a.name}}</small></span><ChevronRight :size="15"/></button><p v-if="!filtered.length" class="empty">No matching equipment</p></section>
     </div>
     <section class="panel"><div class="panel-title"><h2>Simulation quick controls</h2><span class="pill amber-pill">UI PREVIEW ONLY</span></div><div class="control-row"><button class="primary" @click="demoRunning=!demoRunning"><Play :size="16"/> {{demoRunning?'Pause preview':'Run preview'}}</button><button class="secondary" @click="demoRunning=false"><RotateCcw :size="16"/> Reset</button><span>These controls do not execute TEP.</span></div></section>
    </template>
    <template v-else-if="active==='Traceability'"><TraceabilityExplorer /></template>
    <template v-else-if="active==='OPC UA Connectivity'"><OpcuaConnectivity /></template>
    <template v-else-if="active==='Engineering BOM'"><EngineeringBom @open-record="openRecord" /></template>
    <template v-else-if="active==='Relationship Verification'"><EngineeringVerificationWorkbench /></template>
    <template v-else-if="active==='Product Catalog'"><ProductCatalog :key="navigationKey" :focus-id="active==='Product Catalog'?destinationId:''" @open-record="openRecord" /></template>
    <template v-else-if="active==='Asset Inventory'"><AssetInventory :key="navigationKey" :focus-id="active==='Asset Inventory'?destinationId:''" @open-record="openRecord" /></template>
    <template v-else-if="active==='Multi-Signal Replay'"><MultiSignalReplay /></template>
    <template v-else-if="graphView"><EngineeringRdfGraph :key="navigationKey" :domain="active==='ECAD Explorer'?'ecad':'dexpi'" :focus-identifier="destinationId" @open-record="openRecord" /></template>
    <template v-else-if="active==='AI Query'"><PaperAiQuery /></template>
    <template v-else-if="active==='Benchmarks'"><BenchmarkDiagnostics /></template>
    <template v-else-if="active==='Q13 Ontology Trace'"><OntologyQ13Audit /></template>
    <template v-else-if="active==='Simulation Control'"><SimulationDashboard /></template>
    <template v-else-if="active==='Faults & Disturbances'"><FaultManagement /></template>
    <template v-else><section class="panel placeholder"><Database :size="42"/><h2>{{active}}</h2><p>Workspace scaffold ready. Records, semantic links and validation results require backend integration.</p><span class="pill amber-pill">Not connected</span></section></template>
    <section v-if="!['Product Catalog','Asset Inventory','AI Query','Benchmarks','Q13 Ontology Trace'].includes(active)" class="context panel"><div class="panel-title"><h2>Selection context</h2><span class="pill">{{selected}}</span></div><div class="context-grid"><div><small>Engineering identifier</small><strong>{{selected}}</strong></div><div><small>Cross-domain links</small><strong>Not resolved</strong></div><div><small>Simulation signal mapping</small><strong>Not loaded</strong></div></div></section>
   </div>
  </main>
 </div>
</template>