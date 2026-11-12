<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'

type Benchmark = {
 id: string
 mode: 'With Run ID' | 'Without Run ID'
 description: string
 reportPath: string
 available: boolean
 report?: Record<string, unknown>
 error?: string
}
type Question = {id:string; question:string; mode:string; expected?:string; note?:string}
type QuestionGroup = {id:string; title:string; provenance?:string; note?:string; questions:Question[]}
const groups = ref<QuestionGroup[]>([])
const benchmarks = ref<Benchmark[]>([])
const mode = ref<'Without Run ID' | 'With Run ID'>('Without Run ID')
const selected = ref('')
const loading = ref(false)
const error = ref('')
const active = computed(() => benchmarks.value.filter(b => b.mode === mode.value))
const visibleGroups = computed(() => groups.value.map(g => ({...g, questions:g.questions.filter(q => q.mode === mode.value)})).filter(g => g.questions.length || g.id==='37'))
const current = computed(() => active.value.find(b => b.id === selected.value))
async function refresh() {
 loading.value = true
 error.value = ''
 try {
  const response = await fetch('/api/ai/benchmarks/reports', {cache:'no-store'})
  const data = await response.json()
  if (!response.ok) throw new Error(data.error || 'Benchmark reports unavailable')
  if (!Array.isArray(data.benchmarks)) throw new Error('Invalid benchmark registry')
  benchmarks.value = data.benchmarks
  const questionResponse = await fetch('/api/ai/benchmarks/questions', {cache:'no-store'})
  const questionData = await questionResponse.json()
  if (!questionResponse.ok || !Array.isArray(questionData.groups)) throw new Error(questionData.error || 'Question inventory unavailable')
  groups.value = questionData.groups
  if (!active.value.some(b => b.id === selected.value)) selected.value = active.value[0]?.id || ''
 } catch (e) {
  error.value = e instanceof Error ? e.message : String(e)
 } finally {
  loading.value = false
 }
}
function changeMode(value: 'With Run ID' | 'Without Run ID') {
 mode.value = value
 selected.value = benchmarks.value.find(b => b.mode === value)?.id || ''
}
onMounted(() => { void refresh() })
</script>

<template>
 <div style="display:grid;gap:16px">
  <section class="panel">
   <div class="panel-title">
    <div><h2>TEP NEXUS — Benchmark diagnostics</h2><p>Inspect locally generated experiment reports. No benchmark is executed by this page.</p></div>
    <span class="pill">EXPERIMENTAL · READ ONLY</span>
   </div>
   <div class="mode-switch" role="group" aria-label="Benchmark execution context">
    <button type="button" :class="mode==='Without Run ID'?'primary':'secondary'" :aria-pressed="mode==='Without Run ID'" @click="changeMode('Without Run ID')">Without Run ID · GraphDB</button>
    <button type="button" :class="mode==='With Run ID'?'primary':'secondary'" :aria-pressed="mode==='With Run ID'" @click="changeMode('With Run ID')">With Run ID · VTKG</button>
   </div>
   <p class="subdued">These modes group experiments by intended data context; they do not imply every experiment executed the full pipeline. Generated reports are not proof of answer correctness.</p>
   <div class="control-row">
    <label style="display:grid;gap:6px;flex:1">Experiment
     <select v-model="selected"><option v-for="item in active" :key="item.id" :value="item.id">Experiment {{item.id}} — {{item.description}}</option></select>
    </label>
    <button class="secondary" type="button" :disabled="loading" @click="refresh">{{loading?'Refreshing…':'Refresh reports'}}</button>
   </div>
   <p v-if="error" role="alert">{{error}}</p>
  </section>
  <section class="panel">
   <div class="panel-title"><div><h2>Benchmark question inventory</h2><p>Source-backed questions; expected results are not measured outcomes.</p></div><span class="pill">{{visibleGroups.reduce((sum,g)=>sum+g.questions.length,0)}} questions</span></div>
   <div v-for="group in visibleGroups" :key="group.id" style="margin:16px 0">
    <h3>{{group.title}} · {{group.questions.length}} questions</h3>
    <p class="subdued">{{group.provenance}}</p>
    <p v-if="group.note" class="subdued">{{group.note}}</p>
    <details v-for="q in group.questions" :key="group.id+q.id" style="padding:9px 0;border-bottom:1px solid #294159">
     <summary><strong>{{q.id}}</strong> — {{q.question}}</summary>
     <p><strong>Expected:</strong> {{q.expected || "Not independently annotated"}}</p>
     <p class="subdued">{{q.note}}</p>
    </details>
   </div>
  </section>
  <section v-if="current" class="panel">
   <div class="panel-title"><div><h2>Experiment {{current.id}}</h2><p>{{current.description}}</p></div><span class="pill">{{current.available?'Local report found':'Not run / report missing'}}</span></div>
   <p class="subdued">Expected report: <code>{{current.reportPath}}</code></p>
   <p v-if="current.error" role="alert">{{current.error}}</p>
   <template v-if="current.available && current.report">
    <p class="subdued">Raw diagnostic report. Interpret metrics alongside the experiment's dataset provenance and limitations.</p>
    <details open><summary>Complete report and execution trace</summary><pre style="white-space:pre-wrap;overflow-wrap:anywhere;max-height:70vh;overflow:auto">{{JSON.stringify(current.report,null,2)}}</pre></details>
   </template>
   <p v-else class="subdued">Run this experiment locally using its existing CLI and refresh. This UI does not launch Ollama, GraphDB, or TimescaleDB jobs.</p>
  </section>
 </div>
</template>
