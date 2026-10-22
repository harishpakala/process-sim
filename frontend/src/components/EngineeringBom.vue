<script setup lang="ts">
import { computed, ref } from 'vue'
import { engineeringBomItems, engineeringBomAssemblies } from '../data/engineeringBom'
import { engineeringReconciliation } from '../data/engineeringReconciliation'
const emit = defineEmits<{(e:'open-record', destination:string, identifier:string):void}>()
const items = engineeringBomItems.map(item => ({...item}))
const assemblies = engineeringBomAssemblies.map(item => ({...item}))
type BomItem = (typeof items)[number]
type Assembly = (typeof assemblies)[number]
type Node = { id:string; parent:string; title:string; type:'assembly'|'item'; assembly?:Assembly; item?:BomItem }
const displayParent = (item:BomItem):string => {
 if(!item.FunctionalAssemblyReference)return item.ParentItemId
 const tag=item.EngineeringLocalId
 const control=item.SourceGroup==='ActuatingFunctions'||/^(CV-|VC_|SC_|M[-_]?|M1$)/.test(tag)
 return item.FunctionalAssemblyReference+(control?'-CTRL':'-INST')
}
const nodes:Node[] = [
 ...assemblies.map(a => ({id:a.BOMItemId,parent:a.ParentItemId,title:a.ItemDescription,type:'assembly' as const,assembly:a})),
 ...items.map(i => ({id:i.BOMItemId,parent:displayParent(i),title:i.ItemDescription,type:'item' as const,item:i}))
]
const byId = new Map(nodes.map(n=>[n.id,n]))
const search = ref('')
const domain = ref('All')
const selectedId = ref('ASM-REACTOR')
const expanded = ref(new Set(['ASM-ROOT','ASM-REACTOR']))
const selected = computed(()=>byId.get(selectedId.value))
const matched = items.filter(i=>i.AssetReference).length
const filteredIds = computed(()=>{
 const term=search.value.trim().toLowerCase()
 return new Set(items.filter(i=>(domain.value==='All'||i.SourceDomain===domain.value)&&(!term||Object.values(i).some(v=>String(v).toLowerCase().includes(term)))).map(i=>i.BOMItemId))
})
const visible = computed(()=>{
 const allowed = new Set<string>(filteredIds.value)
 if(!search.value.trim() && domain.value==='All')for(const a of assemblies)allowed.add(a.BOMItemId)
 for(const id of filteredIds.value){
  let parent=byId.get(id)?.parent
  while(parent && !allowed.has(parent)){allowed.add(parent);parent=byId.get(parent)?.parent}
 }
 const result:{node:Node;depth:number}[]=[]
 const visit=(parent:string,depth:number)=>{
  for(const node of nodes.filter(n=>n.parent===parent&&allowed.has(n.id))){
   result.push({node,depth})
   if(node.type==='assembly' && (expanded.value.has(node.id)||!!search.value.trim()||domain.value!=='All'))visit(node.id,depth+1)
  }
 }
 visit('',0)
 return result
})
function select(node:Node){
 selectedId.value=node.id
 if(node.type==='assembly'){
  const next=new Set(expanded.value)
  next.has(node.id)?next.delete(node.id):next.add(node.id)
  expanded.value=next
 }
}
const related=(id:string)=>items.filter(i=>i.FunctionalAssemblyReference===id)
const candidatePairs=(id:string)=>engineeringReconciliation.filter(p=>p.equipmentAssembly===id)
const linkedPairs=(item:BomItem)=>engineeringReconciliation.filter(p=>item.EngineeringReference===p.dexpiReference||item.EngineeringReference===p.ecadReference)
const childCount=(id:string)=>items.filter(i=>i.ParentItemId===id&&!i.FunctionalAssemblyReference).length
const subassemblyCount=(id:string)=>assemblies.filter(a=>a.ParentItemId===id).length
</script>

