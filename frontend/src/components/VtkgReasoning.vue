<script setup lang="ts">
import { computed, ref } from 'vue'

// Local fixture only. No live mappings, runs or observations are asserted.
const executed = ref(false)
const selected = ref(0)
const interval = ref<'BEFORE'|'AFTER'>('BEFORE')
const samples = [0,10,20,30,40,50,60].map((time,i)=>({time,value:[100,102,99,98,84,76,73][i]!,id:'demo-observation-'+i,run:'demo-run',signal:'XMEAS6'}))
const command = {time:30,run:'demo-run',id:'demo-command'}
const relation = (s: typeof samples[number]) => s.run !== command.run ? 'UNKNOWN' : s.time < command.time ? 'BEFORE' : s.time > command.time ? 'AFTER' : 'AT'
const counts = computed(()=>({BEFORE:samples.filter(s=>relation(s)==='BEFORE').length,AFTER:samples.filter(s=>relation(s)==='AFTER').length,AT:samples.filter(s=>relation(s)==='AT').length}))
const matching = computed(()=>samples.filter(s=>relation(s)===interval.value))
const observation = computed(()=>matching.value[selected.value] ?? matching.value[0]!)
const question = 'Which DEXPI and ECAD entities are associated with feed-flow observations before and after the recorded disturbance command in the same run?'
const focus = ref<'semantic'|'temporal'>('semantic')
function chooseInterval(value:'BEFORE'|'AFTER') { interval.value=value; selected.value=0; focus.value='temporal' }
function chooseSample(id:string) {
 const s=samples.find(p=>p.id===id)
 if (!s) return
 const r=relation(s)
 if (r!=='BEFORE' && r!=='AFTER') return
 interval.value=r
 selected.value=matching.value.findIndex(p=>p.id===id)
 focus.value='temporal'
}
const x=(time:number)=>65+time*10
const y=(value:number)=>210-(value-65)*4
</script>
<template>
 <section class="reasoning-demo">
  <p class="notice" role="status"><strong>Illustrative reasoning prototype.</strong> Synthetic observations and example mapping edges; no live backend execution. Physical sensor identity and fault causation are not established.</p>
  <label>R05 · Combined semantic–temporal reasoning</label>
  <p>{{question}}</p>
  <button type="button" class="primary" @click="executed=true">Explore demonstration</button>
  <template v-if="executed">
   <h3>1. Derived Results</h3>
   <div class="choices" role="group" aria-label="Temporal relationship">
    <button v-for="r in (['BEFORE','AFTER'] as const)" :key="r" type="button" :aria-pressed="interval===r" @click="chooseInterval(r)">{{r}} command · {{counts[r]}}</button>
    <span class="at-count">At command · {{counts.AT}} (excluded)</span>
   </div>
   <table><thead><tr><th>Engineering entity</th><th>Shared signal</th><th>Relationship</th><th>Observations</th></tr></thead>
    <tbody><tr v-for="entity in ['DEXPI FI_106','ECAD FI-1101']" :key="entity"><td><button class="entity-button" type="button" @click="focus='semantic'">{{entity}}</button></td><td>XMEAS6</td><td>{{interval}}</td><td>{{matching.length}}</td></tr></tbody>
   </table>
   <label for="demo-observation">Supporting observation</label>
   <select id="demo-observation" v-model.number="selected" @change="focus='temporal'"><option v-for="(s,i) in matching" :key="s.id" :value="i">{{s.id}} · {{s.time}} s</option></select>
   <h3>2. VTKG Reasoning Evidence</h3>
   <div class="legend"><span><i class="semantic-key"></i>Engineering mapping (fixture)</span><span><i class="historian-key"></i>Historian / run evidence (fixture)</span><span><i class="derived-key"></i>Derived relationship</span></div>
   <div class="scroll"><svg viewBox="0 0 700 300" role="img" aria-label="Example graph: two engineering entities map to XMEAS6; observation observes signal and belongs to run; run has recorded command; derived temporal relationship">
    <defs><marker v-for="edge in [{id:'semantic',color:'#60a5fa'},{id:'historian',color:'#94a3b8'},{id:'derived',color:'#4ade80'}]" :key="edge.id" :id="'demo-arrow-'+edge.id" markerWidth="7" markerHeight="7" refX="7" refY="3.5" orient="auto"><path d="M0 0 L7 3.5 L0 7 Z" :fill="edge.color"/></marker></defs>
    <g fill="none" stroke-width="2">
     <g stroke="#60a5fa" marker-end="url(#demo-arrow-semantic)" :opacity="focus==='semantic'?1:.55"><path d="M110 56 L265 120"/><path d="M390 56 L335 120"/></g>
     <g stroke="#94a3b8" marker-end="url(#demo-arrow-historian)"><path d="M110 220 L235 151" :opacity="focus==='semantic'?1:.55"/><path d="M180 238 L525 151" :opacity="focus==='temporal'?1:.55"/><path d="M580 160 V220" :opacity="focus==='temporal'?1:.55"/></g>
    </g>
    <g fill="#15283d" stroke="#7292aa"><rect x="20" y="12" width="180" height="44" rx="7"/><rect x="300" y="12" width="180" height="44" rx="7"/><rect x="235" y="120" width="130" height="40" rx="7"/><rect x="525" y="120" width="110" height="40" rx="7"/><rect x="20" y="220" width="160" height="40" rx="7"/><rect x="510" y="220" width="140" height="40" rx="7"/></g>
    <g fill="#edf5ff" font-size="14" text-anchor="middle"><text x="110" y="39">DEXPI FI_106</text><text x="390" y="39">ECAD FI-1101</text><text x="300" y="145">XMEAS6</text><text x="580" y="145">Demo run</text><text x="100" y="245">Observation {{observation.time}} s</text><text x="580" y="245">Command 30 s</text></g>
    <g fill="currentColor" font-size="12"><text x="105" y="90">mapsToSignal</text><text x="365" y="90">mapsToSignal</text><text x="75" y="175">observesSignal</text><text x="355" y="205">belongsToRun</text><text x="585" y="190">hasRecorded</text><text x="585" y="204">Command</text></g>
    <path d="M100 260 V280 H580 V260" fill="none" stroke="#4ade80" stroke-width="2" stroke-dasharray="6 4" marker-end="url(#demo-arrow-derived)"/>
    <text x="340" y="295" fill="#4ade80" text-anchor="middle" font-size="13">Derived: {{interval}}</text>
   </svg></div>
   <div class="choices"><button type="button" :aria-pressed="focus==='semantic'" @click="focus='semantic'">Semantic path</button><button type="button" :aria-pressed="focus==='temporal'" @click="focus='temporal'">Temporal rule</button></div>
   <p v-if="focus==='semantic'">Observation → observesSignal → XMEAS6 ← mapsToSignal ← engineering entity. Example mapping provenance: GraphDB / OPCUAConnectivity (fixture only).</p>
   <p v-else>Same run: {{observation.run}}. Observation at {{observation.time}} s {{interval==='BEFORE'?'\u003c':'\u003e'}} command at {{command.time}} s. Derived {{relation(observation)}} from fixture timestamps. Equal-time observations are excluded from BEFORE and AFTER.</p>
   <h3>3. Historical Observations</h3>
   <p>Choose an observation below or in the selector to inspect its reasoning evidence.</p>
   <div class="scroll"><svg viewBox="0 0 700 255" role="img" aria-label="Synthetic historical values with selected temporal interval">
    <rect x="65" y="15" width="300" height="195" fill="#60a5fa" :opacity="interval==='BEFORE'?.17:.05"/>
    <rect x="365" y="15" width="300" height="195" fill="#4ade80" :opacity="interval==='AFTER'?.17:.05"/>
    <text x="215" y="38" text-anchor="middle" fill="#93c5fd" font-size="11">BEFORE</text>
    <text x="515" y="38" text-anchor="middle" fill="#86efac" font-size="11">AFTER</text>
    <text transform="translate(15 115) rotate(-90)" text-anchor="middle" fill="currentColor" font-size="12">Recorded value</text>
    <path d="M65 15 V210 H665" stroke="currentColor" fill="none"/>
    <line x1="365" x2="365" y1="15" y2="210" stroke="#f59e0b" stroke-dasharray="5 4"/>
    <text x="375" y="20" fill="currentColor" font-size="12">Command 30 s</text>
    <polyline :points="samples.map(s=>x(s.time)+','+y(s.value)).join(' ')" stroke="#38bdf8" stroke-width="2" fill="none"/>
    <g v-for="s in samples" :key="s.id"><circle :cx="x(s.time)" :cy="y(s.value)" :r="s.id===observation.id?8:4" :fill="s.id===observation.id?'#4ade80':'#38bdf8'"><title>{{s.time}} s · {{s.value}}</title></circle><text :x="x(s.time)" y="230" text-anchor="middle" fill="currentColor" font-size="12">{{s.time}}</text></g>
    <text x="365" y="250" text-anchor="middle" fill="currentColor" font-size="12">Simulation seconds</text>
    <text v-for="v in [70,80,90,100]" :key="v" x="55" :y="y(v)+4" text-anchor="end" fill="currentColor" font-size="12">{{v}}</text>
   </svg></div>
   <div class="choices"><button v-for="s in samples" :key="s.id" type="button" :disabled="relation(s)==='AT'" :aria-pressed="s.id===observation.id" @click="chooseSample(s.id)">{{s.time}} s · {{s.value}}</button></div>
   <div class="observation-detail"><div><small>Selected observation</small><strong>{{observation.id}}</strong></div><div><small>Recorded value (units unspecified)</small><strong>{{observation.value}}</strong></div><div><small>Observation / command time</small><strong>{{observation.time}} s / {{command.time}} s</strong></div><div><small>Time difference · {{interval}}</small><strong>{{observation.time>command.time?'+':''}}{{observation.time-command.time}} s</strong></div></div>
  </template>
 </section>
