<script setup lang="ts">
import { computed, ref } from 'vue'
import bom from '../../../examples/aas/tep_engineering_bom_instance.json'
const emit=defineEmits<{(e:'open-record',destination:string,identifier:string):void}>()
type Item={BOMItemId:string;SourceDomain:string;SourceGroup:string;EngineeringReference:string;EngineeringLocalId:string;ItemDescription:string;Quantity:string;Unit:string;QuantityBasis:string;AssetReference:string;CandidateProductReference:string;SelectionStatus:string;Revision:string;ValidationStatus:string;EquivalenceStatus:string}
const items:Item[]=bom.submodelElements[0].value.map(entry=>Object.fromEntries(entry.value.map(p=>[p.idShort,p.value])) as Item)
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
 <p class="catalog-disclaimer">Engineering model inventory, not an approved procurement or manufacturing BOM. Quantity 1 means one source engineering object. Cross-domain device equivalence has not been assessed; DEXPI and ECAD items may represent the same intended component.</p>
 <div class="catalog-layout">
  <section class="panel catalog-list">
   <div class="panel-title"><h2>Engineering BOM</h2><span class="pill">{{filtered.length}} / {{items.length}}</span></div>
   <label class="search"><input v-model="search" aria-label="Search EBOM" placeholder="Search tags, source IDs, items…"/></label>
   <label class="catalog-filter">Source domain <select v-model="domain" aria-label="Filter source domain"><option>All</option><option>DEXPI</option><option>ECAD</option></select></label>
   <div class="catalog-results">
    <button v-for="item in filtered" :key="item.BOMItemId" class="asset-row catalog-item" :class="{highlight:selectedId===item.BOMItemId}" @click="selectedId=item.BOMItemId">
     <span><strong>{{item.BOMItemId}} · {{item.EngineeringLocalId}}</strong><small>{{item.ItemDescription}} · {{item.SourceDomain}}</small><small>{{item.ValidationStatus}}</small></span>
    </button>
    <p v-if="!filtered.length" class="empty">No matching EBOM items.</p>
   </div>
  </section>
  <section v-if="selected" class="panel catalog-detail">
   <div class="panel-title"><div><h2>{{selected.ItemDescription}}</h2><p>{{selected.BOMItemId}} · {{selected.SourceDomain}} / {{selected.SourceGroup}}</p></div><span class="pill">{{selected.ValidationStatus}}</span></div>
   <div class="catalog-properties">
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
