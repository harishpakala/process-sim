<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { engineeringRelationships } from '../data/engineeringRelationships'
import { engineeringReconciliation } from '../data/engineeringReconciliation'

type Decision = 'ACCEPTED_FUNCTIONAL_CORRESPONDENCE' | 'REJECTED' | 'NEEDS_EVIDENCE'
type Review = {relationshipId:string; decision:Decision; reviewer:string; evidenceReference:string; notes:string; reviewedAt:string}
type ReviewStore = {schemaVersion:1; reviews:Review[]}
const storageKey='tep-nexus-engineering-relationship-reviews-v1'
function load(): Review[] {
 try {
  const raw=localStorage.getItem(storageKey)
  if(!raw)return []
  const parsed:unknown=JSON.parse(raw)
  if(!parsed||typeof parsed!=='object'||!('reviews' in parsed)||!Array.isArray(parsed.reviews))return []
  const ids=new Set(engineeringRelationships.map(r=>r.relationshipId))
  return parsed.reviews.filter((r:unknown):r is Review=>{
   if(!r||typeof r!=='object')return false
   const x=r as Partial<Review>
   return typeof x.relationshipId==='string'&&ids.has(x.relationshipId)&&
    ['ACCEPTED_FUNCTIONAL_CORRESPONDENCE','REJECTED','NEEDS_EVIDENCE'].includes(x.decision||'')&&
    typeof x.reviewer==='string'&&typeof x.evidenceReference==='string'&&
    typeof x.notes==='string'&&typeof x.reviewedAt==='string'
  })
 } catch{return []}
}
const reviews=ref<Review[]>(load())
const selectedId=ref<string>(engineeringRelationships[0]?.relationshipId||'')
const filter=ref('ALL')
const reviewer=ref('')
const evidenceReference=ref('')
const notes=ref('')
const decision=ref<Decision>('NEEDS_EVIDENCE')
const feedback=ref('')
const selected=computed(()=>engineeringRelationships.find(r=>r.relationshipId===selectedId.value))
const reviewFor=(id:string)=>reviews.value.find(r=>r.relationshipId===id)
const pending=computed(()=>engineeringRelationships.filter(r=>!reviewFor(r.relationshipId)).length)
const displayed=computed(()=>engineeringRelationships.filter(r=>filter.value==='ALL'||(reviewFor(r.relationshipId)?.decision||'PENDING_REVIEW')===filter.value))
const pair=computed(()=>engineeringReconciliation.find(p=>p.dexpiReference===selected.value?.sourceReference&&p.ecadReference===selected.value?.targetReference))
watch(selectedId,id=>{
 const previous=reviewFor(id)
 reviewer.value=previous?.reviewer||''
 evidenceReference.value=previous?.evidenceReference||''
 notes.value=previous?.notes||''
 decision.value=previous?.decision||'NEEDS_EVIDENCE'
 feedback.value=''
})
function save(){
 if(!selected.value||!reviewer.value.trim()||!notes.value.trim()||!evidenceReference.value.trim()){
  feedback.value='Reviewer, evidence reference and rationale are required.'
  return
 }
 const record:Review={relationshipId:selected.value.relationshipId,decision:decision.value,reviewer:reviewer.value.trim(),evidenceReference:evidenceReference.value.trim(),notes:notes.value.trim(),reviewedAt:new Date().toISOString()}
 const updated=[...reviews.value.filter(r=>r.relationshipId!==record.relationshipId),record]
 try{
  localStorage.setItem(storageKey,JSON.stringify({schemaVersion:1,reviews:updated} satisfies ReviewStore))
  reviews.value=updated
  feedback.value='Review saved in this browser. Export it for a durable, shareable record.'
 }catch{feedback.value='Could not save the review in browser storage. Export or enable storage.'}
}
function exportReviews(){
 const payload:ReviewStore={schemaVersion:1,reviews:reviews.value}
 const blob=new Blob([JSON.stringify(payload,null,2)],{type:'application/json'})
 const url=URL.createObjectURL(blob)
 const anchor=document.createElement('a')
 anchor.href=url
 anchor.download='tep-engineering-relationship-reviews.json'
 anchor.click()
 URL.revokeObjectURL(url)
}
function importReviews(event:Event){
 const input=event.target as HTMLInputElement
 const file=input.files?.[0]
 if(!file)return
 const reader=new FileReader()
 reader.onload=()=>{
  try{
   const payload=JSON.parse(String(reader.result)) as ReviewStore
   if(payload.schemaVersion!==1||!Array.isArray(payload.reviews))throw Error('Unsupported review file')
   const ids=new Set(engineeringRelationships.map(r=>r.relationshipId))
   if(payload.reviews.some(r=>!ids.has(r.relationshipId)||!['ACCEPTED_FUNCTIONAL_CORRESPONDENCE','REJECTED','NEEDS_EVIDENCE'].includes(r.decision)||typeof r.reviewer!=='string'||!r.reviewer.trim()||typeof r.notes!=='string'||!r.notes.trim()||typeof r.evidenceReference!=='string'||!r.evidenceReference.trim()||typeof r.reviewedAt!=='string'))throw Error('Invalid review record')
   const merged=new Map(reviews.value.map(r=>[r.relationshipId,r]))
   for(const record of payload.reviews)merged.set(record.relationshipId,record)
   const next=[...merged.values()]
   localStorage.setItem(storageKey,JSON.stringify({schemaVersion:1,reviews:next}))
   reviews.value=next
   feedback.value='Review records imported and saved in this browser.'
  }catch(e){feedback.value=e instanceof Error?e.message:'Import failed'}
  input.value=''
 }
 reader.readAsText(file)
}
</script>

