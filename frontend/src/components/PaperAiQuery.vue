<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'

type Question = { id: string; question: string; requiresRun: boolean }
type Run = { run_id?: string; runId?: string; [key:string]: unknown }
type FaultEvent = { event_id: string; fault_id: string; action: string; simulation_time_hours?: number; simulation_seconds?: number; event_source?: string; target?: string }
type Answer = { id: string; question: string; answer: string; limitations: string[]; status: string; evidence?: unknown; reason?: string; model?: string; promptVersion: string; answerValidation: string; warning: string; runId?: string; eventId?: string; questionAdaptation?: string }
type Mapping = { assetId?: string; dexpiLocal?: string; ecadLocal?: string; signal?: string; productId?: string; eclassCode?: string }
type Sample = { simulation_seconds?: number; value?: number }
type SamplePair = { before?: Sample | null; after?: Sample | null }
type EngineeringRecord = { equipment_tag?: string; asset_id?: string; signal?: string; manufacturer?: string; product_key?: string; product_uri?: string; eclass_class?: string; eclass_irdi?: string; eclass_verification?: string; catalog_technical_specifications?: unknown; qudt_product_specification?: unknown }
function object(value: unknown): Record<string, unknown> { return value && typeof value==='object' && !Array.isArray(value) ? value as Record<string,unknown> : {} }
const evidence = computed(()=>object(answer.value?.evidence))
const mappings = computed<Mapping[]>(()=>Array.isArray(evidence.value.graphdb_verified_mappings) ? evidence.value.graphdb_verified_mappings as Mapping[] : [])
const engineering = computed<EngineeringRecord[]>(()=> Object.values(evidence.value).filter(v=>object(v).equipment_tag).map(v=>v as EngineeringRecord))
const temporal = computed(()=>object(evidence.value.temporal))
const event = computed(()=>object(evidence.value.activation || temporal.value.activation))
const measurements = computed<Record<string,SamplePair>>(()=>{
 const raw = object(evidence.value.measurements || temporal.value.measurements)
 if(temporal.value.signal && raw.before !== undefined) return { [String(temporal.value.signal)]: raw as SamplePair }
 return raw as Record<string,SamplePair>
})
const sampleRows = computed(()=>Object.entries(measurements.value).map(([signal,pair])=>({signal,before:pair?.before,after:pair?.after})))
function seconds(value:unknown):string { return typeof value==='number' && Number.isFinite(value) ? value.toFixed(3)+' s' : 'Not recorded' }
function sampleValue(sample?:Sample|null):string { return sample && typeof sample.value==='number' ? String(sample.value) : 'Not recorded' }
function assetShort(uri?:string):string { return uri ? uri.split('/').pop() || uri : '—' }
const evidenceSources = computed(()=>{
 const sources:string[]=[]
 if(mappings.value.length) sources.push('GraphDB: exact four-domain mapping')
 if(engineering.value.length) sources.push('AssetInventory / ProductCatalog instance evidence')
 if(event.value.fault_id || sampleRows.value.length) sources.push('TimescaleDB: persisted fault events and signal samples')
 return sources
})
const relevantLimitations = computed(()=>{
 const q=Number(answer.value?.id.slice(1) || 0)
 return (answer.value?.limitations || []).filter(s=>{
  const t=s.toLowerCase()
  if(q<=3 && (t.includes('product information') || t.includes('product unavailable') || t.includes('product not available')))return false
  if(q<=7 && (t.includes('fault activation') || t.includes('causal fault')))return false
  return true
 })
})
const mode = ref<'custom'|'paper'>('custom')
const customQuestion = ref('')
const examples = [
 'Which reactor instruments are linked to operational signals?',
 'Show the product and manufacturer associated with TI-1101.',
 'What ECLASS and QUDT attributes are recorded for PI-1101?',
 'What measurements were recorded before and after the selected fault command?'
]
const temporalCustom = computed(()=>/fault|inject|before|after|historian|recorded value|measurement|timeseries|time series|simulation time|operational history|trend/i.test(customQuestion.value))
const questions = ref<Question[]>([])
const runs = ref<Run[]>([])
const events = ref<FaultEvent[]>([])
const runId = ref('')
const eventId = ref('')
const questionId = ref('Q1')
const busy = ref(false)
const error = ref('')
const historyError = ref('')
const answer = ref<Answer | null>(null)
const selectedQuestion = computed(() => questions.value.find(q => q.id === questionId.value))
const available = computed(() => questions.value.filter(q => !q.requiresRun || Boolean(runId.value)))
const selectedEvent = computed(() => events.value.find(e => e.event_id === eventId.value))
const firstInjection = computed(() => events.value.find(e => ['inject','activate','enable','start'].includes(e.action.toLowerCase())))
const runOptions = computed(() => runs.value.map(r => String(r.run_id || r.runId || '')).filter(Boolean))
function clearAnswer(){ answer.value = null; error.value = '' }
async function getJson(url:string, options?:RequestInit) {
 const response = await fetch(url,options)
 const data = await response.json()
 if(!response.ok) throw new Error(data.error || 'Request failed')
 return data
}
async function loadQuestions(){
 try {
  const data = await getJson('/api/ai/paper/questions')
  questions.value = data.questions
 } catch(e){error.value = e instanceof Error ? e.message : String(e)}
}
async function loadRuns(){
 historyError.value=''
 try {
  const data = await getJson('/api/simulation/runs?limit=100')
  runs.value = Array.isArray(data.runs) ? data.runs : []
 } catch(e){historyError.value = 'Run history unavailable: '+(e instanceof Error ? e.message : String(e))}
}
async function loadEvents(){
 events.value=[]; eventId.value=''
 if(!runId.value)return
 historyError.value=''
 try {
  const data=await getJson('/api/simulation/fault-events/history?runId='+encodeURIComponent(runId.value))
  events.value=Array.isArray(data.events)?data.events:[]
  eventId.value=events.value.find(e=>['inject','activate','enable','start'].includes(e.action.toLowerCase()))?.event_id || ''
 } catch(e){historyError.value = 'Fault history unavailable: '+(e instanceof Error ? e.message : String(e))}
}
watch(runId,()=>{clearAnswer();void loadEvents();if(!runId.value && Number(questionId.value.slice(1))>=8)questionId.value='Q1'})
watch(questionId,clearAnswer)
watch(mode,clearAnswer)
watch(customQuestion,clearAnswer)
watch(eventId,clearAnswer)
async function ask(){
 clearAnswer()
 if(mode.value==='paper' && !selectedQuestion.value)return
 if(mode.value==='custom' && (customQuestion.value.trim().length<5 || customQuestion.value.length>1000)){error.value='Enter a question between 5 and 1000 characters';return}
 if(mode.value==='paper' && selectedQuestion.value?.requiresRun && !runId.value){error.value='Select a recorded run';return}
 if(mode.value==='paper' && selectedQuestion.value?.requiresRun && !eventId.value){error.value='Select a recorded injection event';return}
 if(mode.value==='custom' && temporalCustom.value && !runId.value){error.value='Select a recorded run for this temporal question';return}
 busy.value=true
 try{
  answer.value=await getJson(mode.value==='custom' ? '/api/ai/custom/answer' : '/api/ai/paper/answer',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(mode.value==='custom' ? {question:customQuestion.value.trim(),runId:temporalCustom.value ? runId.value||null : null,eventId:temporalCustom.value ? eventId.value||null : null} : {questionId:questionId.value,runId:runId.value||null,eventId:selectedQuestion.value?.requiresRun ? eventId.value : null})})
 }catch(e){error.value=e instanceof Error?e.message:String(e)}
 finally{busy.value=false}
}
onMounted(()=>{void loadQuestions();void loadRuns()})
</script>

