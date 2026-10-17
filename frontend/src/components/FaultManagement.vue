<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'

type Fault = { fault_id:string; fault_type:string; target:string; magnitude:number|null; value:number|null; start_time_hours:number; duration_hours:number|null; status:string }
const faults = ref<Fault[]>([])
const connected = ref(false)
const error = ref('')
const message = ref('')
const busy = ref(false)
const faultId = ref('')
const faultType = ref('process_disturbance')
const target = ref('IDV1')
const magnitude = ref(1)
const value = ref(0)
const durationHours = ref(0)
let timer: ReturnType<typeof setInterval> | undefined

const targets = computed(()=>faultType.value==='process_disturbance'
 ? Array.from({length:20},(_,i)=>'IDV'+(i+1))
 : Array.from({length:41},(_,i)=>'XMEAS'+(i+1)).concat(Array.from({length:12},(_,i)=>'XMV'+(i+1))))
function onTypeChange(){target.value=targets.value[0]}
function generateId(){return 'fault-'+Date.now().toString(36)}
async function refresh(){
 try {
  const response=await fetch('/api/simulation/faults')
  const result=await response.json()
  if(!response.ok)throw new Error(result.error||'Fault listing failed')
  faults.value=result.faults
  connected.value=true
  error.value=''
 }catch(e){connected.value=false;error.value=e instanceof Error?e.message:String(e)}
}
async function send(payload:Record<string,unknown>){
 busy.value=true;message.value='';error.value=''
 try {
  const response=await fetch('/api/simulation/faults',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)})
  const result=await response.json()
  if(!response.ok||!result.success)throw new Error(result.error||'Fault operation failed')
  message.value=payload.action==='inject'?'Fault injected successfully':'Fault cleared successfully'
  await refresh()
 }catch(e){error.value=e instanceof Error?e.message:String(e)}
 finally{busy.value=false}
}
function inject(){
 const id=faultId.value.trim()||generateId()
 if(!Number.isFinite(magnitude.value)||!Number.isFinite(value.value)||!Number.isFinite(durationHours.value)||durationHours.value<0){error.value='Enter finite numbers and a non-negative duration';return}
 void send({action:'inject',faultId:id,faultType:faultType.value,target:target.value,magnitude:magnitude.value,value:value.value,durationHours:durationHours.value})
}
function clear(id:string){if(window.confirm('Clear fault '+id+'?'))void send({action:'clear',faultId:id})}
function clearAll(){if(window.confirm('Clear all registered faults?'))void send({action:'clear_all'})}
onMounted(()=>{void refresh();timer=setInterval(()=>void refresh(),4000)})
onUnmounted(()=>{if(timer)clearInterval(timer)})
</script>

<template>
 <div style="display:grid;gap:16px">
  <section class="panel">
   <div class="panel-title"><div><h2>Fault injection via OPC UA</h2><p>Calls the existing TEP FaultManagement methods</p></div><span class="pill">{{connected?'Connected':'Disconnected'}}</span></div>
   <p v-if="error" role="alert" style="color:#b45309">{{error}}</p>
   <p v-if="message" role="status">{{message}}</p>
   <form @submit.prevent="inject" style="display:grid;gap:14px">
    <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(190px,1fr));gap:12px">
     <label style="display:grid;gap:5px">Fault ID <input v-model="faultId" placeholder="Auto-generated if empty" maxlength="100" /></label>
     <label style="display:grid;gap:5px">Fault type
      <select v-model="faultType" @change="onTypeChange">
       <option value="process_disturbance">Process disturbance</option>
       <option value="bias">Bias</option><option value="drift">Drift</option><option value="stuck">Stuck</option>
      </select>
     </label>
     <label style="display:grid;gap:5px">Target
      <select v-model="target"><option v-for="item in targets" :key="item" :value="item">{{item}}</option></select>
     </label>
     <label v-if="faultType!=='stuck'" style="display:grid;gap:5px">Magnitude
      <input v-model.number="magnitude" type="number" step="any" required />
     </label>
     <label v-else style="display:grid;gap:5px">Stuck value
      <input v-model.number="value" type="number" step="any" required />
     </label>
     <label style="display:grid;gap:5px">Duration (simulation hours; 0 = indefinite)
      <input v-model.number="durationHours" type="number" min="0" step="any" required />
     </label>
    </div>
    <div class="control-row"><button class="primary" type="submit" :disabled="!connected||busy">Inject fault</button><span>Simulation environment only. Injection affects the running TEP model.</span></div>
   </form>
  </section>
  <section class="panel">
   <div class="panel-title"><div><h2>Registered faults</h2><p>Includes active and expired faults returned by OPC UA</p></div><div class="control-row"><button class="secondary" :disabled="busy" @click="refresh">Refresh</button><button class="secondary" :disabled="!connected||busy||!faults.length" @click="clearAll">Clear all</button></div></div>
   <p v-if="!faults.length" class="subdued">No registered faults.</p>
   <div v-for="fault in faults" :key="fault.fault_id" style="display:flex;align-items:center;justify-content:space-between;gap:12px;padding:12px 0;border-bottom:1px solid #cbd5e1;flex-wrap:wrap">
    <div><strong>{{fault.fault_id}}</strong> <span class="pill">{{fault.status}}</span><div><small>{{fault.fault_type}} · {{fault.target}} · injected at {{Number(fault.start_time_hours).toFixed(3)}} h</small></div><small>Magnitude: {{fault.magnitude??'—'}} · Value: {{fault.value??'—'}} · Duration: {{fault.duration_hours===null?'indefinite':fault.duration_hours+' h'}}</small></div>
    <button class="secondary" :disabled="busy||!connected" @click="clear(fault.fault_id)">Clear</button>
   </div>
  </section>
 </div>
</template>

<style scoped>
input,select{padding:9px;border:1px solid #aebfc9;border-radius:7px;background:transparent;color:inherit;max-width:100%}
</style>
