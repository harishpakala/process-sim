<script setup lang="ts">
import { computed, ref } from 'vue'

type DtwiseResult = {
 question: string; mode: string; sparql: string; executed: boolean;
 graph_mode: string; answer: Record<string, unknown>; plan: unknown
}
const question = ref('')
const busy = ref(false)
const error = ref('')
const result = ref<DtwiseResult | null>(null)
const entities = computed(() => Array.isArray(result.value?.answer?.entities) ? result.value.answer.entities : [])
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
    <label for="dtwise-question">Engineering question</label>
    <textarea id="dtwise-question" v-model="question" maxlength="1000" rows="4"
      placeholder="List OPCUA SignalNames." @keydown.ctrl.enter="ask" />
    <p class="subdued">Results come from the frozen DTwise pipeline. No alternative planner or automatic fallback.</p>
   </div>
   <button class="primary" type="button" :disabled="busy || question.trim().length < 5" @click="ask">
    {{busy ? 'Executing DTwise query…' : 'Ask DTwise'}}
   </button>
   <p v-if="error" role="alert" style="color:#b45309">{{error}}</p>
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
    <div v-if="entities.length" class="table-scroll">
     <table class="evidence-table">
      <thead><tr><th>#</th><th>Returned entity / value</th></tr></thead>
      <tbody><tr v-for="(entity,i) in entities" :key="i">
       <td>{{i+1}}</td><td><pre>{{JSON.stringify(entity,null,2)}}</pre></td>
      </tr></tbody>
     </table>
    </div>
    <details class="detail-toggle"><summary>Full structured answer</summary><pre>{{JSON.stringify(result.answer,null,2)}}</pre></details>
   </div>
   <div class="result-section"><h3>Generated SPARQL</h3><pre>{{result.sparql}}</pre></div>
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