</template>
<style scoped>
.reasoning-demo{display:grid;gap:12px;padding:12px 0;min-width:0}.notice{border:1px solid #b45309;border-radius:8px;padding:12px}.choices{display:flex;flex-wrap:wrap;gap:8px}.choices button[aria-pressed=true]{outline:2px solid #4ade80}.scroll{overflow-x:auto}.scroll svg{display:block;width:100%;min-width:560px;max-height:340px}table{border-collapse:collapse;width:100%;font-size:13px}th,td{text-align:left;padding:8px;border-bottom:1px solid #334a62}h3,p{margin:0}select{padding:8px;background:#101820;color:white;border:1px solid #657b92;border-radius:6px}
.choices button,.entity-button{background:#172d42;color:#eaf4ff;border:1px solid #45627b;border-radius:7px;padding:8px 12px;font:inherit;cursor:pointer}.choices button[aria-pressed=true]{outline:none;background:#21505a;border-color:#55d3cd;color:#eaffff}.choices button:disabled{opacity:.5;cursor:not-allowed}.choices button:focus-visible,.entity-button:focus-visible{outline:2px solid #93c5fd;outline-offset:2px}.at-count{align-self:center;color:#a8bed4;font-size:13px}.legend{display:flex;flex-wrap:wrap;gap:16px;font-size:12px;color:#c7d9ea}.legend span{display:flex;align-items:center;gap:7px}.legend i{width:25px;border-top:2px solid}.legend .semantic-key{border-color:#60a5fa}.legend .historian-key{border-color:#94a3b8}.legend .derived-key{border-color:#4ade80;border-top-style:dashed}.observation-detail{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:12px;background:#101f30;border:1px solid #334a62;border-radius:8px;padding:12px}.observation-detail div{display:grid;gap:5px;overflow-wrap:anywhere}.observation-detail small{color:#a8bed4}.observation-detail strong{color:#eaf4ff}.reasoning-demo>.primary{justify-self:start}.scroll svg{max-height:400px}
</style>