<template>
 <section class="workbench">
  <p class="intro">Review DEXPI ↔ ECAD candidate correspondences. An accepted functional correspondence does <strong>not</strong> confirm device identity, installation, physical BOM parentage or quantity. Review decisions are stored in this browser, not on the server; export them to preserve or share them.</p>
  <div class="summary"><div><small>Candidate relationships</small><strong>{{engineeringRelationships.length}}</strong></div><div><small>Awaiting review</small><strong>{{pending}}</strong></div><div><small>Reviewed</small><strong>{{reviews.length}}</strong></div></div>
  <div class="toolbar">
   <label>Show <select v-model="filter"><option value="ALL">All relationships</option><option value="PENDING_REVIEW">Pending</option><option value="ACCEPTED_FUNCTIONAL_CORRESPONDENCE">Accepted functional</option><option value="REJECTED">Rejected</option><option value="NEEDS_EVIDENCE">Needs evidence</option></select></label>
   <button type="button" @click="exportReviews">Export review JSON</button>
   <label class="import">Import review JSON <input type="file" accept=".json,application/json" @change="importReviews"/></label>
  </div>
  <div class="columns">
   <section class="panel list">
    <h2>Relationship registry</h2>
    <button v-for="relation in displayed" :key="relation.relationshipId" class="relation" :class="{active:selectedId===relation.relationshipId}" @click="selectedId=relation.relationshipId">
     <strong>{{relation.relationshipId}} · {{relation.evidence.dexpiFunction}} ↔ {{relation.evidence.ecadDevice}}</strong>
     <small>{{relation.scopeAssembly}} · {{reviewFor(relation.relationshipId)?.decision||'PENDING_REVIEW'}}</small>
    </button>
    <p v-if="!displayed.length" class="empty">No relationships match this filter.</p>
   </section>
   <section v-if="selected" class="panel detail">
    <h2>{{selected.relationshipId}} · Relationship review</h2>
    <div class="facts">
     <div><span>Relationship type</span><strong>{{selected.relationshipType}}</strong></div>
     <div><span>DEXPI function</span><strong>{{pair?.dexpiLocalId}} · {{selected.sourceReference}}</strong></div>
     <div><span>ECAD device</span><strong>{{pair?.ecadLocalId}} · {{selected.targetReference}}</strong></div>
     <div><span>Equipment scope</span><strong>{{selected.scopeAssembly==='ASM-ROOT'?'Plant-wide / not assigned to equipment':selected.scopeAssembly}}</strong></div>
     <div><span>Evidence basis</span><strong>{{selected.evidence.description}}</strong></div>
     <div><span>Physical membership</span><strong>Not verified</strong></div>
     <div><span>Same installed device</span><strong>Not verified</strong></div>
     <div v-if="reviewFor(selected.relationshipId)"><span>Last saved review</span><strong>{{reviewFor(selected.relationshipId)?.reviewedAt}}</strong></div>
    </div>
    <form @submit.prevent="save">
     <label>Review decision <select v-model="decision"><option value="NEEDS_EVIDENCE">Needs more evidence</option><option value="ACCEPTED_FUNCTIONAL_CORRESPONDENCE">Accept functional correspondence only</option><option value="REJECTED">Reject candidate</option></select></label>
     <label>Reviewer <input v-model="reviewer" placeholder="Engineer name or identifier" required /></label>
     <label>Evidence reference <input v-model="evidenceReference" placeholder="Drawing, document, revision or URL" required /></label>
     <label>Engineering rationale <textarea v-model="notes" rows="4" placeholder="Why this relationship is supported or rejected" required /></label>
     <button class="save" type="submit">Save review decision</button>
     <p v-if="feedback" role="status" class="feedback">{{feedback}}</p>
    </form>
   </section>
  </div>
 </section>