<template>
 <section class="ebom">
  <div class="ebom-stats">
   <div><small>Engineering objects</small><strong>{{items.length}}</strong></div>
   <div><small>Equipment assemblies</small><strong>5</strong></div>
   <div><small>Exact asset references</small><strong>{{matched}}</strong></div>
   <div><small>Unassigned objects</small><strong>{{childCount('ASM-UNASSIGNED')}}</strong></div>
  </div>
  <p class="ebom-notice">Equipment-oriented EBOM preview. The five equipment objects are assigned to their named assemblies; instrument, actuator and electrical component membership is not verified. Source-described functional associations appear in each equipment inspector; they are not physical BOM assignments. Mechanical, instrumentation and electrical/control branches are empty placeholders under each equipment assembly. Only items without an equipment association appear in Unassigned. Functionally associated records are displayed under equipment discipline branches, without asserting physical membership. Quantities are modeled-object counts, not purchase quantities.</p>
  <div class="ebom-workspace">
   <section class="ebom-panel ebom-tree">
    <div class="ebom-panel-header"><h2>Assembly structure</h2><span>{{filteredIds.size}} objects</span></div>
    <div class="ebom-filters">
     <input v-model="search" aria-label="Search BOM items" placeholder="Search item, tag or identifier" />
     <select v-model="domain" aria-label="Filter source"><option>All</option><option>DEXPI</option><option>ECAD</option></select>
    </div>
    <div class="ebom-scroll" role="tree" aria-label="Engineering BOM assembly tree">
     <button v-for="entry in visible" :key="entry.node.id" class="ebom-node" :class="{active:selectedId===entry.node.id,assembly:entry.node.type==='assembly'}" :style="{paddingLeft:(12+entry.depth*18)+'px'}" role="treeitem" :aria-level="entry.depth+1" :aria-selected="selectedId===entry.node.id" :aria-expanded="entry.node.type==='assembly'?(expanded.has(entry.node.id)||!!search.trim()||domain!=='All'):undefined" @click="select(entry.node)">
      <span class="ebom-glyph">{{entry.node.type==='assembly'?(expanded.has(entry.node.id)||!!search.trim()||domain!=='All'?'▾':'▸'):'•'}}</span>
      <span class="ebom-node-text"><strong>{{entry.node.title}}</strong><small>{{entry.node.item?.EngineeringLocalId || entry.node.id }}{{entry.node.item?.FunctionalAssemblyReference ? ' · Functionally associated' : ''}}</small></span>
      <span v-if="entry.node.id==='ASM-UNASSIGNED'" class="ebom-count">{{childCount(entry.node.id)}}</span>
     </button>
     <p v-if="!visible.length" class="ebom-empty">No matching engineering items.</p>
    </div>
   </section>
   <section class="ebom-panel ebom-inspector">
    <template v-if="selected">
     <div class="ebom-panel-header"><h2>{{selected.title}}</h2><span>{{selected.type==='assembly'?'Assembly':'Engineering object'}}</span></div>
     <template v-if="selected.assembly">
      <p class="ebom-summary">Assembly identity: <strong>{{selected.id}}</strong></p>
      <div class="ebom-fields">
       <div><span>Parent</span><strong>{{selected.parent || 'Top level'}}</strong></div>
       <div><span>Assembly type</span><strong>{{selected.assembly.AssemblyKind}}</strong></div>
       <div><span>Direct engineering objects</span><strong>{{childCount(selected.id)}}</strong></div>
       <div><span>Subassemblies</span><strong>{{subassemblyCount(selected.id)}}</strong></div>
       <div><span>Structure status</span><strong>{{selected.assembly.StructureStatus}}</strong></div>
      </div>
      <div v-if="candidatePairs(selected.id).length" class="ebom-related">
       <h3>DEXPI ↔ ECAD candidate correspondences ({{candidatePairs(selected.id).length}})</h3>
       <p>Engineering function ↔ electrical device candidates. None are verified as identical physical components.</p>
       <div v-for="pair in candidatePairs(selected.id)" :key="pair.dexpiReference" class="ebom-pair">
        <strong>{{pair.dexpiLocalId}} ↔ {{pair.ecadLocalId}}</strong>
        <span>{{pair.dexpiIdShort}} ↔ {{pair.ecadDescription}}</span>
        <small>Candidate · Verification required</small>
       </div>
      </div>
      <div v-if="related(selected.id).length" class="ebom-related">
       <h3>Functionally associated instruments and devices ({{related(selected.id).length}})</h3>
       <p>Identified from DEXPI/ECAD descriptions; physical assembly membership is not verified.</p>
       <button v-for="item in related(selected.id)" :key="item.BOMItemId" @click="selectedId=item.BOMItemId">
        <strong>{{item.ItemDescription.replaceAll('_','-')}}</strong>
        <span>{{item.EngineeringLocalId}} · {{item.SourceDomain}}</span>
       </button>
      </div>
      <p class="ebom-hint">Select an engineering object in the tree to inspect its source references. These discipline branches are placeholders. Physical components, sensor assignments and quantities will be populated only when engineering evidence supports them.</p>
     </template>
     <template v-else-if="selected.item">
      <p class="ebom-summary">{{selected.item.BOMItemId}} · {{selected.item.SourceDomain}} / {{selected.item.SourceGroup}}</p>
      <div class="ebom-fields">
       <div><span>Engineering tag</span><strong>{{selected.item.EngineeringLocalId}}</strong></div>
       <div><span>Physical EBOM parent</span><strong>{{selected.item.ParentItemId}}</strong></div>
       <div><span>BOM position</span><strong>{{selected.item.BOMPosition}}</strong></div>
       <div><span>Quantity basis</span><strong>{{selected.item.Quantity}} {{selected.item.Unit}} · modeled object</strong></div>
       <div><span>Assignment status</span><strong>{{selected.item.StructureStatus}}</strong></div>
       <div><span>Functional association</span><strong>{{selected.item.FunctionalAssemblyReference || "Unresolved"}}</strong></div>
       <div><span>Association evidence</span><strong>{{selected.item.AssociationBasis}}</strong></div>
       <div><span>Asset reference</span><strong>{{selected.item.AssetReference || 'Unresolved'}}</strong></div>
       <div><span>Product selection</span><strong>{{selected.item.SelectionStatus}}</strong></div>
       <div><span>Revision</span><strong>{{selected.item.Revision}}</strong></div>
      </div>
      <div v-if="linkedPairs(selected.item).length" class="ebom-related">
       <h3>Cross-domain candidate correspondence</h3>
       <div v-for="pair in linkedPairs(selected.item)" :key="pair.dexpiReference" class="ebom-pair">
        <strong>{{pair.dexpiLocalId}} ↔ {{pair.ecadLocalId}}</strong>
        <span>{{pair.dexpiIdShort}} ↔ {{pair.ecadDescription}}</span>
        <small>Unverified candidate — not a merged BOM component</small>
       </div>
      </div>
      <div class="ebom-actions">
       <button @click="emit('open-record',selected.item!.SourceDomain==='DEXPI'?'DEXPI Explorer':'ECAD Explorer',selected.item!.EngineeringReference)">Open {{selected.item.SourceDomain}} source ↗</button>
       <button v-if="selected.item.AssetReference" @click="emit('open-record','Asset Inventory',selected.item!.AssetReference)">Open asset ↗</button>
       <button v-if="selected.item.CandidateProductReference" @click="emit('open-record','Product Catalog',selected.item!.CandidateProductReference)">Open candidate product ↗</button>
      </div>
      <p class="ebom-reference">{{selected.item.EngineeringReference}}</p>
     </template>
    </template>
   </section>
  </div>
 </section>
