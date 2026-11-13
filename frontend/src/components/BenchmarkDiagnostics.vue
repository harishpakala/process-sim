<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'

type Case = { id: string; question: string; kind: string; expectedPathId: string | null; source: string; domain: string | null }
type Result = {
 caseId: string; question: string; expectedPathId: string | null; selectedPathId: string
 correctPathSelection: boolean | null; candidatePaths: unknown[]; llmRaw: string
 validation: string; query?: string; pathEvidence?: unknown; execution: string
 executionError?: string; returnedRows?: number; sampleBindings?: unknown[]
 answer: string; answerStatus: string; elapsedSeconds: number; model: string
}
const experiment = ref<37 | 42>(42)
const cases = ref<Case[]>([])
const indexSha = ref('')
const selectedId = ref('')
const loading = ref(false)
const busy = ref(false)
const execute = ref(false)
const error = ref('')
const result = ref<Result | null>(null)
const selected = computed(() => cases.value.find(q => q.id === selectedId.value))
const positiveCount = computed(() => cases.value.filter(q => q.kind === 'positive').length)
async function getJson(url: string, options?: RequestInit) {
 const response = await fetch(url, options)
 const data = await response.json()
 if (!response.ok) throw new Error(data.error || 'Request failed')
 return data
}
async function load() {
 loading.value = true
 error.value = ''
 result.value = null
 try {
  const data = await getJson('/api/ai/benchmarks/'+experiment.value+'/questions', {cache:'no-store'})
  if (!Array.isArray(data.questions) || !data.indexSha256) throw new Error('Invalid frozen benchmark registry')
  cases.value = data.questions
  indexSha.value = data.indexSha256
  if (!cases.value.some(q => q.id === selectedId.value)) selectedId.value = cases.value[0]?.id || ''
 } catch (e) { error.value = e instanceof Error ? e.message : String(e) }
 finally { loading.value = false }
}
async function run() {
 if (!selected.value || busy.value) return
 busy.value = true
 result.value = null
 error.value = ''
 try {
  result.value = await getJson('/api/ai/benchmarks/'+experiment.value+'/run', {
   method: 'POST', headers: {'Content-Type':'application/json'},
   body: JSON.stringify({caseId:selected.value.id,indexSha256:indexSha.value,execute:execute.value})
  })
 } catch (e) { error.value = e instanceof Error ? e.message : String(e) }
 finally { busy.value = false }
}
onMounted(() => { void load() })
</script>

<template>
 <div style="display:grid;gap:16px">
  <section class="panel">
   <div class="panel-title"><div><h2>Frozen Benchmark — Experiment {{experiment}}</h2><p>Select a fixed question and run ontology-grounded hybrid retrieval and the constrained Llama path planner.</p></div><span class="pill">DEVELOPMENT BENCHMARK</span></div>
   <p class="subdued">Experiment 42 contains eight authored engineering probes without gold-answer verification; Experiment 37 is the catalog-derived path-selection baseline. Neither uses Run ID, temporal data or aggregation. The current 36D planner supports path selection only, so some pilot questions are intentionally beyond its capabilities.</p>
   <label>Frozen dataset <select v-model.number="experiment" :disabled="busy" @change="load"><option :value="42">Experiment 42 — Eight engineering questions</option><option :value="37">Experiment 37 — Catalog path baseline</option></select></label>
   <div class="control-row">
    <strong>{{cases.length}} questions · {{experiment===37 ? positiveCount+' supported path cases · '+(cases.length-positiveCount)+' abstention cases' : '8 authored engineering probes; gold answers pending'}}</strong>
    <button type="button" class="secondary" :disabled="loading||busy" @click="load">{{loading?'Loading…':'Refresh frozen questions'}}</button>
   </div>
   <label style="display:grid;gap:7px">Benchmark question
    <select v-model="selectedId" :disabled="busy" @change="result=null">
     <option v-for="q in cases" :key="q.id" :value="q.id">{{q.id}} — {{q.question}}</option>
    </select>
   </label>
   <template v-if="selected">
    <div class="result-section">
     <h3>{{selected.id}} — Question</h3>
     <p>{{selected.question}}</p>
     <p class="subdued">Expected path: <code>{{selected.expectedPathId || 'Not yet independently annotated'}}</code> · {{selected.kind}} · {{selected.source}}</p>
    </div>
    <label class="control-row"><input v-model="execute" type="checkbox" :disabled="busy" /> Execute validated SELECT against GraphDB (optional; read-only)</label>
    <button class="primary" type="button" :disabled="busy||loading" @click="run">{{busy?'Retrieving ontology, querying Ollama…':'Run selected benchmark question'}}</button>
   </template>
   <p v-if="error" role="alert" style="color:#b45309">{{error}}</p>
  </section>
  <section v-if="result" class="panel">
   <div class="panel-title"><div><h2>{{result.caseId}} — Query result</h2><p>{{result.question}}</p></div><span class="pill">{{result.correctPathSelection===null?'NOT SCORED':result.correctPathSelection?'PATH MATCH':'PATH MISMATCH'}}</span></div>
   <div class="result-section"><h3>Answer / outcome</h3><p>{{result.answer}}</p><p class="subdued">Answer verification: {{result.answerStatus}}. Experiment 42 has no gold answer annotations, so no pass/fail is claimed. Experiment 37 path match compares against its catalog-derived annotation only.</p></div>
   <div class="result-section"><h3>Benchmark evaluation</h3>
    <p>Expected: <code>{{result.expectedPathId || 'Not annotated'}}</code></p>
    <p>Selected: <code>{{result.selectedPathId}}</code></p>
    <p>Deterministic validation: {{result.validation}}</p>
    <p>GraphDB execution: {{result.execution}} <span v-if="result.returnedRows!==undefined">· {{result.returnedRows}} rows</span></p>
    <p v-if="result.executionError" role="alert">{{result.executionError}}</p>
    <p class="subdued">Model: {{result.model}} · {{result.elapsedSeconds}} s</p>
   </div>
   <div v-if="result.query" class="result-section"><h3>Compiled SPARQL query</h3><pre style="white-space:pre-wrap;overflow-wrap:anywhere">{{result.query}}</pre></div>
   <div v-if="result.sampleBindings" class="result-section"><h3>GraphDB bindings (up to 10)</h3><pre style="white-space:pre-wrap;overflow-wrap:anywhere">{{JSON.stringify(result.sampleBindings,null,2)}}</pre></div>
   <details class="result-section"><summary>Hybrid retrieval candidates</summary><pre style="white-space:pre-wrap;overflow-wrap:anywhere">{{JSON.stringify(result.candidatePaths,null,2)}}</pre></details>
   <details class="result-section"><summary>Raw Llama response and ontology path evidence</summary><pre style="white-space:pre-wrap;overflow-wrap:anywhere">{{result.llmRaw}}</pre><pre style="white-space:pre-wrap;overflow-wrap:anywhere">{{JSON.stringify(result.pathEvidence,null,2)}}</pre></details>
  </section>
 </div>
</template>
