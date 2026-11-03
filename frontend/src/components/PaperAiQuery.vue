<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'

type Question = { id: string; question: string; requiresRun: boolean }
type Run = { run_id?: string; runId?: string; [key:string]: unknown }
type FaultEvent = { event_id: string; fault_id: string; action: string; simulation_time_hours?: number; simulation_seconds?: number; event_source?: string; target?: string }
type Answer = { answer: string; limitations: string[]; status: string; evidence?: unknown; reason?: string; model?: string; promptVersion: string; answerValidation: string; warning: string }
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
watch(eventId,clearAnswer)
async function ask(){
 clearAnswer()
 if(!selectedQuestion.value)return
 if(selectedQuestion.value.requiresRun && !runId.value){error.value='Select a recorded run';return}
 if(selectedQuestion.value.requiresRun && !eventId.value){error.value='Select a recorded injection event';return}
 busy.value=true
 try{
  answer.value=await getJson('/api/ai/paper/answer',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({questionId:questionId.value,runId:runId.value||null,eventId: selectedQuestion.value.requiresRun ? eventId.value : null})})
 }catch(e){error.value=e instanceof Error?e.message:String(e)}
 finally{busy.value=false}
}
onMounted(()=>{void loadQuestions();void loadRuns()})
</script>

<template>
 <div style="display:grid;gap:16px">
  <section class="panel">
   <div class="panel-title"><div><h2>TEP NEXUS — Paper Evaluation</h2><p>Read-only evidence-grounded Q1–Q10 queries. A live simulation is not required for engineering questions.</p></div><span class="pill">Q1–Q10</span></div>
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
    <label style="display:grid;gap:6px">Evaluation question
     <select v-model="questionId"><option v-for="q in available" :key="q.id" :value="q.id">{{q.id}} — {{q.question}}</option></select>
    </label>
    <p v-if="selectedQuestion" class="subdued">{{selectedQuestion.requiresRun ? 'Requires a recorded run, fault command and samples; the simulator may be stopped.' : 'Engineering evidence only; simulation is not required.'}}</p>
    <button class="primary" type="button" :disabled="busy || !selectedQuestion || (selectedQuestion.requiresRun && (!runId || !eventId))" @click="ask">{{busy?'Retrieving evidence and querying Ollama…':'Ask selected question'}}</button>
    <p v-if="error" role="alert" style="color:#b45309">{{error}}</p>
   </div>
  </section>
  <section v-if="answer" class="panel" style="display:grid;gap:12px">
   <div class="panel-title"><h2>Evidence-grounded answer</h2><span class="pill">{{answer.status}}</span></div>
   <p style="white-space:pre-wrap">{{answer.answer}}</p>
   <div v-if="answer.limitations?.length"><strong>Limitations</strong><ul><li v-for="(item,i) in answer.limitations" :key="i">{{item}}</li></ul></div>
   <p class="subdued">{{answer.warning}}</p>
   <details><summary>Inspect supporting evidence (JSON)</summary><pre style="overflow:auto;max-height:450px;white-space:pre-wrap;word-break:break-word">{{JSON.stringify(answer.evidence,null,2)}}</pre></details>
   <small>Prompt: {{answer.promptVersion}} · Model: {{answer.model || 'No LLM answer'}} · {{answer.answerValidation}}. Manual rubric grading is required.</small>
  </section>
 </div>
</template>

<style scoped>
select{padding:10px;border:1px solid #aebfc9;border-radius:7px;background:transparent;color:inherit;max-width:100%;width:100%}
</style>
