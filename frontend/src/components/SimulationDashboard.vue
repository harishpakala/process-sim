<script setup lang="ts">
import { onMounted, onUnmounted, ref } from 'vue'
type Snapshot = { connected: boolean; simulation: { TimeHours: number; Running: boolean; ControlMode: string; RealTimeFactor: number }; measurements: number[]; manipulatedVariables: number[] }
const data = ref<Snapshot | null>(null)
const error = ref('')
const busy = ref(false)
const loading = ref(false)
let timer: ReturnType<typeof setInterval> | undefined
const names: Record<number, string> = { 1:'A feed flow',2:'D feed flow',3:'E feed flow',4:'A/C feed flow',5:'Recycle flow',6:'Reactor feed rate',7:'Reactor pressure',8:'Reactor level',9:'Reactor temperature',10:'Purge rate',11:'Separator temperature',12:'Separator level',13:'Separator pressure',14:'Separator underflow',15:'Stripper level',16:'Stripper pressure',17:'Stripper underflow',18:'Stripper temperature',19:'Stripper steam flow',20:'Compressor work',21:'Reactor cooling outlet temperature',22:'Separator cooling outlet temperature' }
const units: Record<number,string> = { 1:'kscmh',2:'kg/hr',3:'kg/hr',4:'kscmh',5:'kscmh',6:'kscmh',7:'kPa gauge',8:'%',9:'°C',10:'kscmh',11:'°C',12:'%',13:'kPa gauge',14:'m³/hr',15:'%',16:'kPa gauge',17:'m³/hr',18:'°C',19:'kg/hr',20:'kW',21:'°C',22:'°C' }
async function refresh() {
 if (loading.value) return
 loading.value=true
 try {
  const response=await fetch('/api/simulation/status')
  const body=await response.json()
  if (!response.ok) throw new Error(body.error || 'Simulation API unavailable')
  data.value=body
  error.value=''
 } catch(e) { data.value=null;error.value=e instanceof Error?e.message:String(e) }
 finally {loading.value=false}
}
async function command(action:'Start'|'Stop'|'Reset') {
 busy.value=true
 try {
  const response=await fetch('/api/simulation/control',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({action})})
  const body=await response.json()
  if(!response.ok || !body.success) throw new Error(body.error || 'OPC UA command failed')
  await refresh()
 } catch(e) {error.value=e instanceof Error?e.message:String(e)}
 finally {busy.value=false}
}
onMounted(()=>{void refresh();timer=setInterval(()=>void refresh(),2000)})
onUnmounted(()=>{if(timer)clearInterval(timer)})
</script>

<template>
 <div style="display:grid;gap:16px">
  <section class="panel">
   <div class="panel-title"><div><h2>TEP OPC UA Simulation</h2><p>Live values from the existing OPC UA server via Python API</p></div><span class="pill">{{data?.simulation.Running?'Running':data?'Stopped':'Disconnected'}}</span></div>
   <p v-if="error" role="alert" style="color:#b45309">{{error}}</p>
   <div v-if="data" class="metric-grid">
    <div class="metric"><small>SIMULATION TIME</small><strong>{{data.simulation.TimeHours.toFixed(3)}} h</strong></div>
    <div class="metric"><small>CONTROL MODE</small><strong>{{data.simulation.ControlMode}}</strong></div>
    <div class="metric"><small>REAL-TIME FACTOR</small><strong>{{data.simulation.RealTimeFactor}}×</strong></div>
   </div>
   <div class="control-row">
    <button class="primary" :disabled="!data||busy||data.simulation.Running" @click="command('Start')">Start</button>
    <button class="secondary" :disabled="!data||busy||!data.simulation.Running" @click="command('Stop')">Stop</button>
    <button class="secondary" :disabled="!data||busy" @click="command('Reset')">Reset</button>
    <button class="secondary" :disabled="loading" @click="refresh">Refresh</button>
   </div>
  </section>
  <section class="panel">
   <div class="panel-title"><h2>Process measurements (XMEAS)</h2><span class="pill">Read-only · 2 s polling</span></div>
   <div v-if="data" style="display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:12px">
    <div v-for="(value,index) in data.measurements" :key="index" style="border:1px solid var(--border,#d6dde3);border-radius:8px;padding:12px">
     <small>XMEAS{{index+1}} · {{names[index+1]||'Analyzer measurement'}}</small>
     <div style="font-weight:700;font-size:20px;margin-top:6px">{{Number(value).toFixed(3)}} <small>{{units[index+1]||(index>=22?'mol%':'')}}</small></div>
    </div>
   </div>
   <p v-else class="subdued">Start the OPC UA server and Python API to see live measurements.</p>
  </section>
  <section class="panel">
   <div class="panel-title"><h2>Manipulated variables (XMV)</h2><span class="pill">Read-only</span></div>
   <div v-if="data" style="display:grid;grid-template-columns:repeat(auto-fit,minmax(160px,1fr));gap:12px">
    <div v-for="(value,index) in data.manipulatedVariables" :key="index"><small>XMV{{index+1}}</small><strong style="display:block">{{Number(value).toFixed(3)}}</strong></div>
   </div>
  </section>
 </div>
</template>
