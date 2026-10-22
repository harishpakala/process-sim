<script setup lang="ts">
import { computed, ref } from 'vue'
import { engineeringBomItems, engineeringBomAssemblies } from '../data/engineeringBom'
const emit=defineEmits<{(e:'open-record',destination:string,identifier:string):void}>()
type Item={ParentItemId:string;ItemType:string;BOMPosition:string;QuantityPerAssembly:string;StructureStatus:string;BOMItemId:string;SourceDomain:string;SourceGroup:string;EngineeringReference:string;EngineeringLocalId:string;ItemDescription:string;Quantity:string;Unit:string;QuantityBasis:string;AssetReference:string;CandidateProductReference:string;SelectionStatus:string;Revision:string;ValidationStatus:string;EquivalenceStatus:string}
const items:Item[]=engineeringBomItems.map(entry=>({...entry}))
const assemblies=engineeringBomAssemblies.map(a=>({...a}))
const expanded=ref<string[]>(['ASM-ROOT','ASM-REACTOR','ASM-CONDENSER','ASM-SEPARATOR','ASM-COMPRESSOR','ASM-STRIPPER','ASM-UNASSIGNED'])
const tree= computed(()=>{const nodes=[...assemblies,...items];const matching=new Set(filtered.value.map(i=>i.BOMItemId));const ancestors=new Set(matching);for(const id of matching){let node=nodes.find(n=>n.BOMItemId===id);while(node?.ParentItemId){ancestors.add(node.ParentItemId);node=nodes.find(n=>n.BOMItemId===node?.ParentItemId)}}const result:{node:typeof nodes[number];depth:number}[]=[];const walk=(parent:string,depth:number)=>{for(const node of nodes.filter(n=>n.ParentItemId===parent && ancestors.has(n.BOMItemId))){result.push({node,depth});if(expanded.value.includes(node.BOMItemId))walk(node.BOMItemId,depth+1)}};walk('',0);return result})
function toggle(id:string){expanded.value=expanded.value.includes(id)?expanded.value.filter(x=>x!==id):[...expanded.value,id]}
const search=ref('')
const domain=ref('All')
const selectedId=ref(items[0]?.BOMItemId||'')
const filtered=computed(()=>items.filter(item=>(domain.value==='All'||item.SourceDomain===domain.value)&&Object.values(item).join(' ').toLowerCase().includes(search.value.toLowerCase())))
const selected=computed(()=>items.find(item=>item.BOMItemId===selectedId.value))
const matched=computed(()=>items.filter(item=>item.AssetReference).length)
</script>
<template>
<section class="catalog">
 <div class="metric-grid">
  <div class="metric"><small>ENGINEERING BOM LINES</small><strong>{{items.length}}</strong></div>
  <div class="metric"><small>DEXPI / ECAD</small><strong>{{items.filter(i=>i.SourceDomain==='DEXPI').length}} / {{items.filter(i=>i.SourceDomain==='ECAD').length}}</strong></div>
  <div class="metric"><small>EXACT ASSET MATCHES</small><strong>{{matched}}</strong></div>
  <div class="metric"><small>UNRESOLVED REFERENCES</small><strong>{{items.length-matched}}</strong></div>
 </div>
 <p class="catalog-disclaimer">Assembly tree now uses named equipment assemblies. Only the matching DEXPI equipment objects are assigned to them; 74 other engineering objects remain unassigned until component membership is verified. Mechanical, instrumentation and electrical subassemblies are not yet evidenced. Engineering model inventory, not an approved procurement or manufacturing BOM. Quantity 1 means one source engineering object. Cross-domain device equivalence has not been assessed; DEXPI and ECAD items may represent the same intended component.</p>
 <div class="catalog-layout">
  <section class="panel catalog-list">
   <div class="panel-title"><h2>Engineering BOM</h2><span class="pill">{{filtered.length}} / {{items.length}}</span></div>
   <label class="search"><input v-model="search" aria-label="Search EBOM" placeholder="Search tags, source IDs, items…"/></label>
   <label class="catalog-filter">Source domain <select v-model="domain" aria-label="Filter source domain"><option>All</option><option>DEXPI</option><option>ECAD</option></select></label>
   <div class="catalog-results">
    <div v-for="entry in tree" :key="entry.node.BOMItemId" class="asset-row catalog-item" :style="{paddingLeft:(8+entry.depth*16)+'px'}">
     <button v-if="entry.node.ItemType==='ASSEMBLY'" type="button" class="secondary" @click="toggle(entry.node.BOMItemId)">{{expanded.includes(entry.node.BOMItemId)?'▾':'▸'}} {{entry.node.ItemDescription}} <small>({{entry.node.BOMItemId}})</small></button>
     <button v-else type="button" class="secondary" :class="{highlight:selectedId===entry.node.BOMItemId}" @click="selectedId=entry.node.BOMItemId">{{entry.node.BOMItemId}} · {{entry.node.ItemDescription}}</button>
    </div>
    <p v-if="!filtered.length" class="empty">No matching EBOM items.</p>
   </div>
  </section>
  <section v-if="selected" class="panel catalog-detail">
   <div class="panel-title"><div><h2>{{selected.ItemDescription}}</h2><p>{{selected.BOMItemId}} · {{selected.SourceDomain}} / {{selected.SourceGroup}}</p></div><span class="pill">{{selected.ValidationStatus}}</span></div>
   <div class="catalog-properties">
    <div class="catalog-property"><span>Parent assembly</span><strong>{{selected.ParentItemId}} · {{selected.StructureStatus}}</strong></div>
    <div class="catalog-property"><span>BOM position</span><strong>{{selected.BOMPosition}}</strong></div>
    <div class="catalog-property"><span>Engineering ID</span><strong>{{selected.EngineeringLocalId}}</strong></div>
    <div class="catalog-property"><span>Source reference</span><button class="secondary" type="button" @click="emit('open-record',selected.SourceDomain==='DEXPI'?'DEXPI Explorer':'ECAD Explorer',selected.EngineeringReference)">{{selected.EngineeringReference}} ↗</button></div>
    <div class="catalog-property"><span>Quantity</span><strong>{{selected.Quantity}} {{selected.Unit}} (modeled object)</strong></div>
    <div class="catalog-property"><span>Asset Inventory</span><button v-if="selected.AssetReference" class="secondary" type="button" @click="emit('open-record','Asset Inventory',selected.AssetReference)">{{selected.AssetReference}} ↗</button><span v-else>Unresolved — no exact reference match</span></div>
    <div class="catalog-property"><span>Candidate product</span><button v-if="selected.CandidateProductReference" class="secondary" type="button" @click="emit('open-record','Product Catalog',selected.CandidateProductReference)">{{selected.CandidateProductReference}} ↗</button><span v-else>Not selected</span></div>
    <div class="catalog-property"><span>Selection status</span><strong>{{selected.SelectionStatus}}</strong></div>
    <div class="catalog-property"><span>Revision</span><span>{{selected.Revision}}</span></div>
    <div class="catalog-property"><span>Cross-domain equivalence</span><span>{{selected.EquivalenceStatus}}</span></div>
   </div>
  </section>
 </div>
 <p class="catalog-disclaimer">This view reads the versioned EBOM AAS instance bundled at build time. RDF publication is handled separately by the existing semantic importer.</p>
</section>
</template>
