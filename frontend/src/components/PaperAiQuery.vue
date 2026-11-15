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
const vtkgQuestion = ref('')
const vtkgFunction = ref('')
const vtkgRunId = ref('')
const vtkgStart = ref<number | null>(null)
const vtkgEnd = ref<number | null>(null)
const vtkgLimit = ref(100)
const vtkgBusy = ref(false)
const vtkgError = ref('')
type VtkgReport = {answer:string; evidence:{observations: Array<Record<string,unknown>>; observationCount:number; truncated:boolean; provenance:Record<string,unknown>}; validatedPlan:unknown; materializedInGraphDB:boolean}
const vtkgResult = ref<VtkgReport | null>(null)
async function askVtkg() {
 vtkgResult.value = null
 vtkgError.value = ''
 if (vtkgStart.value === null || vtkgEnd.value === null) {
  vtkgError.value = 'Explicit simulation-time bounds are required'
  return
 }
 vtkgBusy.value = true
 try {
  const response = await fetch('/api/ai/vtkg/answer', {
   method:'POST', headers:{'Content-Type':'application/json'},
   body:JSON.stringify({
    question:vtkgQuestion.value, engineering_function:vtkgFunction.value,
    run_id:vtkgRunId.value, start_simulation_seconds:vtkgStart.value,
    end_simulation_seconds:vtkgEnd.value, limit:vtkgLimit.value
   })
  })
  const data = await response.json()
  if (!response.ok) throw new Error(data.error || 'VTKG query failed')
  vtkgResult.value = data as VtkgReport
 } catch(e) { vtkgError.value = e instanceof Error ? e.message : String(e) }
 finally { vtkgBusy.value = false }
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
    <label for="dtwise-question">Engineering question (editable)</label>
    <textarea id="dtwise-question" v-model="question" maxlength="1000" rows="4"
      placeholder="List OPCUAconnectivity SignalNames." @keydown.ctrl.enter="ask" />
    <p class="subdued">Results come from the frozen DTwise pipeline. No alternative planner or automatic fallback.</p>
   </div>
   <button class="primary" type="button" :disabled="busy || question.trim().length < 5" @click="ask">
    {{busy ? 'Executing DTwise query…' : 'Ask DTwise'}}
   </button>
   <p v-if="error" role="alert" style="color:#b45309">{{error}}</p>
  </section>
  <section class="panel">
   <div class="panel-title"><div><h2>VTKG — Simulation observations</h2><p>Existing constrained virtual temporal graph · TimescaleDB historian · no RDF materialization</p></div></div>
   <form class="custom-query" @submit.prevent="askVtkg">
    <label for="vtkg-function">Engineering function (supported registry ID)</label>
    <input id="vtkg-function" v-model="vtkgFunction" required placeholder="TI_101" />
    <label for="vtkg-run">Simulation run UUID</label>
    <input id="vtkg-run" v-model="vtkgRunId" required placeholder="Run UUID" />
    <label for="vtkg-start">Start simulation seconds</label>
    <input id="vtkg-start" v-model.number="vtkgStart" type="number" min="0" step="any" required />
    <label for="vtkg-end">End simulation seconds</label>
    <input id="vtkg-end" v-model.number="vtkgEnd" type="number" min="0" step="any" required />
    <label for="vtkg-limit">Observation limit</label>
    <input id="vtkg-limit" v-model.number="vtkgLimit" type="number" min="1" max="5000" step="1" required />
    <label for="vtkg-question">Question (must name the function and the same explicit time interval)</label>
    <textarea id="vtkg-question" v-model="vtkgQuestion" required maxlength="1000" rows="3"
     placeholder="Show observations for TI_101 between 0 seconds and 60 seconds." />
    <p class="subdued">The existing VTKG contract rejects mismatched functions or time bounds. No automatic query routing or inferred joins.</p>
    <button class="primary" type="submit" :disabled="vtkgBusy">{{vtkgBusy ? 'Querying VTKG…' : 'Query VTKG'}}</button>
    <p v-if="vtkgError" role="alert" style="color:#b45309">{{vtkgError}}</p>
   </form>
   <div v-if="vtkgResult" class="result-section">
    <h3>Virtual temporal graph result</h3>
    <p>{{vtkgResult.answer}}</p>
    <p>Observations: {{vtkgResult.evidence.observationCount}} · Truncated: {{vtkgResult.evidence.truncated ? 'Yes' : 'No'}} · Materialized in GraphDB: {{vtkgResult.materializedInGraphDB ? 'Yes' : 'No'}}</p>
    <div class="table-scroll"><table class="evidence-table">
     <thead><tr><th>#</th><th>Simulation time (hours)</th><th>Value</th><th>Observed at</th></tr></thead>
     <tbody><tr v-for="(observation,i) in vtkgResult.evidence.observations" :key="i">
      <td>{{i+1}}</td><td>{{display(observation.simulationTimeHours)}}</td><td>{{display(observation.value)}}</td><td>{{display(observation.observedAt)}}</td>
     </tr></tbody>
    </table></div>
    <details class="detail-toggle"><summary>VTKG provenance and validated plan</summary><pre>{{JSON.stringify({provenance:vtkgResult.evidence.provenance,validatedPlan:vtkgResult.validatedPlan},null,2)}}</pre></details>
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
.mode-switch{display:flex;gap:8px;flex-wrap:wrap;margin:12px 0}.custom-query{display:grid;gap:10px;margin:12px 0}.custom-query textarea{width:100%;box-sizing:border-box;padding:12px;border:1px solid #334a62;border-radius:8px;background:#0c192a;color:#eaf4ff;font:inherit;resize:vertical}.example-list{display:grid;gap:8px}.example-list strong{font-size:12px}.example-button{text-align:left;white-space:normal;padding:9px 12px}
.result-panel{display:grid;gap:16px}.result-panel pre{white-space:pre-wrap;overflow-wrap:anywhere;max-height:480px;overflow:auto}.result-section{border-top:1px solid #334a62;padding-top:15px;display:grid;gap:9px}.result-section h3{font-size:14px;margin:0}.answer-text{white-space:pre-wrap;overflow-wrap:anywhere;line-height:1.65}.section-heading{display:flex;align-items:center;justify-content:space-between;gap:12px}.table-scroll{overflow-x:auto}.evidence-table{width:100%;border-collapse:collapse;font-size:12px;text-align:left}.evidence-table th,.evidence-table td{padding:10px;border-bottom:1px solid #334a62;vertical-align:top}.evidence-table th{color:#a9bfd0;font-weight:600}.full-id{display:block;overflow-wrap:anywhere;font-size:10px;opacity:.75;margin-top:3px}.mono{font-family:ui-monospace,SFMono-Regular,Consolas,monospace;overflow-wrap:anywhere}.event-summary{display:grid;gap:7px;padding:12px;border:1px solid #334a62;border-radius:8px}.event-summary small{color:#a9bfd0}.source-row{font-size:12px;margin:0}.detail-toggle{font-size:12px;overflow:hidden}.detail-toggle summary{cursor:pointer}.detail-toggle pre{white-space:pre-wrap;overflow-wrap:anywhere;max-height:420px;overflow:auto;font-size:11px}.spec-block{padding:12px 0}.result-notice{padding:12px;border:1px solid #b45309;border-radius:8px}.result-section ul{margin:0;padding-left:22px}.result-section li{margin:6px 0}
select{padding:10px;border:1px solid #657b92;border-radius:7px;background:#101820;color:#fff;max-width:100%;width:100%;color-scheme:dark}
select option,select optgroup{background:#101820;color:#fff}
select:focus-visible{outline:2px solid #79b8ff;outline-offset:2px}
select:disabled{opacity:.6;cursor:not-allowed}
</style>
