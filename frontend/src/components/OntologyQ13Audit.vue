<script setup lang="ts">
import { onMounted, ref } from 'vue'

type Triple = { s: string; p: string; o: string; o_type: string }
type Domain = { domain: string; status?: string; summarySource?: string; verifiedTriples?: Triple[]; finding?: { verified_facts?: string[]; unverified_or_missing?: string[]; verified_status_assertions?: string[] } }
type Historian = { run_id?: string; signal?: string; count?: number; window_seconds?: number[]; first?: { simulation_seconds?: number; value?: number }; last?: { simulation_seconds?: number; value?: number } }
type Audit = { question?: string; answer: string; status?: string; method?: string; synthesisMode?: string; fallbackReason?: string; acceptance?: Record<string, unknown>; historian?: Historian; domains?: Domain[] }
const result = ref<Audit | null>(null)
const loading = ref(false)
const error = ref('')
async function apiJson(url: string, options?: RequestInit): Promise<Record<string, any>> {
 const response = await fetch(url, options)
 const raw = await response.text()
 let data: Record<string, any>
 try { data = raw.trim() ? JSON.parse(raw) : {} }
 catch { throw new Error(`API returned non-JSON (HTTP ${response.status}): ${raw.slice(0, 240) || 'empty response'}`) }
 if (!response.ok) throw new Error(data.error || `API request failed (HTTP ${response.status}${raw ? '' : ', empty response'})`)
 if (!raw.trim()) throw new Error(`API returned an empty response (HTTP ${response.status})`)
 return data
}
const liveState = ref('')
const liveBusy = ref(false)
const liveError = ref('')
async function liveStart() {
 liveBusy.value = true; liveError.value = ''
 try {
  const data = await apiJson('/api/ai/q13/ontology/live/start', { method:'POST' })
  liveState.value = data.state || 'QUEUED'
 } catch (e) { liveError.value = e instanceof Error ? e.message : String(e) }
 finally { liveBusy.value = false }
}
async function liveCheck() {
 liveBusy.value = true; liveError.value = ''
 try {
  const data = await apiJson('/api/ai/q13/ontology/live/status', {cache:'no-store'})
  liveState.value = data.state || 'UNKNOWN'
  if (data.state === 'COMPLETED') {
   const audit = await apiJson('/api/ai/q13/ontology/live/result', {cache:'no-store'})
   result.value = audit as Audit
  }
  if (data.state === 'FAILED') liveError.value = data.error || 'Live Q13 failed'
 } catch (e) { liveError.value = e instanceof Error ? e.message : String(e) }
 finally { liveBusy.value = false }
}
const domainNames: Record<string,string> = { dexpi:'DEXPI', ecad:'ECAD', engineeringbom:'Engineering BOM', assetinventory:'AssetInventory', productcatalog:'ProductCatalog', opcuaconnectivity:'OPC UA Connectivity' }
const name = (value: string) => domainNames[value] || value
const shortPredicate = (value: string) => value.split(/[/#]/).pop() || value
async function refresh() {
 loading.value = true
 error.value = ''
 try {
  const data = await apiJson('/api/ai/q13/ontology/result', { cache:'no-store' })
  result.value = data as Audit
 } catch (e) {
  result.value = null
  error.value = e instanceof Error ? e.message : String(e)
 } finally { loading.value = false }
}
onMounted(() => { void refresh() })
</script>

<template>
 <div class="q13-layout">
  <section class="panel">
   <div class="panel-title">
    <div><h2>Q13 — Ontology-guided engineering trace</h2><p>Read-only view of the configured, completed Q13 audit. This does not execute a new query.</p></div>
    <button type="button" class="secondary" :disabled="loading" @click="refresh">{{ loading ? 'Loading…' : 'Reload audit' }}</button>
   </div>
   <div class="q13-status"><button type="button" class="secondary" :disabled="liveBusy || liveState==='RUNNING' || liveState==='QUEUED'" @click="liveStart">Run live Q13 (opt-in)</button><button type="button" class="secondary" :disabled="liveBusy" @click="liveCheck">Check live status / load result</button><span v-if="liveState">Live job: {{ liveState }}</span></div>
   <p v-if="liveError" role="alert" class="q13-error">{{ liveError }}</p>
   <p v-if="error" role="alert" class="q13-error">{{ error }}</p>
   <template v-if="result">
    <div class="q13-status">
     <span><strong>Review:</strong> {{ result.status || 'Unknown' }}</span>
     <span><strong>Synthesis:</strong> {{ result.synthesisMode || 'Unknown' }}</span>
     <span><strong>Evidence domains:</strong> {{ result.domains?.length || 0 }}/6</span>
    </div>
    <p v-if="result.synthesisMode==='DETERMINISTIC_FALLBACK'" class="q13-warning">Ollama synthesis was rejected or unavailable. The answer below is a deterministic reconstruction from audited evidence. {{ result.fallbackReason || '' }}</p>
    <p class="q13-question">{{ result.question }}</p>
    <h3>Engineering answer</h3>
    <pre class="q13-answer">{{ result.answer }}</pre>
    <p class="q13-note">Verified RDF assertions establish recorded engineering data, not physical installation or a live OPC UA connection. Review status is not production approval.</p>
   </template>
  </section>
  <template v-if="result">
   <section class="panel">
    <h3>Six-domain RDF evidence</h3>
    <p class="q13-note">Expand a domain to inspect original subject–predicate–object triples and source-grounded uncertainties.</p>
    <details v-for="domain in result.domains || []" :key="domain.domain" class="q13-domain">
     <summary><strong>{{ name(domain.domain) }}</strong> · {{ domain.status || 'Unknown' }} · {{ domain.verifiedTriples?.length || 0 }} triples</summary>
     <div class="q13-domain-body">
      <h4>Verified RDF assertions</h4>
      <ul><li v-for="(fact,i) in domain.finding?.verified_facts || []" :key="i">{{ fact }}</li></ul>
      <template v-if="domain.finding?.verified_status_assertions?.length"><h4>Verified status literals (not operational proof)</h4><ul><li v-for="(fact,i) in domain.finding.verified_status_assertions" :key="i">{{ fact }}</li></ul></template>
      <template v-if="domain.finding?.unverified_or_missing?.length"><h4>Missing or unverified</h4><ul><li v-for="(fact,i) in domain.finding.unverified_or_missing" :key="i">{{ fact }}</li></ul></template>
      <details><summary>Original RDF triples</summary>
       <div class="q13-table-wrap"><table class="q13-table"><thead><tr><th>#</th><th>Predicate</th><th>Object</th><th>Subject URI</th></tr></thead>
       <tbody><tr v-for="(triple,i) in domain.verifiedTriples || []" :key="i"><td>{{ i }}</td><td>{{ shortPredicate(triple.p) }}</td><td>{{ triple.o || '(empty)' }}</td><td class="q13-uri">{{ triple.s }}</td></tr></tbody></table></div>
      </details>
     </div>
    </details>
   </section>
   <section class="panel">
    <h3>Historian evidence</h3>
    <div v-if="result.historian" class="q13-status">
     <span><strong>Signal:</strong> {{ result.historian.signal }}</span>
     <span><strong>Observations:</strong> {{ result.historian.count }}</span>
     <span><strong>Window:</strong> {{ result.historian.window_seconds?.join('–') }} s</span>
     <span><strong>First:</strong> {{ result.historian.first?.value }} at {{ result.historian.first?.simulation_seconds }} s</span>
     <span><strong>Last:</strong> {{ result.historian.last?.value }} at {{ result.historian.last?.simulation_seconds }} s</span>
    </div>
    <p v-else>No historian summary is present in this audit.</p>
    <details><summary>Audit acceptance and provenance</summary><p><strong>Method:</strong> {{ result.method }}</p><pre class="q13-json">{{ JSON.stringify(result.acceptance || {}, null, 2) }}</pre></details>
   </section>
  </template>
 </div>
</template>

<style scoped>
.q13-layout{display:grid;gap:16px}
.q13-status{display:flex;flex-wrap:wrap;gap:10px;margin:14px 0}
.q13-status span{border:1px solid var(--border,#d6dee5);border-radius:8px;padding:9px 12px}
.q13-error,.q13-warning{padding:12px;border-left:3px solid #b76a1b;background:rgba(183,106,27,.09)}
.q13-question{font-weight:600;margin-top:16px}
.q13-answer{white-space:pre-wrap;overflow-wrap:anywhere;font:inherit;line-height:1.6}
.q13-note{opacity:.8;font-size:.9em}
.q13-domain{border-top:1px solid var(--border,#d6dee5);padding:12px 0}
.q13-domain summary{cursor:pointer}
.q13-domain-body{padding:12px 0}
.q13-domain-body li{overflow-wrap:anywhere;margin:5px 0}
.q13-table-wrap{overflow:auto}
.q13-table{border-collapse:collapse;font-size:.85em;width:100%}
.q13-table td,.q13-table th{padding:7px;border:1px solid var(--border,#d6dee5);text-align:left;vertical-align:top;overflow-wrap:anywhere}
.q13-uri{min-width:250px;max-width:480px}
.q13-json{white-space:pre-wrap;overflow-wrap:anywhere}
</style>
