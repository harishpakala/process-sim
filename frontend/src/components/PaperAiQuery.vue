<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'

withDefaults(defineProps<{ page?: 'engineering' | 'historian' }>(), {page: 'engineering'})

type DtwiseResult = {
 question: string; mode: string; sparql: string; executed: boolean;
 graph_mode: string; answer: Record<string, unknown>; plan: unknown
}
type BenchmarkQuestion = {id:string;category:string;question:string;version:string}
const benchmarkQuestions = ref<BenchmarkQuestion[]>([])
const category = ref('')
const benchmarkId = ref('')
const manifestError = ref('')
const MULTIHOP_CATEGORY = 'Multi Domain Multi Hop'
const selectableQuestions = computed(() => benchmarkQuestions.value)
const supplementalQuestions: BenchmarkQuestion[] = [
 {id:'MH1',category:MULTIHOP_CATEGORY,question:'Show the ProductIdentifier and ManufacturerName of products associated with DEXPI InstrumentationFunction entities.',version:'supplemental'},
 {id:'MH2',category:MULTIHOP_CATEGORY,question:'Show the ProductIdentifier and ProductDescription of products associated with DEXPI InstrumentationFunction entities.',version:'supplemental'},
 {id:'MH3',category:MULTIHOP_CATEGORY,question:'Show the ManufacturerName of products associated with DEXPI InstrumentationFunction entities.',version:'supplemental'},
 {id:'MH4',category:MULTIHOP_CATEGORY,question:'Show the AssetIdentifier and ProductIdentifier of assets associated with DEXPI InstrumentationFunction entities.',version:'supplemental'},
 {id:'B23.1',category:'Cross-domain',question:'Get SignalName of the ECAD Device with LocalID FI-1003.',version:'supplemental'},
 {id:'B23.2',category:'Cross-domain',question:'Get SignalName of the ECAD Device with LocalID LI-1101.',version:'supplemental'},
 {id:'B23.3',category:'Cross-domain',question:'Get SignalName of the DEXPI InstrumentationFunction with LocalID FI_105.',version:'supplemental'}
]
const benchmarkStages: { label: string; category: string }[] = [
 {label:'01 · Atomic Property Retrieval',category:'basic'},
 {label:'02 · Attribute-Based Selection and Logical Filtering',category:'filters'},
 {label:'03 · Multi-Attribute Projection',category:'multiple_projections'},
 {label:'04 · Aggregation and Grouping',category:'aggregation'},
 {label:'05 · Result Ordering and Pagination',category:'sorting_pagination'},
 {label:'06 · Natural-Language Paraphrase Robustness',category:'language_variation'},
 {label:'07 · Cross-Domain Semantic Joins',category:'cross_domain'},
 {label:'08 · Intra-Domain Optionality',category:'single_domain'},
 {label:'09 · Lexical and Pattern-Based Filtering',category:'string_filtering'},
 {label:'10 · Boolean Constraint Evaluation',category:'boolean'},
 {label:'11 · Multi-Hop Semantic Traversal',category:'multi_domain_multi_hop'}
]
const categories = computed(() => benchmarkStages.map(stage => stage.label))
const displayedQuestion = (item: BenchmarkQuestion): string => item.question
const categoryQuestions = computed(() => {
 const selectedStage = benchmarkStages.find(stage => stage.label === category.value)
 if (!selectedStage) return []
 const questions = benchmarkQuestions.value.filter(q => q.category === selectedStage.category)
 if (selectedStage.category === 'cross_domain') {
  questions.push(...supplementalQuestions.filter(q => q.id.startsWith('B23.')))
 }
 if (selectedStage.category === 'multi_domain_multi_hop') {
  questions.push(...supplementalQuestions.filter(q => q.category === MULTIHOP_CATEGORY))
 }
 return questions
})
const selectedBenchmark = computed(() => [...benchmarkQuestions.value, ...supplementalQuestions].find(q => q.id === benchmarkId.value))
const isMultihop = computed(() => result.value?.answer?.join_type === 'shacl_multihop_identifier_join')
const isPropertyTable = computed(() => projectedProperties.value.length > 1)
const projectedProperties = computed(() => Array.isArray(result.value?.answer?.properties) ? result.value.answer.properties as string[] : [])
const propertyLabel = (iri: string) => {
 const raw = iri.split(/[/#]/).pop()?.replace(/^has(?=[A-Z])/, '') || iri
 return raw.replace(/([a-z0-9])([A-Z])/g, '$1 $2').replace(/([A-Z])([A-Z][a-z])/g, '$1 $2')
}
const domainLabel = (domain: unknown): string => {
 if (typeof domain !== 'string' || !domain) return 'Unknown domain'
 const names: Record<string, string> = {dexpi:'DEXPI', ecad:'ECAD', assetinventory:'Asset Inventory', productcatalog:'Product Catalog', opcuaconnectivity:'OPC UA Connectivity'}
 return names[domain.toLowerCase()] || domain.replace(/([a-z0-9])([A-Z])/g, '$1 $2')
}
const joinRoute = computed(() => {
 const answer = result.value?.answer
 if (!answer || typeof answer.source_domain !== 'string' || typeof answer.target_domain !== 'string') return []
 return [answer.source_domain, answer.bridge_domain, answer.target_domain]
  .filter((domain): domain is string => typeof domain === 'string' && domain.length > 0)
})
const joinKeys = computed(() => {
 const plan = result.value?.plan
 if (!plan || typeof plan !== 'object') return []
 const record = plan as Record<string, unknown>
 const keys = record.join_keys
 return Array.isArray(keys) ? keys.filter((key): key is string => typeof key === 'string') :
  typeof record.join_key === 'string' ? [record.join_key] :
  typeof record.key_label === 'string' ? [record.key_label] : []
})
const resultCell = (row: ResultRow, property: string): unknown => {
 const properties = row.properties
 return properties && typeof properties === 'object' && !Array.isArray(properties)
  ? (properties as Record<string, unknown>)[property] : undefined
}
const missingCell = (value: unknown) => value === null || value === undefined || value === ''
const missingCount = computed(() => isMultihop.value
 ? rows.value.reduce((count, row) => count + projectedProperties.value.filter(p => missingCell(resultCell(row, p))).length, 0)
 : 0)
function selectCategory(next:string) {
 category.value = next
 benchmarkId.value = ''
}
function selectBenchmark(id:string) {
 benchmarkId.value = id
 const item = [...benchmarkQuestions.value, ...supplementalQuestions].find(q => q.id === id)
 if (item) question.value = displayedQuestion(item)
 result.value = null
 error.value = ''
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
type ShaclScenario = {
 scenario_id: string
 type: string
 expected_semantics: {
  domains: string[]; projections: string[]
  filters: Array<{property:string;operator:string;value:string}>
  boolean_operator: string; order_by: {property:string;direction:string}|null
  limit: number|null; join: boolean
 }
 paraphrases: Array<{id:string;query:string}>
}
type ShaclExecution = {
 id:string; scenario_id:string; question:string; status:string; sparql:string|null
 row_count:number|null; columns:string[]; rows:Array<Record<string,string>>
 mapping_ids:string[]; error:unknown; plan:unknown
}
const shaclExecution = ref<ShaclExecution|null>(null)
const shaclBusy = ref(false)
const shaclExecutionError = ref('')
function navigatorClipboardFallback(value:string) {
 if (typeof navigator !== 'undefined' && navigator.clipboard) void navigator.clipboard.writeText(value)
}
async function executeShacl() {
 if (!shaclVariantId.value || shaclBusy.value) return
 shaclBusy.value = true
 shaclExecution.value = null
 shaclExecutionError.value = ''
 try {
  const response = await fetch('/api/ai/shacl/benchmark/execute', {
   method:'POST', headers:{'Content-Type':'application/json'},
   body:JSON.stringify({id:shaclVariantId.value})
  })
  const data = await response.json()
  if (!response.ok) throw new Error(data.error || 'SHACL execution unavailable')
  shaclExecution.value = data as ShaclExecution
 } catch(e) { shaclExecutionError.value = e instanceof Error ? e.message : String(e) }
 finally { shaclBusy.value = false }
}
const shaclScenarios = ref<ShaclScenario[]>([])
const shaclError = ref('')
const shaclScope = ref<'single'|'cross'>('single')
const shaclScenarioId = ref('')
const shaclVariantId = ref('')
const shaclSelectedScenario = computed(() => shaclScenarios.value.find(s => s.scenario_id === shaclScenarioId.value))
const shaclVisibleScenarios = computed(() => shaclScenarios.value.filter(s => s.scenario_id.startsWith(shaclScope.value === 'single' ? 'SD' : 'CD')))
const shaclIntent = (s: ShaclScenario): string => {
 const x = s.expected_semantics
 const entity = x.projections.join(', ')
 if (x.order_by) return `Ordering / limit — ${x.order_by.property} ${x.order_by.direction}, top ${x.limit}`
 if (x.boolean_operator === 'AND') return `Boolean AND — ${x.filters.map(f => f.property).join(' + ')}`
 if (x.boolean_operator === 'OR') return `Boolean OR — ${x.filters.map(f => f.property).join(' / ')}`
 if (x.join) return x.filters.length ? 'Cross-domain identifier join with filtering' : 'Cross-domain identifier join'
 if (x.filters.length) return `Attribute filtering — ${x.filters.map(f => f.property).join(', ')}`
 return s.type === 'entity' ? `Entity retrieval — ${entity}` : `Property projection — ${entity}`
}
function chooseShaclScope(scope: 'single'|'cross') {
 shaclScope.value = scope
 shaclExecution.value = null
 shaclScenarioId.value = ''
 shaclVariantId.value = ''
 result.value = null
}
function chooseShaclScenario(id: string) {
 shaclScenarioId.value = id
 shaclExecution.value = null
 shaclVariantId.value = ''
 result.value = null
}
function chooseShaclVariant(id: string) {
 shaclVariantId.value = id
 shaclExecution.value = null
 const item = shaclSelectedScenario.value?.paraphrases.find(p => p.id === id)
 if (item) question.value = item.query
 result.value = null
 error.value = ''
}
onMounted(async () => {
 try {
  const response = await fetch('/api/ai/shacl/benchmark/questions', {cache:'no-store'})
  const data = await response.json()
  if (!response.ok) throw new Error(data.error || 'SHACL benchmark catalog unavailable')
  if (!Array.isArray(data.scenarios) || data.scenarios.length !== 25 ||
      data.scenarios.reduce((n:number,s:ShaclScenario) => n + s.paraphrases.length, 0) !== 125)
   throw new Error('Unexpected SHACL benchmark manifest size; expected 25 scenarios and 125 questions')
  shaclScenarios.value = data.scenarios
 } catch(e) { shaclError.value = e instanceof Error ? e.message : String(e) }
})

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
 const text = question.value.trim()
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
function hGeneratedQuestion(): string {
 if (!hFunction.value) return ''
 const element = hDomain.value === 'DEXPI' ? 'DEXPI InstrumentationFunction' : 'ECAD Device'
 const run = hRun.value ? ` for simulation run ${hRun.value}` : ''
 const interval = hStart.value !== '' && hEnd.value !== ''
  ? ` between simulation seconds ${hStart.value} and ${hEnd.value}`
  : hStart.value !== '' ? ` from simulation second ${hStart.value} onward`
  : hEnd.value !== '' ? ` up to simulation second ${hEnd.value}`
  : ' for all simulation times'
 return `Get historian values for the ${element} with LocalID ${hFunction.value}${run},${interval}.`
}
let hLastGeneratedQuestion = ''
function hSelectFunction() {
 hQuestion.value = hGeneratedQuestion()
 hLastGeneratedQuestion = hQuestion.value
 hResult.value = null
}
watch([hRun, hStart, hEnd], () => {
 if (hQuestion.value === hLastGeneratedQuestion && hFunction.value) {
  hQuestion.value = hGeneratedQuestion()
  hLastGeneratedQuestion = hQuestion.value
 }
})
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
  <section v-if="page === 'engineering'" class="panel">
   <div class="panel-title">
    <div><h2>TEP NEXUS — DTwise Engineering Query</h2><p>Phase 1 SHACL planner · SPARQL compiler · read-only GraphDB execution</p></div>
   </div>
   <div class="custom-query">
    <div class="shacl-catalog" aria-label="Phase 1 SHACL benchmark catalog">
     <h3>Phase 1 · SHACL benchmark queries</h3>
     <p class="subdued">14 single-domain scenarios (70 questions) · 11 cross-domain scenarios (55 questions). Intents are derived from the existing expected semantics; no new benchmark metadata is required.</p>
     <div class="mode-switch" role="group" aria-label="SHACL domain scope">
      <button type="button" :class="shaclScope === 'single' ? 'primary' : 'secondary'" @click="chooseShaclScope('single')">Single-domain (70)</button>
      <button type="button" :class="shaclScope === 'cross' ? 'primary' : 'secondary'" @click="chooseShaclScope('cross')">Cross-domain (55)</button>
     </div>
     <label for="shacl-scenario">Scenario · query intent</label>
     <select id="shacl-scenario" :value="shaclScenarioId" @change="chooseShaclScenario(($event.target as HTMLSelectElement).value)">
      <option value="">Select a scenario</option>
      <option v-for="scenario in shaclVisibleScenarios" :key="scenario.scenario_id" :value="scenario.scenario_id">{{scenario.scenario_id}} · {{shaclIntent(scenario)}}</option>
     </select>
     <label for="shacl-variant">Benchmark paraphrase</label>
     <select id="shacl-variant" :value="shaclVariantId" :disabled="!shaclSelectedScenario" @change="chooseShaclVariant(($event.target as HTMLSelectElement).value)">
      <option value="">Select one of five questions</option>
      <option v-for="variant in shaclSelectedScenario?.paraphrases || []" :key="variant.id" :value="variant.id">{{variant.id}} · {{variant.query}}</option>
     </select>
     <p v-if="shaclSelectedScenario" class="subdued">Domains: {{shaclSelectedScenario.expected_semantics.domains.join(' + ')}} · Projections: {{shaclSelectedScenario.expected_semantics.projections.join(', ')}} · Filters: {{shaclSelectedScenario.expected_semantics.filters.length}}</p>
     <p v-if="shaclError" role="alert">{{shaclError}}</p>
     <button class="primary shacl-run-button" type="button" :disabled="!shaclVariantId || shaclBusy" @click="executeShacl">{{shaclBusy ? '✨ Thinking…' : '✨ Ask DTwise'}}</button>
     <p class="subdued">Runs the selected manifest question through the Phase 1 SHACL planner, SPARQL compiler and GraphDB. </p>
     <p v-if="shaclExecutionError" role="alert">{{shaclExecutionError}}</p>
     <section v-if="shaclExecution" class="shacl-output" aria-label="SHACL benchmark results">
      <h3>SHACL execution · {{shaclExecution.id}}</h3>
      <p>Status: <strong>{{shaclExecution.status}}</strong> · Rows: {{shaclExecution.row_count === null ? 'Not executed' : shaclExecution.row_count}}</p>
      <p v-if="shaclExecution.error" role="alert">{{JSON.stringify(shaclExecution.error)}}</p>
      <p v-if="shaclExecution.mapping_ids.length" class="subdued">Mapping IDs: {{shaclExecution.mapping_ids.join(', ')}}</p>
      <h3>GraphDB results table</h3>
      <div v-if="shaclExecution.rows.length" class="table-scroll">
       <table class="evidence-table"><thead><tr><th>#</th><th v-for="col in shaclExecution.columns" :key="col">{{col}}</th></tr></thead>
        <tbody><tr v-for="(entry,i) in shaclExecution.rows" :key="i"><td>{{i+1}}</td><td v-for="col in shaclExecution.columns" :key="col" class="mono">{{entry[col] ?? '—'}}</td></tr></tbody>
       </table>
      </div>
      <p v-else-if="shaclExecution.status === 'executed_zero_rows'" class="subdued">Query executed successfully; GraphDB returned zero rows.</p>
      <p v-else class="subdued">No result rows available.</p>
      <h3>Generated SPARQL</h3>
      <div v-if="shaclExecution.sparql">
       <button type="button" @click="navigatorClipboardFallback(shaclExecution.sparql!)">Copy SPARQL</button>
       <pre class="shacl-sparql">{{shaclExecution.sparql}}</pre>
      </div>
      <p v-else class="subdued">No SPARQL generated.</p>
      <details><summary>Phase 1 plan</summary><pre class="shacl-sparql">{{JSON.stringify(shaclExecution.plan,null,2)}}</pre></details>
     </section>
    </div>
    <!-- Legacy B01–B53 catalog temporarily hidden; restore by removing these comment markers.
    <details class="legacy-benchmark"><summary>Legacy B01–B53 benchmark catalog</summary>
    <label for="benchmark-category">Benchmark category (B01–B53)</label>
    <select id="benchmark-category" :value="category" @change="selectCategory(($event.target as HTMLSelectElement).value)">
     <option value="">Select a stage</option>
     <option v-for="item in categories" :key="item" :value="item">{{item}}</option>
    </select>
    <label for="benchmark-question">Benchmark question</label>
    <select id="benchmark-question" :value="benchmarkId" :disabled="!category" @change="selectBenchmark(($event.target as HTMLSelectElement).value)">
     <option value="">Select a question</option>
     <option v-for="item in categoryQuestions" :key="item.id" :value="item.id">{{item.id + ' — ' + displayedQuestion(item)}}</option>
    </select>
    <p v-if="manifestError" role="status" style="color:#b45309">{{manifestError}}. Manual questions remain available.</p>
    <p class="subdued">B01–B53 are grouped by manifest category; supplemental questions are labeled separately.</p>
    <p v-if="category === benchmarkStages.find(stage => stage.category === 'multi_domain_multi_hop')?.label" class="subdued">DEXPI → AssetInventory → ProductCatalog · SHACL-validated AssetIdentifier and ProductIdentifier joins. Select a query or edit it below.</p>
    </details>
    -->
    <p v-if="shaclVariantId" class="subdued">Selected question: {{question}}</p>
    <!-- Legacy Unified IR question editor and Ask DTwise execution temporarily hidden.
    <label for="dtwise-question">Engineering question (editable)</label>
    <textarea id="dtwise-question" v-model="question" maxlength="1000" rows="4"
      placeholder="List OPCUAconnectivity SignalNames." @keydown.ctrl.enter="ask" />
    <p class="subdued">Results come from the LLM-driven Unified IR pipeline. Invalid plans are rejected; no automatic fallback.</p>
   <button class="primary" type="button" :disabled="busy || question.trim().length < 5" @click="ask">
    {{busy ? 'Executing query…' : 'Ask DTwise'}}
   </button>
   <p v-if="error" role="alert" style="color:#b45309">{{error}}</p>
    -->
   </div>
  </section>
  <section v-if="page === 'historian'" class="panel">
   <div class="panel-title"><div><h2>Semantic Historian Query</h2><p>DEXPI / ECAD → OPCUAConnectivity · GraphDB semantic join + TimescaleDB historian · read-only</p></div></div>
   <form class="custom-query" @submit.prevent="hAsk">
    <label for="h-run">Simulation run (required for historian queries)</label>
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
    <button class="primary" type="submit"  :disabled="hBusy || !hFunction || !hRun">{{hBusy ? 'Executing…' : 'Query historian'}}</button>
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
  <!-- Legacy Unified IR result panel temporarily hidden.
  <section v-if="page === 'engineering' && result" class="panel result-panel">
   <div class="panel-title">
    <div><h2>Engineering result</h2><p>{{result.question}}</p></div>
    <span class="pill">{{result.executed ? 'Executed' : 'Not executed'}}</span>
   </div>
   <div class="result-section">
    <h3>Structured answer</h3>
    <p class="subdued">GraphDB result via SHACL-validated Unified IR · result values not independently verified</p>
    <p v-if="result.answer.truncated_possible" role="status">Results may be truncated by the query limit.</p>
    <p v-if="result.answer.count !== undefined">Reported count: {{result.answer.count}}</p>
    <div v-if="joinRoute.length > 1" class="join-provenance" aria-label="SHACL join provenance">
     <strong>SHACL-validated domain join</strong>
     <div class="join-steps"><template v-for="(domain,i) in joinRoute" :key="i"><span class="join-domain">{{domainLabel(domain)}}</span><span v-if="i < joinRoute.length - 1" class="join-arrow" aria-hidden="true">→</span></template></div>
     <p v-if="joinKeys.length" class="subdued">Join identifiers: {{joinKeys.join(' · ')}}</p>
     <p class="subdued">Structural paths verified against SHACL; returned values come from GraphDB.</p>
    </div>
    <p v-if="isMultihop && missingCount" class="subdued">{{missingCount}} unavailable property value{{missingCount === 1 ? '' : 's'}} shown as Not available (optional data).</p>
    <div v-if="(isMultihop || isPropertyTable) && rows.length" class="table-scroll">
     <table class="evidence-table">
      <thead><tr><th>#</th><th v-for="property in projectedProperties" :key="property" :title="property">{{propertyLabel(property)}}</th></tr></thead>
      <tbody><tr v-for="(row,i) in rows" :key="i"><td>{{i+1}}</td><td v-for="property in projectedProperties" :key="property" class="mono" :class="{'missing-value':missingCell(resultCell(row,property))}"><span v-if="missingCell(resultCell(row,property))" title="This optional property was not returned by GraphDB">Not available</span><span v-else :title="display(resultCell(row,property))">{{display(resultCell(row,property))}}</span></td></tr></tbody>
     </table>
    </div>
    <div v-else-if="rows.length" class="table-scroll">
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
    <details class="detail-toggle"><summary>Unified IR plan</summary><pre>{{JSON.stringify(result.plan,null,2)}}</pre></details>
   </div>
  </section>
  -->
 </div>
</template>

<style scoped>
.join-provenance{display:grid;gap:8px;padding:12px;border:1px solid #334a62;border-radius:8px}.join-provenance p{margin:0}.join-steps{display:flex;align-items:center;flex-wrap:wrap;gap:8px}.join-domain{padding:5px 9px;border:1px solid #476078;border-radius:6px;font-weight:600}.join-arrow{opacity:.75}.missing-value{font-style:italic;opacity:.7}

.vtkg-source-trace{display:grid;gap:10px;padding:12px;border:1px solid #334a62;border-radius:8px}.vtkg-source-trace h3{margin:0}.vtkg-trace-steps{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:10px}.vtkg-trace-steps>div{display:grid;align-content:start;gap:6px;padding:10px;border:1px solid #334a62;border-radius:7px}.vtkg-trace-steps span{font-weight:600;overflow-wrap:anywhere}.vtkg-trace-steps small{opacity:.8;overflow-wrap:anywhere}

.vtkg-chart{display:grid;gap:8px}.vtkg-chart h3{margin:0}.vtkg-chart-scroll{overflow-x:auto}.vtkg-chart svg{display:block;width:100%;min-width:520px;height:auto;max-height:370px}

.mode-switch{display:flex;gap:8px;flex-wrap:wrap;margin:12px 0}.custom-query{display:grid;gap:10px;margin:12px 0}.custom-query textarea{width:100%;box-sizing:border-box;padding:12px;border:1px solid #334a62;border-radius:8px;background:#0c192a;color:#eaf4ff;font:inherit;resize:vertical}.example-list{display:grid;gap:8px}.example-list strong{font-size:12px}.example-button{text-align:left;white-space:normal;padding:9px 12px}
.result-panel{display:grid;gap:16px}.result-panel pre{white-space:pre-wrap;overflow-wrap:anywhere;max-height:480px;overflow:auto}.result-section{border-top:1px solid #334a62;padding-top:15px;display:grid;gap:9px}.result-section h3{font-size:14px;margin:0}.answer-text{white-space:pre-wrap;overflow-wrap:anywhere;line-height:1.65}.section-heading{display:flex;align-items:center;justify-content:space-between;gap:12px}.table-scroll{overflow-x:auto}.evidence-table{width:100%;border-collapse:collapse;font-size:12px;text-align:left}.evidence-table th,.evidence-table td{padding:10px;border-bottom:1px solid #334a62;vertical-align:top}.evidence-table th{color:#a9bfd0;font-weight:600}.full-id{display:block;overflow-wrap:anywhere;font-size:10px;opacity:.75;margin-top:3px}.mono{font-family:ui-monospace,SFMono-Regular,Consolas,monospace;overflow-wrap:anywhere}.event-summary{display:grid;gap:7px;padding:12px;border:1px solid #334a62;border-radius:8px}.event-summary small{color:#a9bfd0}.source-row{font-size:12px;margin:0}.detail-toggle{font-size:12px;overflow:hidden}.detail-toggle summary{cursor:pointer}.detail-toggle pre{white-space:pre-wrap;overflow-wrap:anywhere;max-height:420px;overflow:auto;font-size:11px}.spec-block{padding:12px 0}.result-notice{padding:12px;border:1px solid #b45309;border-radius:8px}.result-section ul{margin:0;padding-left:22px}.result-section li{margin:6px 0}
select{padding:10px;border:1px solid #657b92;border-radius:7px;background:#101820;color:#fff;max-width:100%;width:100%;color-scheme:dark}
select option,select optgroup{background:#101820;color:#fff}
select:focus-visible{outline:2px solid #79b8ff;outline-offset:2px}
select:disabled{opacity:.6;cursor:not-allowed}
.shacl-catalog{display:grid;gap:10px;padding:15px;border:1px solid #334a62;border-radius:9px}.shacl-catalog h3{margin:0;font-size:15px}.legacy-benchmark{display:grid;gap:10px}.legacy-benchmark[open]{padding:12px;border:1px solid #334a62;border-radius:8px}.legacy-benchmark summary{cursor:pointer;margin-bottom:10px}
.shacl-run-button{width:fit-content;max-width:100%;justify-self:start;padding-inline:16px}\n.shacl-output{display:grid;gap:10px;border-top:1px solid #334a62;padding-top:12px}.shacl-sparql{white-space:pre-wrap;overflow-wrap:anywhere;max-height:460px;overflow:auto;font-size:12px}
</style>