</template>

<style scoped>
.workbench{color:#d5e7f5}.intro{font-size:12px;line-height:1.7;color:#b4c7d9;margin:0 0 16px}.summary{display:grid;grid-template-columns:repeat(3,1fr);gap:12px;margin-bottom:16px}.summary>div,.panel{background:#132238;border:1px solid #294159;border-radius:12px}.summary>div{padding:16px;display:flex;flex-direction:column;gap:8px}.summary small,.relation small{font-size:11px;color:#98b1ca}.summary strong{font-size:23px}.toolbar{display:flex;gap:10px;flex-wrap:wrap;align-items:center;margin-bottom:16px}.toolbar label{font-size:12px}.toolbar button,.import,.save{background:#173b48;border:1px solid #3d8089;border-radius:8px;padding:10px;color:#8af0e8;cursor:pointer}.import input{display:block;margin-top:6px;max-width:220px;font-size:11px}.columns{display:grid;grid-template-columns:minmax(300px,1fr) minmax(0,1.25fr);gap:16px;align-items:start}.panel{min-width:0;padding:16px}.panel h2{font-size:15px;margin:0 0 15px}.list{max-height:680px;overflow:auto}.relation{display:flex;flex-direction:column;text-align:left;gap:6px;width:100%;border:0;border-top:1px solid #294159;padding:12px 8px;background:transparent;color:#d5e7f5;overflow-wrap:anywhere}.relation.active,.relation:hover{background:#194653}.relation strong{font-size:12px}.facts{border:1px solid #294159;border-radius:8px;overflow:hidden;margin-bottom:16px}.facts>div{display:grid;grid-template-columns:32% 1fr;gap:10px;padding:10px;border-bottom:1px solid #294159;font-size:11px;overflow-wrap:anywhere}.facts>div:last-child{border:0}.facts span{color:#98b1ca}.facts strong{font-weight:500}.detail form{display:flex;flex-direction:column;gap:12px}.detail form label{display:flex;flex-direction:column;gap:6px;font-size:12px}.detail input,.detail textarea,.detail select,.toolbar select{width:100%;box-sizing:border-box;background:#0c192a;border:1px solid #334a62;border-radius:8px;color:#eaf4ff;padding:10px;font-size:12px}.toolbar select{width:auto;margin-left:8px}.save{align-self:flex-start}.feedback,.empty{font-size:12px;color:#b4c7d9}@media(max-width:1000px){.columns{grid-template-columns:1fr}}@media(max-width:600px){.summary{grid-template-columns:1fr}.facts>div{grid-template-columns:1fr}}
</style>
