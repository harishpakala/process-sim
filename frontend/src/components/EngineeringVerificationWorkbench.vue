<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { engineeringRelationships } from '../data/engineeringRelationships'
import { engineeringReconciliation } from '../data/engineeringReconciliation'
import { engineeringBomItems } from '../data/engineeringBom'
type Decision = 'ACCEPTED_FUNCTIONAL_CORRESPONDENCE'|'REJECTED'|'NEEDS_EVIDENCE'
type EventRecord = {sequence:number;event_id:string;relationship_id:string;review_kind:string;decision:string;reviewer:string;evidence_reference:string;rationale:string;physical_parent:string;recorded_at:string;previous_hash:string;event_hash:string}
const events=ref<EventRecord[]>([])
const revisions=ref<{revisionId:string;createdAt:string;snapshotHash:string;integrityValid:boolean;snapshot:{physicalAssignments:{bomItemId:string;physicalParent:string;evidenceEventId:string}[]}}[]>([])
const revisionAuthor=ref('')
const revisionRationale=ref('')
const selectedEvidenceEvent=ref('')
const revisionFeedback=ref('')
const physicalCandidates=computed(()=>events.value.filter(e=>e.review_kind==='PHYSICAL_MEMBERSHIP'&&e.decision==='VERIFIED_PHYSICAL_MEMBERSHIP'&&events.value.filter(v=>v.relationship_id===e.relationship_id&&v.review_kind==='PHYSICAL_MEMBERSHIP').at(-1)?.event_id===e.event_id).map(e=>({event:e,item:engineeringBomItems.find(i=>i.SourceDomain==='ECAD'&&i.EngineeringReference===engineeringRelationships.find(r=>r.relationshipId===e.relationship_id)?.targetReference)})).filter(x=>x.item))
const selectedId=ref<string>(engineeringRelationships[0]?.relationshipId||'')
const filter=ref('ALL')
const reviewer=ref('')
const evidenceReference=ref('')
const notes=ref('')
const decision=ref<Decision>('NEEDS_EVIDENCE')
const reviewKind=ref('FUNCTIONAL_CORRESPONDENCE')
const physicalParent=ref('')
const installationEvidenceConfirmed=ref(false)
const feedback=ref('')
const busy=ref(false)
const connected=ref(false)
const integrity=ref('')
const selected=computed(()=>engineeringRelationships.find(r=>r.relationshipId===selectedId.value))
const history=(id:string)=>events.value.filter(e=>e.relationship_id===id)
const reviewFor=(id:string)=>[...history(id)].reverse().find(e=>e.review_kind==='FUNCTIONAL_CORRESPONDENCE')
const pending=computed(()=>engineeringRelationships.filter(r=>!reviewFor(r.relationshipId)).length)
const displayed=computed(()=>engineeringRelationships.filter(r=>filter.value==='ALL'||(reviewFor(r.relationshipId)?.decision||'PENDING_REVIEW')===filter.value))
const pair=computed(()=>engineeringReconciliation.find(p=>p.dexpiReference===selected.value?.sourceReference&&p.ecadReference===selected.value?.targetReference))
watch(selectedId,()=>{reviewer.value='';evidenceReference.value='';notes.value='';decision.value='NEEDS_EVIDENCE';reviewKind.value='FUNCTIONAL_CORRESPONDENCE';physicalParent.value='';installationEvidenceConfirmed.value=false;feedback.value=''})
async function refresh(){
 try{
  const response=await fetch('/api/engineering/reviews',{cache:'no-store'})
  if(!response.ok)throw Error('HTTP '+response.status)
  const data=await response.json()
  events.value=data.events
  integrity.value=data.integrity?.valid?'Valid hash chain':'INTEGRITY CHECK FAILED'
  connected.value=true
  const revisionResponse=await fetch('/api/engineering/physical-bom/revisions',{cache:'no-store'})
  if(revisionResponse.ok)revisions.value=(await revisionResponse.json()).revisions
 }catch(e){connected.value=false;feedback.value='Review API unavailable: '+String(e)}
}
onMounted(()=>{void refresh()})
async function save(){
 if(!selected.value||busy.value)return
 if(!reviewer.value.trim()||!notes.value.trim()||!evidenceReference.value.trim()){
  feedback.value='Reviewer, evidence reference and rationale are required.';return
 }
 busy.value=true
 try{
  const response=await fetch('/api/engineering/reviews',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({
   relationshipId:selected.value.relationshipId,reviewKind:reviewKind.value,
   decision:reviewKind.value==='FUNCTIONAL_CORRESPONDENCE'?decision.value:'VERIFIED_PHYSICAL_MEMBERSHIP',
   reviewer:reviewer.value,evidenceReference:evidenceReference.value,notes:notes.value,
   physicalParent:reviewKind.value==='PHYSICAL_MEMBERSHIP'?physicalParent.value:'',
   installationEvidenceConfirmed:installationEvidenceConfirmed.value
  })})
  const data=await response.json()
  if(!response.ok)throw Error(data.error||'HTTP '+response.status)
  await refresh()
  feedback.value='Append-only review event #'+data.event.sequence+' saved on server.'
  notes.value='';evidenceReference.value='';installationEvidenceConfirmed.value=false
 }catch(e){feedback.value='Save failed: '+String(e)}
 finally{busy.value=false}
}
async function promote(){
 const match=physicalCandidates.value.find(x=>x.event.event_id===selectedEvidenceEvent.value)
 if(!match?.item||!revisionAuthor.value.trim()||!revisionRationale.value.trim()){revisionFeedback.value='Select an approved installation event, author and rationale.';return}
 try{
  const response=await fetch('/api/engineering/physical-bom/revisions',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({author:revisionAuthor.value,rationale:revisionRationale.value,assignments:[{bomItemId:match.item.BOMItemId,evidenceEventId:match.event.event_id}]})})
  const result=await response.json()
  if(!response.ok)throw Error(result.error||'Promotion failed')
  revisionFeedback.value='Created immutable physical BOM overlay '+result.revisionId
  await refresh()
 }catch(e){revisionFeedback.value=String(e)}
}
function exportReviews(){
 const blob=new Blob([JSON.stringify({schemaVersion:2,events:events.value},null,2)],{type:'application/json'})
 const url=URL.createObjectURL(blob)
 const anchor=document.createElement('a')
 anchor.href=url;anchor.download='tep-engineering-review-audit.json';anchor.click()
 URL.revokeObjectURL(url)
}
</script>
<template>
 <section class="workbench">
  <p class="intro">Review DEXPI ↔ ECAD candidate correspondences. An accepted functional correspondence does <strong>not</strong> confirm device identity, installation, physical BOM parentage or quantity. Review events are appended to the server database and hash-linked for tamper detection. Reviewer names are self-declared because authentication is not enabled.</p>
  <div class="summary"><div><small>Candidate relationships</small><strong>{{engineeringRelationships.length}}</strong></div><div><small>Awaiting review</small><strong>{{pending}}</strong></div><div><small>Reviewed</small><strong>{{events.length}}</strong></div></div>
  <div class="toolbar">
   <label>Show <select v-model="filter"><option value="ALL">All relationships</option><option value="PENDING_REVIEW">Pending</option><option value="ACCEPTED_FUNCTIONAL_CORRESPONDENCE">Accepted functional</option><option value="REJECTED">Rejected</option><option value="NEEDS_EVIDENCE">Needs evidence</option></select></label>
   <button type="button" @click="exportReviews">Export review JSON</button>
   <button type="button" @click="refresh">Refresh server history</button>
  </div>
  <p class="feedback">Server: {{connected?'Connected':'Unavailable'}} · Audit integrity: {{integrity||'Not checked'}}</p>
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
     <div><span>Equipment scope</span><strong>{{String(selected.scopeAssembly)==='ASM-ROOT'?'Plant-wide / not assigned to equipment':selected.scopeAssembly}}</strong></div>
     <div><span>Evidence basis</span><strong>{{selected.evidence.description}}</strong></div>
     <div><span>Physical membership</span><strong>Not verified</strong></div>
     <div><span>Same installed device</span><strong>Not verified</strong></div>
     <div v-if="reviewFor(selected.relationshipId)"><span>Last functional review</span><strong>{{reviewFor(selected.relationshipId)?.recorded_at}}</strong></div>
    </div>
    <form @submit.prevent="save">
     <label>Review type <select v-model="reviewKind"><option value="FUNCTIONAL_CORRESPONDENCE">Functional correspondence</option><option value="PHYSICAL_MEMBERSHIP">Physical installation evidence</option></select></label>
     <label v-if="reviewKind==='FUNCTIONAL_CORRESPONDENCE'">Review decision <select v-model="decision"><option value="NEEDS_EVIDENCE">Needs more evidence</option><option value="ACCEPTED_FUNCTIONAL_CORRESPONDENCE">Accept functional correspondence only</option><option value="REJECTED">Reject candidate</option></select></label>
     <template v-if="reviewKind==='PHYSICAL_MEMBERSHIP'"><label>Verified physical equipment parent <select v-model="physicalParent"><option value="">Select equipment</option><option v-for="assembly in ['ASM-REACTOR','ASM-SEPARATOR','ASM-STRIPPER','ASM-CONDENSER','ASM-COMPRESSOR']" :key="assembly" :value="assembly">{{assembly}}</option></select></label><label><input type="checkbox" v-model="installationEvidenceConfirmed" /> I have reviewed installation evidence supporting this physical membership</label><p class="feedback">Physical verification records a separate evidence-backed claim. It does not rewrite or merge canonical BOM items.</p></template>
     <label>Reviewer <input v-model="reviewer" placeholder="Engineer name or identifier" required /></label>
     <label>Evidence reference <input v-model="evidenceReference" placeholder="Drawing, document, revision or URL" required /></label>
     <label>Engineering rationale <textarea v-model="notes" rows="4" placeholder="Why this relationship is supported or rejected" required /></label>
     <button class="save" type="submit" :disabled="busy||!connected">Append review event</button>
     <p v-if="feedback" role="status" class="feedback">{{feedback}}</p>
    </form>
    <h2>Append-only decision history</h2><div v-for="event in history(selected.relationshipId)" :key="event.event_id" class="ebom-history"><strong>#{{event.sequence}} · {{event.review_kind}} · {{event.decision}}</strong><small>{{event.recorded_at}} · {{event.reviewer}} · {{event.evidence_reference}}</small><p>{{event.rationale}}</p><small>Hash: {{event.event_hash}}</small></div><p v-if="!history(selected.relationshipId).length" class="feedback">No recorded decisions.</p>
   </section>
  </div>
  <section class="panel revision-panel"><h2>Versioned physical BOM revisions</h2><p class="intro">Promote a specifically identified ECAD engineering object only after a physical installation review has been recorded. This creates an immutable overlay, not a change to the source BOM or a DEXPI–ECAD identity assertion.</p>
   <form @submit.prevent="promote"><label>Approved installation event <select v-model="selectedEvidenceEvent"><option value="">Select evidence-backed ECAD object</option><option v-for="candidate in physicalCandidates" :key="candidate.event.event_id" :value="candidate.event.event_id">{{candidate.item?.BOMItemId}} · {{candidate.event.physical_parent}} · #{{candidate.event.sequence}}</option></select></label><label>Revision author <input v-model="revisionAuthor" required placeholder="Engineering reviewer" /></label><label>Revision rationale <textarea v-model="revisionRationale" required rows="2" placeholder="Reason for physical BOM revision" /></label><button class="save" type="submit" :disabled="!connected||integrity!=='Valid hash chain'">Create immutable revision</button></form>
   <p class="feedback" role="status">{{revisionFeedback}}</p><div v-for="revision in revisions" :key="revision.revisionId" class="ebom-history"><strong>{{revision.revisionId}} · {{revision.integrityValid?'Integrity valid':'Integrity failed'}}</strong><small>{{revision.createdAt}} · {{revision.snapshotHash}}</small><p v-for="assignment in revision.snapshot.physicalAssignments" :key="assignment.bomItemId">{{assignment.bomItemId}} → {{assignment.physicalParent}} · Evidence {{assignment.evidenceEventId}}</p></div><p v-if="!revisions.length" class="feedback">No promoted physical BOM revisions yet.</p>
  </section>
 </section>