<template>
 <div style="display:grid;gap:16px">
  <section class="panel">
   <div class="panel-title"><div><h2>TEP NEXUS — AI Query</h2><p>Ask exploratory engineering questions or run the controlled Q1–Q10 evaluation.</p></div><span class="pill">{{mode==='paper'?'Q1–Q10':'Exploratory'}}</span></div>
   <div class="mode-switch" role="group" aria-label="Query mode">
    <button type="button" :class="mode==='custom'?'primary':'secondary'" :aria-pressed="mode==='custom'" @click="mode='custom'">Ask a question</button>
    <button type="button" :class="mode==='paper'?'primary':'secondary'" :aria-pressed="mode==='paper'" @click="mode='paper'">Paper evaluation</button>
   </div>
   <div v-if="mode==='custom'" class="custom-query">
    <label for="custom-question">Your question</label>
    <textarea id="custom-question" v-model="customQuestion" maxlength="1000" rows="4" placeholder="Which reactor instruments are linked to operational signals?" />
    <p class="subdued">Questions use supported engineering, catalog and historian evidence only. Free-text exploration is not included in the paper evaluation scores.</p>
    <div class="example-list"><strong>Example questions</strong><button v-for="example in examples" :key="example" type="button" class="secondary example-button" @click="customQuestion=example">{{example}}</button></div>
   </div>
   <div style="display:grid;gap:14px">
    <label style="display:grid;gap:6px">Recorded simulation run (optional for Q1–Q7)
     <select v-model="runId"><option value="">Engineering only — no run selected</option><option v-for="id in runOptions" :key="id" :value="id">{{id}}</option></select>
    </label>
    <div class="control-row"><button class="secondary" type="button" @click="loadRuns">Refresh runs</button><button class="secondary" type="button" :disabled="!runId" @click="loadEvents">Refresh recorded faults</button></div>
    <p v-if="historyError" role="status" style="color:#b45309">{{historyError}}. Engineering-only queries remain available.</p>
    <label v-if="runId" style="display:grid;gap:6px">Recorded fault command
     <select v-model="eventId"><option value="">Select recorded injection event</option><option v-for="event in events.filter(e=>['inject','activate','enable','start'].includes(e.action.toLowerCase()))" :key="event.event_id" :value="event.event_id">{{event.fault_id}} · {{event.action}} · {{event.target || 'target not recorded'}} · {{event.simulation_seconds ?? (event.simulation_time_hours === undefined ? '?' : event.simulation_time_hours*3600)}} s</option></select>
    </label>
    <p v-if="runId && !events.length" class="subdued">No persisted fault events found for this run.</p>
    <p v-if="selectedEvent && firstInjection && selectedEvent.event_id!==firstInjection.event_id" role="alert" style="color:#b45309">The current evidence generator uses the first injection command. Select that event to avoid incorrect temporal attribution.</p>
    <label v-if="mode==='paper'" style="display:grid;gap:6px">Evaluation question
     <select v-model="questionId"><option v-for="q in available" :key="q.id" :value="q.id">{{q.id}} — {{q.question}}</option></select>
    </label>
    <p v-if="mode==='paper' && selectedQuestion" class="subdued">{{selectedQuestion.requiresRun ? 'Requires a recorded run, fault command and samples; the simulator may be stopped.' : 'Engineering evidence only; simulation is not required.'}}</p>
    <button class="primary" type="button" :disabled="busy || (mode==='paper' ? (!selectedQuestion || (selectedQuestion.requiresRun && (!runId || !eventId))) : (customQuestion.trim().length<5 || (temporalCustom && !runId)))" @click="ask">{{busy?'Retrieving evidence and querying Ollama…':mode==='custom'?'Ask TEP NEXUS':'Ask selected question'}}</button>
    <p v-if="error" role="alert" style="color:#b45309">{{error}}</p>
   </div>
  </section>
  <section v-if="answer" class="panel result-panel">
   <div class="panel-title"><div><h2>{{answer.id==='CUSTOM'?'Exploratory query':answer.id+' — Query result'}}</h2><p>{{answer.question}}</p></div><span class="pill">{{answer.status}}</span></div>
   <div v-if="answer.status!=='EVIDENCE_AVAILABLE'" class="result-notice" role="status">{{answer.reason || 'Required evidence is incomplete. This is not a verified answer.'}}</div>
   <div class="result-section">
    <h3>AI-generated explanation</h3>
    <p class="answer-text">{{answer.answer}}</p>
    <p class="subdued">Model-generated text is not verified against the evidence. Use the structured records below to check individual claims.</p>
   </div>
   <div class="result-section">
    <div class="section-heading"><h3>Supporting evidence</h3><span class="pill">{{mappings.length || engineering.length || sampleRows.length || (event.fault_id ? 1 : 0)}} record(s)</span></div>
    <div v-if="mappings.length" class="table-scroll">
     <table class="evidence-table"><thead><tr><th>ECAD instrument</th><th>AAS asset identifier</th><th>DEXPI reference</th><th>Signal</th><th v-if="Number(answer.id.slice(1))>=7">Product candidate</th></tr></thead>
      <tbody><tr v-for="(m,i) in mappings" :key="i"><td>{{m.ecadLocal || '—'}}</td><td><span class="mono">{{assetShort(m.assetId)}}</span><small class="full-id">{{m.assetId}}</small></td><td>{{m.dexpiLocal || '—'}}</td><td><strong>{{m.signal || '—'}}</strong></td><td v-if="Number(answer.id.slice(1))>=7">{{m.productId || '—'}}</td></tr></tbody>
     </table>
    </div>
    <div v-if="engineering.length" class="table-scroll">
     <table class="evidence-table"><thead><tr><th>Instrument</th><th>Asset</th><th>Signal</th><th>Product candidate</th><th>Manufacturer</th><th v-if="answer.id==='Q5'">ECLASS</th></tr></thead>
      <tbody><tr v-for="(m,i) in engineering" :key="i"><td>{{m.equipment_tag || '—'}}</td><td class="mono">{{assetShort(m.asset_id)}}</td><td>{{m.signal || '—'}}</td><td>{{m.product_key || '—'}}</td><td>{{m.manufacturer || '—'}}</td><td v-if="answer.id==='Q5'">{{m.eclass_class || '—'}}<small class="full-id">{{m.eclass_irdi || 'No IRDI recorded'}}</small></td></tr></tbody>
     </table>
     <details v-if="answer.id==='Q5'" class="detail-toggle"><summary>Catalog specifications and QUDT attributes</summary><div v-for="(m,i) in engineering" :key="i" class="spec-block"><strong>{{m.equipment_tag}} — {{m.eclass_verification || 'Verification status not provided'}}</strong><pre>{{JSON.stringify({specifications:m.catalog_technical_specifications,qudt:m.qudt_product_specification},null,2)}}</pre></div></details>
    </div>
    <div v-if="event.fault_id" class="event-summary">
     <strong>Recorded operator command</strong>
     <div>Fault: {{event.fault_id}} · Action: {{event.action}} · Simulation time: {{seconds(event.simulation_seconds)}} · Source: {{event.event_source || 'not specified'}}</div>
     <small>Recording an operator command does not independently verify activation or causality.</small>
    </div>
    <div v-if="sampleRows.length" class="table-scroll">
     <table class="evidence-table"><thead><tr><th>Signal</th><th>Before time</th><th>Before value</th><th>After time</th><th>After value</th></tr></thead>
      <tbody><tr v-for="row in sampleRows" :key="row.signal"><td><strong>{{row.signal}}</strong></td><td>{{seconds(row.before?.simulation_seconds)}}</td><td>{{sampleValue(row.before)}}</td><td>{{seconds(row.after?.simulation_seconds)}}</td><td>{{sampleValue(row.after)}}</td></tr></tbody>
     </table>
    </div>
    <p v-if="!mappings.length && !engineering.length && !sampleRows.length && !event.fault_id" class="subdued">No structured evidence records were returned for this question.</p>
   </div>
   <div class="result-section">
    <h3>Limitations and qualifications</h3>
    <ul v-if="relevantLimitations.length"><li v-for="(item,i) in relevantLimitations" :key="i">{{item}}</li></ul>
    <p v-else class="subdued">No question-specific limitations were supplied by the model. This does not imply the answer has been verified.</p>
    <p v-if="Number(answer.id.slice(1))>=8" class="subdued">{{answer.warning}}</p>
    <p v-if="answer.id==='Q4' || answer.id==='Q5' || answer.id==='Q7' || answer.id==='Q10'" class="subdued">Catalog product associations are candidates, not proof of installed hardware. ECLASS verification must be assessed separately.</p>
   </div>
   <div class="result-section">
    <h3>Evidence provenance and evaluation</h3>
    <p v-for="source in evidenceSources" :key="source" class="source-row">{{source}}</p>
    <p v-if="answer.runId" class="source-row">Run: <span class="mono">{{answer.runId}}</span></p>
    <p v-if="answer.eventId" class="source-row">Event: <span class="mono">{{answer.eventId}}</span></p>
    <p class="subdued">Model: {{answer.model || 'No LLM answer'}} · Prompt: {{answer.promptVersion}} · {{answer.answerValidation}} · Manual rubric grading required</p>
    <p v-if="answer.questionAdaptation==='EXPLORATORY_NOT_PAPER_EVALUATION'" class="subdued">Exploratory question: not part of the fixed Q1–Q10 evaluation or reported scores.</p>
    <p v-if="answer.questionAdaptation==='UI_CONTEXTUAL_TEMPORAL_WORDING'" class="subdued">Temporal question wording was adapted for the selected run; this is not an exact frozen-question replay.</p>
   </div>
   <details class="detail-toggle"><summary>Technical details — raw evidence JSON</summary><pre>{{JSON.stringify(answer.evidence,null,2)}}</pre></details>
  </section>
 </div>
