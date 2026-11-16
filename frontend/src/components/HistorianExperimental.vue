<script setup lang="ts">
import { ref } from 'vue'

type HistorianResponse = {
 mode: string
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
const busy = ref(false)
const error = ref('')
const response = ref<HistorianResponse | null>(null)

async function run() {
 error.value = ''
 response.value = null
 if (question.value.trim().length < 5) {
  error.value = 'Enter a historian question.'
  return
 }
 busy.value = true
 try {
  const r = await fetch('/api/ai/vtkg/historian/experimental/answer', {
   method: 'POST',
   headers: {'Content-Type':'application/json'},
   body: JSON.stringify({question: question.value.trim()})
  })
  const body = await r.json()
  if (!r.ok) throw new Error(body.error || 'Experimental historian query failed')
  response.value = body as HistorianResponse
 } catch (e) {
  error.value = e instanceof Error ? e.message : String(e)
 } finally {
  busy.value = false
 }
}
</script>

<template>
 <section class="panel">
  <div class="panel-title"><h2>Historian Experimental — Natural Language</h2><span class="pill">ISOLATED EXPERIMENT</span></div>
  <p>Ask a free-text historian question. The experiment validates SHACL schema evidence and reuses the existing VTKG Historian executor. Existing Historian Queries remain unchanged.</p>
  <p>For this first prototype, include DEXPI or ECAD, exactly one LocalID, and the full simulation run UUID. Time bounds are optional.</p>
  <label for="historian-experiment-question">Historian question</label>
  <textarea id="historian-experiment-question" v-model="question" rows="4" style="width:100%;margin-top:8px" placeholder="Get historian values for the DEXPI InstrumentationFunction with LocalID FI_101 for simulation run 00000000-0000-0000-0000-000000000001, between simulation seconds 100 and 300." />
  <div style="margin-top:12px"><button class="primary" :disabled="busy" @click="run">{{busy ? 'Running…' : 'Run experimental query'}}</button></div>
  <p v-if="error" role="alert" style="color:#b91c1c">{{error}}</p>
  <template v-if="response">
   <h3>Validated query plan</h3>
   <pre style="overflow:auto;white-space:pre-wrap">{{JSON.stringify(response.plan, null, 2)}}</pre>
   <h3>Historian result</h3>
   <p>Function: {{response.result.engineeringFunction || response.plan.engineering_function}} · Signal: {{response.result.mapping?.operational_signal || '—'}} · Observations: {{response.result.observationCount ?? response.result.observations?.length ?? 0}}</p>
   <table v-if="response.result.observations?.length">
    <thead><tr><th>Simulation time (hours)</th><th>Value</th><th>Observed at</th></tr></thead>
    <tbody><tr v-for="(sample, index) in response.result.observations" :key="index"><td>{{sample.simulationTimeHours}}</td><td>{{sample.value}}</td><td>{{sample.observedAt}}</td></tr></tbody>
   </table>
   <p v-else>No observations returned.</p>
  </template>
 </section>
</template>