</template>

<style scoped>
.ebom{min-width:0}
.ebom-stats{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:12px;margin-bottom:16px}
.ebom-stats>div,.ebom-panel{background:#132238;border:1px solid #294159;border-radius:13px;min-width:0}
.ebom-stats>div{padding:16px;display:flex;flex-direction:column;gap:8px}
.ebom-stats small{font-size:11px;color:#98b1ca}
.ebom-stats strong{font-size:22px;color:#eaf4ff}
.ebom-notice{font-size:12px;line-height:1.6;margin:0 0 16px;color:#b4c7d9}
.ebom-workspace{display:grid;grid-template-columns:minmax(310px,1fr) minmax(0,1.2fr);gap:16px;align-items:start}
.ebom-panel{overflow:hidden}
.ebom-panel-header{display:flex;align-items:flex-start;justify-content:space-between;gap:12px;padding:17px;border-bottom:1px solid #294159}
.ebom-panel-header h2{font-size:15px;line-height:1.4;overflow-wrap:anywhere}
.ebom-panel-header>span{font-size:11px;color:#93b2c7;white-space:nowrap}
.ebom-filters{display:flex;gap:8px;padding:12px}
.ebom-filters input,.ebom-filters select{background:#0c192a;border:1px solid #334a62;border-radius:8px;color:#eaf4ff;padding:10px;min-width:0;font-size:12px}
.ebom-filters input{flex:1;width:0}
.ebom-scroll{max-height:620px;overflow:auto;padding:4px 8px 12px}
.ebom-node{width:100%;display:flex;align-items:center;gap:10px;text-align:left;border:0;border-radius:8px;padding:10px 12px;background:transparent;color:#d5e7f5;min-width:0}
.ebom-node:hover{background:#1a3248}
.ebom-node.active{background:#194653;outline:1px solid #397f88}
.ebom-node.assembly .ebom-node-text strong{font-weight:700}
.ebom-glyph{flex:0 0 14px;color:#69d5d2;text-align:center}
.ebom-node-text{display:flex;flex:1;min-width:0;flex-direction:column;gap:4px}
.ebom-node-text strong{font-size:12px;overflow-wrap:anywhere}
.ebom-node-text small{font-size:10px;color:#91abc4;overflow-wrap:anywhere}
.ebom-count{font-size:11px;color:#9fb8cb}
.ebom-summary,.ebom-hint{font-size:12px;padding:0 17px;margin:16px 0;color:#abc1d5}
.ebom-fields{margin:12px 17px;border:1px solid #294159;border-radius:9px;overflow:hidden}
.ebom-fields>div{display:grid;grid-template-columns:minmax(110px,35%) minmax(0,1fr);gap:12px;padding:12px;border-bottom:1px solid #294159;font-size:12px}
.ebom-fields>div:last-child{border-bottom:0}
.ebom-fields>div:nth-child(odd){background:#0e1c2f}
.ebom-fields span{color:#91abc4}
.ebom-fields strong{font-weight:500;overflow-wrap:anywhere;word-break:break-word}
.ebom-actions{display:flex;flex-wrap:wrap;gap:8px;padding:5px 17px}
.ebom-actions button{background:#173b48;border:1px solid #3d8089;color:#8af0e8;border-radius:8px;padding:9px 12px;font-size:12px}
.ebom-reference{font-size:11px;margin:12px 17px 18px;overflow-wrap:anywhere}
.ebom-related{margin:18px 17px;padding:13px;background:#0e1c2f;border:1px solid #294159;border-radius:9px}
.ebom-related h3{font-size:13px;margin:0 0 8px}
.ebom-related p{font-size:11px;margin:0 0 10px}
.ebom-related button{display:flex;flex-direction:column;align-items:flex-start;gap:4px;width:100%;padding:9px 6px;background:transparent;border:0;border-top:1px solid #294159;color:#d5e7f5;text-align:left}
.ebom-related button:hover{background:#1a3248}
.ebom-related button strong{font-size:12px}
.ebom-related button span{font-size:10px;color:#91abc4}
.ebom-pair{display:flex;flex-direction:column;gap:4px;padding:9px 6px;border-top:1px solid #294159;overflow-wrap:anywhere}
.ebom-pair strong{font-size:12px}
.ebom-pair span,.ebom-pair small{font-size:10px;color:#91abc4}
.ebom-empty{padding:16px;font-size:12px}
@media(max-width:1100px){.ebom-workspace{grid-template-columns:1fr}.ebom-scroll{max-height:380px}}
@media(max-width:700px){.ebom-stats{grid-template-columns:repeat(2,minmax(0,1fr))}.ebom-filters{flex-wrap:wrap}.ebom-filters input{flex-basis:100%;width:100%}.ebom-fields>div{grid-template-columns:1fr;gap:5px}}
</style>
