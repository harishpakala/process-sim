<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { ShieldCheck, Send, RefreshCw } from 'lucide-vue-next'

type AasElement = { modelType: string; idShort: string; valueType?: string; value?: unknown; [key: string]: unknown }
type AasDocument = { id: string; idShort: string; submodelElements?: AasElement[] }
type GovernanceState = { version: number; documents: AasDocument[]; templates: Record<string,AasDocument> }
type ChangeResult = { message_id: string; decision: 'ACCEPTED'|'REJECTED'|'DEFERRED'; committed: boolean; repository_version: number; triggered_policies: string[]; evaluated_contracts: {contract_id:string;verdict:string}[] }

const props = defineProps<{
  domain: 'assetinventory'|'productcatalog'
  identityValues: string[]
  title: string
}>()
const emit = defineEmits<{ (e:'committed'):void }>()
const state = ref<GovernanceState|null>(null)
const collectionPath = ref('')
const elements = ref<{path:string;element:AasElement}[]>([])
const selectedPath = ref('')
const editedValue = ref('')
const loading = ref(false)
const submitting = ref(false)
const error = ref('')
const result = ref<ChangeResult|null>(null)

const rootCollection = computed(()=>props.domain==='assetinventory'?'Assets':'Products')
const domainName = computed(()=>props.domain==='assetinventory'?'Asset Inventory':'Product Catalog')

function propertyMap(items:AasElement[], prefix:string, out:{path:string;element:AasElement}[]=[]){
  for(const item of items||[]){
    const path=prefix?prefix+'.'+item.idShort:item.idShort
    if(item.modelType==='Property')out.push({path,element:item})
    if(item.modelType==='SubmodelElementCollection'&&Array.isArray(item.value))propertyMap(item.value as AasElement[],path,out)
  }
  return out
}
function valuesOf(items:AasElement[]):string[]{
  const values:string[]=[]
  for(const item of items||[]){
    if(item.modelType==='Property' && typeof item.value==='string')values.push(item.value)
    if(item.modelType==='SubmodelElementCollection'&&Array.isArray(item.value))values.push(...valuesOf(item.value as AasElement[]))
  }
  return values
}
function findRecord(document:AasDocument){
  const root=(document.submodelElements||[]).find(e=>e.idShort===rootCollection.value)
  if(!root||!Array.isArray(root.value))return null
  const targets=props.identityValues.filter(Boolean)
  const candidates=(root.value as AasElement[]).filter(e=>e.modelType==='SubmodelElementCollection')
  const scored=candidates.map(e=>({element:e,score:valuesOf([e]).filter(v=>targets.includes(v)).length}))
    .sort((a,b)=>b.score-a.score)
  if (!scored[0]?.score || (scored[1] && scored[1].score === scored[0].score)) return null
  return scored[0].element
}
async function refresh(clearResult = true){
  loading.value=true;error.value='';if(clearResult)result.value=null
  try{
    const response=await fetch('/api/governance/state')
    const payload=await response.json()
    if(!response.ok)throw new Error(payload.error||'SELiRA repository state unavailable')
    state.value=payload
    const expectedId=props.domain==='assetinventory'?'https://example.org/sm/tep-asset-inventory':'https://example.org/sm/tep-product-catalog-instance'
    const document=(payload.documents as AasDocument[]).find(d=>d.id===expectedId || d.idShort===(props.domain==='assetinventory'?'AssetInventory':'TEP_ProductCatalog'))
    if(!document)throw new Error('The selected engineering Submodel is not registered with SELiRA')
    const record=findRecord(document)
    if(!record)throw new Error('Could not resolve this Explorer record to a unique native AAS element. No change was submitted.')
    const template=payload.templates?.[document.id]
    if(!template)throw new Error('The registered Submodel template is unavailable; editing is disabled.')
    const templatePrefix=rootCollection.value+'.'+(props.domain==='assetinventory'?'Asset':'Product')+'.'
    const allowed=new Map(propertyMap(template.submodelElements||[],'')
      .filter(item=>item.path.startsWith(templatePrefix))
      .map(item=>[item.path.slice(templatePrefix.length),item.element]))
    collectionPath.value=rootCollection.value+'.'+record.idShort
    elements.value=propertyMap((record.value||[]) as AasElement[],collectionPath.value)
      .filter(item=>{
        const relative=item.path.slice(collectionPath.value.length+1)
        const definition=allowed.get(relative)
        return definition?.modelType==='Property' && item.element.modelType==='Property'
          && definition.valueType===item.element.valueType
      })
    if(!elements.value.length)throw new Error('No existing Property elements conforming to the registered AAS template were found for this record')
    selectedPath.value=elements.value[0].path
    editedValue.value=String(elements.value[0].element.value??'')
  }catch(e){error.value=e instanceof Error?e.message:String(e)}
  finally{loading.value=false}
}
watch(selectedPath,path=>{
  const found=elements.value.find(x=>x.path===path)
  editedValue.value=String(found?.element.value??'')
})
watch(()=>[props.domain,props.title,...props.identityValues],()=>{void refresh()})
onMounted(()=>{void refresh()})
const selectedElement=computed(()=>elements.value.find(x=>x.path===selectedPath.value)?.element||null)
async function submit(){
  if(!state.value||!selectedElement.value||submitting.value)return
  submitting.value=true;error.value='';result.value=null
  try{
    const original=selectedElement.value
    const payload={...original,value:editedValue.value}
    const response=await fetch('/api/governance/change',{
      method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({
        header:{message_id:crypto.randomUUID(),source:'TEP-NEXUS-Explorer',message_type:'InformationChangeProposed'},
        domain:{name:props.domain,submodel_id:(state.value.documents.find(d=>d.idShort===(props.domain==='assetinventory'?'AssetInventory':'TEP_ProductCatalog'))||{} as AasDocument).id},
        operation:{type:'UPDATE',id_short_path:selectedPath.value,expected_version:state.value.version},
        payload
      })
    })
    const data=await response.json()
    if(!response.ok)throw new Error(data.error||'SELiRA rejected the change request')
    result.value=data
    if(data.committed){await refresh(false);emit('committed')}
  }catch(e){error.value=e instanceof Error?e.message:String(e)}
  finally{submitting.value=false}
}
</script>

