<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
type Element = { idShort: string; modelType: string; value?: unknown; [key: string]: unknown }
type Document = { id: string; idShort: string; submodelElements: Element[] }
type Result = { message_id: string; decision: string; committed: boolean; repository_version: number; triggered_policies: string[]; evaluated_contracts: {contract_id:string; verdict:string}[] }
const documents = ref<Document[]>([])
const version = ref<number|null>(null)
const selected = ref('')
const proposed = ref('')
const busy = ref(false)
const error = ref('')
const history = ref<Result[]>([])
const fields = computed(() => {
 const result: {key:string; document:Document; path:string; element:Element}[] = []
 for (const document of documents.value) {
  function walk(elements:Element[], prefix:string) {
   for (const element of elements) {
    const path = prefix ? prefix+'.'+element.idShort : element.idShort
    if (element.modelType==='SubmodelElementCollection' && Array.isArray(element.value)) walk(element.value as Element[],path)
    else if (element.modelType==='Property' && typeof element.value==='string' && element.valueType==='xs:string') result.push({key:document.id+'#'+path,document,path,element})
   }
  }
  walk(document.submodelElements||[],'')
 }
 return result
})
const field = computed(()=>fields.value.find(x=>x.key===selected.value))
function choose(){proposed.value=String(field.value?.element.value??'')}
async function load(){
 const response=await fetch('/api/governance/state')
 const data=await response.json()
 if(!response.ok) throw new Error(data.error||'State unavailable')
 documents.value=data.documents
 version.value=data.version
 if(!field.value) selected.value=fields.value[0]?.key||''
 choose()
}
async function refresh(){
 busy.value=true;error.value=''
 try{await load()}catch(e){version.value=null;error.value=String(e)}finally{busy.value=false}
}
async function submit(){
 if(!field.value||version.value===null||busy.value)return
 if(!window.confirm('Submit this change to the configured governed repository?'))return
 busy.value=true;error.value=''
 const f=field.value
 const message={header:{message_id:crypto.randomUUID(),source:'TEP-NEXUS-UI'},domain:{name:f.document.id==='https://example.org/sm/tep-product-catalog-instance'?'productcatalog':'assetinventory',submodel_id:f.document.id},operation:{type:'UPDATE',id_short_path:f.path,expected_version:version.value},payload:{...f.element,value:proposed.value}}
 try{
  const response=await fetch('/api/governance/change',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(message)})
  const data=await response.json()
  if(!response.ok)throw new Error(data.error||'Outcome unconfirmed')
  history.value.unshift(data as Result)
  await load()
 }catch(e){version.value=null;error.value=String(e)+' — refresh and verify state before another submission. Message: '+message.header.message_id}
 finally{busy.value=false}
}
onMounted(refresh)
</script>
<template>
 <section class="panel governance">
  <div class="panel-title"><div><h2>SELiRA Automation Manager</h2><p>Live native AAS changes · SC-01 · LP-01</p></div><span class="pill">Version {{version??'unavailable'}}</span></div>
  <p>Changes affect the configured repository. Evidence is supplied by the server operator.</p>
  <button class="secondary" :disabled="busy" @click="refresh">Refresh committed state</button>
  <p v-if="error" role="alert">{{error}}</p>
  <label>Native AAS property<select v-model="selected" :disabled="busy" @change="choose"><option v-for="f in fields" :key="f.key" :value="f.key">{{f.document.idShort}} / {{f.path}}</option></select></label>
  <label>Committed value<input :value="field?.element.value??''" readonly /></label>
  <label>Proposed value<input v-model="proposed" :disabled="busy" /></label>
  <button class="primary" :disabled="busy||version===null||!field||proposed===field.element.value" @click="submit">{{busy?'Processing…':'Submit native AAS change'}}</button>
  <h2>Governance responses</h2>
  <p v-if="!history.length">No changes submitted in this page session.</p>
  <article v-for="r in history" :key="r.message_id" class="response">
   <strong>{{r.decision}} · {{r.committed?'Committed':'Not confirmed committed'}}</strong>
   <p>Repository version: {{r.repository_version}} · Policies: {{r.triggered_policies.join(', ')||'None'}}</p>
   <p v-for="c in r.evaluated_contracts" :key="c.contract_id">{{c.contract_id}}: {{c.verdict}}</p>
   <small>{{r.message_id}}</small>
  </article>
 </section>
</template>
<style scoped>
.governance{display:grid;gap:16px}.governance label{display:grid;gap:6px}.governance select,.governance input{padding:10px;border:1px solid #8794a3;border-radius:6px;max-width:100%;color:inherit;background:transparent}.response{border-top:1px solid #8794a3;padding:12px 0;overflow-wrap:anywhere}.governance button{justify-self:start}
</style>
