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
const benchmarks = ref<Benchmark[]>([])
const mode = ref<'Without Run ID' | 'With Run ID'>('Without Run ID')
const selected = ref('')
const loading = ref(false)
const error = ref('')
const active = computed(() => benchmarks.value.filter(b => b.mode === mode.value))
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