</template>

<style scoped>
.workbench{color:#d5e7f5}.intro{font-size:12px;line-height:1.7;color:#b4c7d9;margin:0 0 16px}.summary{display:grid;grid-template-columns:repeat(3,1fr);gap:12px;margin-bottom:16px}.summary>div,.panel{background:#132238;border:1px solid #294159;border-radius:12px}.summary>div{padding:16px;display:flex;flex-direction:column;gap:8px}.summary small,.relation small{font-size:11px;color:#98b1ca}.summary strong{font-size:23px}.toolbar{display:flex;gap:10px;flex-wrap:wrap;align-items:center;margin-bottom:16px}.toolbar label{font-size:12px}.toolbar button,.import,.save{background:#173b48;border:1px solid #3d8089;border-radius:8px;padding:10px;color:#8af0e8;cursor:pointer}.import input{display:block;margin-top:6px;max-width:220px;font-size:11px}.columns{display:grid;grid-template-columns:minmax(300px,1fr) minmax(0,1.25fr);gap:16px;align-items:start}.panel{min-width:0;padding:16px}.panel h2{font-size:15px;margin:0 0 15px}.list{max-height:680px;overflow:auto}.relation{display:flex;flex-direction:column;text-align:left;gap:6px;width:100%;border:0;border-top:1px solid #294159;padding:12px 8px;background:transparent;color:#d5e7f5;overflow-wrap:anywhere}.relation.active,.relation:hover{background:#194653}.relation strong{font-size:12px}.facts{border:1px solid #294159;border-radius:8px;overflow:hidden;margin-bottom:16px}.facts>div{display:grid;grid-template-columns:32% 1fr;gap:10px;padding:10px;border-bottom:1px solid #294159;font-size:11px;overflow-wrap:anywhere}.facts>div:last-child{border:0}.facts span{color:#98b1ca}.facts strong{font-weight:500}.detail form{display:flex;flex-direction:column;gap:12px}.detail form label{display:flex;flex-direction:column;gap:6px;font-size:12px}.detail input,.detail textarea,.detail select,.toolbar select{width:100%;box-sizing:border-box;background:#0c192a;border:1px solid #334a62;border-radius:8px;color:#eaf4ff;padding:10px;font-size:12px}.toolbar select{width:auto;margin-left:8px}.save{align-self:flex-start}.feedback,.empty{font-size:12px;color:#b4c7d9}@media(max-width:1000px){.columns{grid-template-columns:1fr}}@media(max-width:600px){.summary{grid-template-columns:1fr}.facts>div{grid-template-columns:1fr}}
.ebom-history{border-top:1px solid #294159;padding:12px 0;display:flex;flex-direction:column;gap:6px;overflow-wrap:anywhere}.ebom-history small{font-size:10px;color:#98b1ca}.ebom-history p{font-size:12px;margin:0}.detail input[type=checkbox]{width:auto;margin-right:8px}.save:disabled{opacity:.5;cursor:not-allowed}
.revision-panel{margin-top:16px}.revision-panel form{display:flex;flex-direction:column;gap:12px}.revision-panel label{display:flex;flex-direction:column;gap:6px;font-size:12px}.revision-panel select,.revision-panel input,.revision-panel textarea{background:#0c192a;border:1px solid #334a62;border-radius:8px;color:#eaf4ff;padding:10px;max-width:650px}.revision-panel button{align-self:flex-start}
</style>