</template>

<style scoped>
.mode-switch{display:flex;gap:8px;flex-wrap:wrap;margin:12px 0}.custom-query{display:grid;gap:10px;margin:12px 0}.custom-query textarea{width:100%;box-sizing:border-box;padding:12px;border:1px solid #334a62;border-radius:8px;background:#0c192a;color:#eaf4ff;font:inherit;resize:vertical}.example-list{display:grid;gap:8px}.example-list strong{font-size:12px}.example-button{text-align:left;white-space:normal;padding:9px 12px}
.result-panel{display:grid;gap:16px}.result-section{border-top:1px solid #334a62;padding-top:15px;display:grid;gap:9px}.result-section h3{font-size:14px;margin:0}.answer-text{white-space:pre-wrap;overflow-wrap:anywhere;line-height:1.65}.section-heading{display:flex;align-items:center;justify-content:space-between;gap:12px}.table-scroll{overflow-x:auto}.evidence-table{width:100%;border-collapse:collapse;font-size:12px;text-align:left}.evidence-table th,.evidence-table td{padding:10px;border-bottom:1px solid #334a62;vertical-align:top}.evidence-table th{color:#a9bfd0;font-weight:600}.full-id{display:block;overflow-wrap:anywhere;font-size:10px;opacity:.75;margin-top:3px}.mono{font-family:ui-monospace,SFMono-Regular,Consolas,monospace;overflow-wrap:anywhere}.event-summary{display:grid;gap:7px;padding:12px;border:1px solid #334a62;border-radius:8px}.event-summary small{color:#a9bfd0}.source-row{font-size:12px;margin:0}.detail-toggle{font-size:12px;overflow:hidden}.detail-toggle summary{cursor:pointer}.detail-toggle pre{white-space:pre-wrap;overflow-wrap:anywhere;max-height:420px;overflow:auto;font-size:11px}.spec-block{padding:12px 0}.result-notice{padding:12px;border:1px solid #b45309;border-radius:8px}.result-section ul{margin:0;padding-left:22px}.result-section li{margin:6px 0}
select{padding:10px;border:1px solid #657b92;border-radius:7px;background:#101820;color:#fff;max-width:100%;width:100%;color-scheme:dark}
select option,select optgroup{background:#101820;color:#fff}
select:focus-visible{outline:2px solid #79b8ff;outline-offset:2px}
select:disabled{opacity:.6;cursor:not-allowed}
</style>
