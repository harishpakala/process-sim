<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'
type Snapshot = { connected: boolean; simulation: { TimeHours: number; Running: boolean; ControlMode: string; RealTimeFactor: number }; measurements: number[]; manipulatedVariables: number[] }
const data = ref<Snapshot | null>(null)
const error = ref('')
const busy = ref(false)
const loading = ref(false)
let timer: ReturnType<typeof setInterval> | undefined
const names: Record<number, string> = { 1:'A feed flow',2:'D feed flow',3:'E feed flow',4:'A/C feed flow',5:'Recycle flow',6:'Reactor feed rate',7:'Reactor pressure',8:'Reactor level',9:'Reactor temperature',10:'Purge rate',11:'Separator temperature',12:'Separator level',13:'Separator pressure',14:'Separator underflow',15:'Stripper level',16:'Stripper pressure',17:'Stripper underflow',18:'Stripper temperature',19:'Stripper steam flow',20:'Compressor work',21:'Reactor cooling outlet temperature',22:'Separator cooling outlet temperature' }
const units: Record<number,string> = { 1:'kscmh',2:'kg/hr',3:'kg/hr',4:'kscmh',5:'kscmh',6:'kscmh',7:'kPa gauge',8:'%',9:'°C',10:'kscmh',11:'°C',12:'%',13:'kPa gauge',14:'m³/hr',15:'%',16:'kPa gauge',17:'m³/hr',18:'°C',19:'kg/hr',20:'kW',21:'°C',22:'°C' }
type FaultEvent = { sequence:number; action:string; fault_id:string; target:string; simulation_time_hours:number }
const faultEvents = ref<FaultEvent[]>([])
const eventError = ref('')
const selected = ref('XMEAS9')
const samples = ref<{time:number; measurements:number[]; manipulatedVariables:number[]}[]>([])
const mvNames = ['D feed flow','E feed flow','A feed flow','A/C feed flow','Compressor recycle valve','Purge valve','Separator pot liquid flow','Stripper liquid product flow','Stripper steam valve','Reactor cooling water flow','Condenser cooling water flow','Agitator speed']
const options = [...Array.from({length:41},(_,i)=>({id:'XMEAS'+(i+1),label:'XMEAS'+(i+1)+' — '+(names[i+1]||'Composition analyzer')})),...Array.from({length:12},(_,i)=>({id:'XMV'+(i+1),label:'XMV'+(i+1)+' — '+mvNames[i]}))]
const trend = computed(()=>{
 const mv=selected.value.startsWith('XMV')
 const index=Number(selected.value.slice(mv?3:5))-1
 return samples.value.map(s=>({x:s.time,y:(mv?s.manipulatedVariables:s.measurements)[index]})).filter(p=>Number.isFinite(p.x)&&Number.isFinite(p.y))
})
const unit = computed(()=>selected.value.startsWith('XMV')?'':(units[Number(selected.value.slice(5))]||'mol%'))
const chart = computed(()=>{
 const p=trend.value
 if(!p.length)return {path:'',lo:0,hi:1,start:0,end:1}
 const values=p.map(v=>v.y)
 let lo=Math.min(...values),hi=Math.max(...values)
 const pad=(hi-lo||Math.max(Math.abs(hi),1))*.08
 lo-=pad;hi+=pad
 const start=p[0].x,end=p[p.length-1].x
 const path=p.map((v,i)=>{
  const x=55+650*(end===start?(p.length===1?0:i/(p.length-1)):(v.x-start)/(end-start))
  const y=20+220*(hi-v.y)/(hi-lo)
  return (i?'L':'M')+x.toFixed(2)+' '+y.toFixed(2)
 }).join(' ')
 return {path,lo,hi,start,end}
})
const visibleEvents = computed(()=>{
 const start=chart.value.start,end=chart.value.end
 if(!trend.value.length||end<=start)return []
 return faultEvents.value.filter(e=>e.simulation_time_hours>=start&&e.simulation_time_hours<=end)
  .map(e=>({...e,x:55+650*(e.simulation_time_hours-start)/(end-start)}))
})
async function refreshEvents(){
 try{
  const response=await fetch('/api/simulation/fault-events')
  const body=await response.json()
  if(!response.ok)throw new Error(body.error||'Fault events unavailable')
  faultEvents.value=body.events
  eventError.value=''
 }catch(e){eventError.value=e instanceof Error?e.message:String(e)}
}
function fmt(n:number){return Number.isFinite(n)?n.toFixed(3):'—'}
async function refresh() {
 if (loading.value) return
 loading.value=true
 try {
  const response=await fetch('/api/simulation/status')
  const body=await response.json()
  if (!response.ok) throw new Error(body.error || 'Simulation API unavailable')
  const snap=body as Snapshot
  const time=Number(snap.simulation.TimeHours)
  const last=samples.value[samples.value.length-1]
  if(last && time<last.time) { samples.value=[]; faultEvents.value=[] }
  if(Number.isFinite(time) && (!last || time!==last.time)) samples.value=[...samples.value,{time,measurements:[...snap.measurements],manipulatedVariables:[...snap.manipulatedVariables]}].slice(-300)
  data.value=snap
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
onMounted(()=>{void refresh();void refreshEvents();timer=setInterval(()=>{void refresh();void refreshEvents()},2000)})
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
   <div class="panel-title"><div><h2>Live process trend</h2><p>Select any of the 41 XMEAS or 12 XMV variables</p></div><span class="pill">2 s polling · 300 samples</span></div>
   <div style="display:flex;gap:18px;flex-wrap:wrap;align-items:end;margin-bottom:16px">
    <label style="display:grid;gap:6px;flex:1;min-width:250px"><small>PROCESS VARIABLE</small>
     <select v-model="selected" style="padding:10px;border:1px solid #b8c6d0;border-radius:8px;background:transparent;color:inherit">
      <option v-for="option in options" :key="option.id" :value="option.id">{{option.label}}</option>
     </select>
    </label>
    <div><small>CURRENT VALUE</small><strong style="display:block;font-size:22px">{{trend.length?fmt(trend[trend.length-1].y):'—'}} {{unit}}</strong></div>
    <button class="secondary" @click="samples=[]">Clear history</button>
   </div>
   <div v-if="trend.length" style="overflow-x:auto">
    <svg viewBox="0 0 760 290" role="img" :aria-label="'Trend for '+selected" style="width:100%;min-width:440px;height:auto">
     <g stroke="currentColor" opacity=".2"><line x1="55" y1="20" x2="705" y2="20"/><line x1="55" y1="130" x2="705" y2="130"/><line x1="55" y1="240" x2="705" y2="240"/><line x1="55" y1="20" x2="55" y2="240"/></g>
     <g fill="currentColor" opacity=".8" font-size="12">
      <text x="48" y="24" text-anchor="end">{{fmt(chart.hi)}}</text>
      <text x="48" y="134" text-anchor="end">{{fmt((chart.hi+chart.lo)/2)}}</text>
      <text x="48" y="244" text-anchor="end">{{fmt(chart.lo)}}</text>
      <text x="55" y="258">{{fmt(chart.start)}}</text>
      <text x="705" y="258" text-anchor="end">{{fmt(chart.end)}}</text>
      <text x="380" y="283" text-anchor="middle">Simulation time (hours)</text>
     </g>
     <g v-for="event in visibleEvents" :key="event.sequence">
      <line :x1="event.x" y1="20" :x2="event.x" y2="240" :stroke="event.action==='inject'?'#dc2626':'#16a34a'" stroke-width="1.8" stroke-dasharray="5 4"/>
      <circle :cx="event.x" cy="20" r="4" :fill="event.action==='inject'?'#dc2626':'#16a34a'"/>
      <title>{{event.action==='inject'?'Injected':'Cleared'}} {{event.fault_id}} ({{event.target}}) at {{fmt(event.simulation_time_hours)}} h</title>
     </g>
     <path :d="chart.path" stroke="#0e7490" stroke-width="2.5" fill="none" stroke-linejoin="round" stroke-linecap="round"/>
    </svg>
   </div>
   <p v-else class="subdued">No samples yet. Connect to OPC UA and run the simulation.</p>
   <div style="display:flex;gap:16px;flex-wrap:wrap;margin-top:10px;font-size:13px">
    <span><span style="color:#dc2626">━━</span> Fault injected</span>
    <span><span style="color:#16a34a">━━</span> Fault cleared</span>
    <span>Markers appear within the collected time window; hover for details.</span>
   </div>
   <p v-if="eventError" class="subdued">Fault event annotations unavailable: {{eventError}}</p>
   <p class="subdued">History is stored only in this browser session. Switching variables preserves collected samples.</p>
  </section>
 </div>
</template>