<template>
  <section class="aas-editor">
    <div class="aas-editor-heading">
      <div><h3><ShieldCheck :size="17"/> Propose an AAS change</h3><p>{{domainName}} · {{title}}</p></div>
      <button class="secondary" type="button" :disabled="loading||submitting" @click="() => refresh()"><RefreshCw :size="14"/> Refresh</button>
    </div>
    <p class="aas-editor-note">Changes are prepared as native AAS Submodel Elements and submitted to SELiRA. The repository is not modified directly by this editor.</p>
    <p v-if="loading" role="status">Resolving native AAS element…</p>
    <p v-if="error" class="catalog-disclaimer" role="alert">{{error}}</p>
    <template v-if="!loading&&elements.length">
      <label class="aas-editor-field">Engineering property
        <select v-model="selectedPath" :disabled="submitting">
          <option v-for="item in elements" :key="item.path" :value="item.path">{{item.path.replace(collectionPath+'.','')}}</option>
        </select>
      </label>
      <label class="aas-editor-field">Proposed value
        <input v-model="editedValue" :disabled="submitting" :type="selectedElement?.valueType==='xs:integer'||selectedElement?.valueType==='xs:double'||selectedElement?.valueType==='xs:float'?'number':'text'"/>
      </label>
      <div class="aas-editor-meta"><span>Submodel version: {{state?.version}}</span><span>{{selectedElement?.modelType}} · {{selectedElement?.valueType||'unspecified'}}</span></div>
      <button class="primary" type="button" :disabled="submitting||loading||editedValue===String(selectedElement?.value??'')" @click="submit"><Send :size="14"/> {{submitting?'Submitting to SELiRA…':'Submit change for qualification'}}</button>
    </template>
    <div v-if="result" class="aas-editor-result" :class="result.decision.toLowerCase()">
      <strong>{{result.decision}}</strong>
      <span>{{result.committed?'AAS change committed.':'No repository commitment was confirmed.'}}</span>
      <small>Message {{result.message_id}} · repository version {{result.repository_version}}</small>
      <small v-for="contract in result.evaluated_contracts" :key="contract.contract_id">{{contract.contract_id}} · {{contract.verdict}}</small>
    </div>
  </section>
</template>

<style scoped>
.aas-editor{margin-top:18px;padding:16px;border:1px solid var(--border,#d6dce3);border-radius:12px;background:var(--panel,#fff);display:grid;gap:12px}.aas-editor-heading{display:flex;align-items:center;justify-content:space-between;gap:12px}.aas-editor-heading h3{display:flex;align-items:center;gap:8px;margin:0;font-size:1rem}.aas-editor-heading p,.aas-editor-note{margin:4px 0 0;color:var(--muted,#64748b);font-size:.84rem}.aas-editor-field{display:grid;gap:6px;font-size:.86rem;font-weight:600}.aas-editor-field input,.aas-editor-field select{width:100%;padding:9px 11px;border:1px solid var(--border,#cbd5e1);border-radius:7px;background:var(--surface,#fff);color:inherit}.aas-editor-meta{display:flex;justify-content:space-between;gap:8px;flex-wrap:wrap;color:var(--muted,#64748b);font-size:.78rem}.aas-editor-result{display:grid;gap:4px;padding:12px;border-radius:8px;background:var(--surface-secondary,#f1f5f9)}.aas-editor-result.accepted{border-left:3px solid #16a34a}.aas-editor-result.rejected{border-left:3px solid #dc2626}.aas-editor-result.deferred{border-left:3px solid #d97706}.aas-editor-result small{overflow-wrap:anywhere}
</style>
