<script setup lang="ts">
import { computed, ref } from 'vue'
import { Factory, Search, Network, Package } from 'lucide-vue-next'
import inventory from '../data/asset_inventory.json'
import catalog from '../data/product_catalog.json'
import AssetStatusKnowledgeGraph from './AssetStatusKnowledgeGraph.vue'
type Field = { idShort: string; value?: string; modelType?: string }
type Asset = { idShort: string; value: Field[] }
const assets = (inventory.submodelElements[0].value as Asset[]).map(asset => ({
  id: asset.idShort,
  fields: Object.fromEntries(asset.value.map(field => [field.idShort, field.value ?? ''])) as Record<string,string>
}))
const products = Object.fromEntries((catalog.submodelElements[0].value as Asset[]).map(product => { const fields = Object.fromEntries(product.value.filter(field => field.modelType === 'Property').map(field => [field.idShort, field.value ?? ''])) as Record<string,string>; return [fields.AssetIdentifier, fields] })) as Record<string,Record<string,string>>
const query = ref('')
const detailTab = ref<'Status' | 'Knowledge Graph'>('Status')
const selectedId = ref(assets[0]?.id ?? '')
const filtered = computed(() => {
 const term = query.value.trim().toLocaleLowerCase()
 return assets.filter(asset => [asset.id, ...Object.values(asset.fields)].join(' ').toLocaleLowerCase().includes(term))
})
const selected = computed(() => filtered.value.find(asset => asset.id === selectedId.value) ?? filtered.value[0])
const readable = (s: string) => s.replace(/([a-z])([A-Z])/g, '$1 $2')
const statusKeys = ['ModelingStatus', 'SimulationStatus', 'MonitoringStatus', 'FaultInjectionStatus', 'FaultDetectionStatus']
const statusLabel = (value: string) => readable(value || 'Unknown')
</script>
<template>
 <section class="catalog asset-inventory">
  <div class="metric-grid">
   <div class="metric"><Factory :size="18"/><small>ASSET INSTANCES</small><strong>{{ assets.length }}</strong></div>
   <div class="metric"><Network :size="18"/><small>OPERATIONAL SIGNALS</small><strong>{{ assets.filter(a => a.fields.OperationalReference).length }}</strong></div>
   <div class="metric"><Package :size="18"/><small>PRODUCT TYPES</small><strong>{{ new Set(assets.map(a => a.fields.ProductReference).filter(ref => ref && products[ref])).size }}</strong></div>
  </div>
  <div class="catalog-layout">
   <section class="panel catalog-list">
    <div class="panel-title"><div><h2>Asset explorer</h2><p>TEP asset-instance reference inventory</p></div><span class="pill">{{ filtered.length }} / {{ assets.length }}</span></div>
    <label class="search"><Search :size="16"/><input v-model="query" aria-label="Search assets" placeholder="Search tags, signals, assets..."/></label><button v-if="query" class="secondary" type="button" @click="query=''">Clear search</button>
    <div class="catalog-results">
     <button v-for="asset in filtered" :key="asset.id" class="asset-row catalog-item" :class="{highlight:selectedId===asset.id}" @click="selectedId=asset.id;detailTab='Status'">
      <span class="asset-icon"><Factory :size="17"/></span><span><strong>{{ asset.fields.EquipmentTag }}</strong><small>{{ asset.fields.AssetName }}</small><small>{{ asset.fields.AssetType }}</small></span>
     </button>
     <p v-if="!filtered.length" class="empty">No matching assets.</p>
    </div>
   </section>
   <section class="panel catalog-detail" v-if="selected">
    <div class="panel-title"><div><h2>{{ selected.fields.AssetName }}</h2><p>{{ selected.fields.EquipmentTag }} · {{ selected.fields.AssetType }}</p></div><span class="pill">AAS ASSET</span></div>
    <div class="tabs"><button :class="{selected:detailTab==='Status'}" @click="detailTab='Status'">Asset status</button><button :class="{selected:detailTab==='Knowledge Graph'}" @click="detailTab='Knowledge Graph'">Knowledge graph</button></div>
    <AssetStatusKnowledgeGraph v-if="detailTab==='Knowledge Graph'" :asset="selected" />
    <template v-else>
    <h2 class="catalog-section-title">Asset status</h2>
    <div class="catalog-properties">
     <div v-for="key in statusKeys" :key="key" class="catalog-property"><span>{{ readable(key) }}</span><span>{{ statusLabel(selected.fields[key]) }}</span></div>
    </div>
    <h2 class="catalog-section-title">Product catalog</h2>
    <div class="catalog-properties" v-if="selected.fields.ProductReference && products[selected.fields.ProductReference]">
     <div class="catalog-property"><span>Manufacturer</span><span>{{ products[selected.fields.ProductReference].ManufacturerName }}</span></div>
     <div class="catalog-property"><span>Part number</span><span>{{ products[selected.fields.ProductReference].ManufacturerPartNumber }}</span></div>
     <div class="catalog-property"><span>Product ID</span><span class="catalog-wrap">{{ selected.fields.ProductReference }}</span></div>
    </div>
    <p v-else class="catalog-disclaimer">No matching product type is defined for this simulated asset.</p>
    <h2 class="catalog-section-title">Engineering & identification</h2>
    <div class="catalog-properties">
     <div v-for="(value,key) in Object.fromEntries(Object.entries(selected.fields).filter(([key]) => !statusKeys.includes(key)))" :key="key" class="catalog-property"><span>{{ readable(String(key)) }}</span><span class="catalog-wrap">{{ value || 'Not assigned' }}</span></div>
    </div>
    <p class="catalog-disclaimer">Engineering reference: identifier of the matching DEXPI/ECAD engineering element, if verified. Operational reference: TEP signal ID. Engineering tags and descriptions use the project engineering tables where available; DEXPI-to-ECAD identity reconciliation is pending. Simulation, monitoring and fault statuses are placeholders until connected to runtime services.</p>
    </template>
   </section>
  </div>
  <p class="catalog-disclaimer">Offline AssetInventory prototype · engineering-defined positions and logical TEP signals · simulation and monitoring states are not connected to live runtime services.</p>
 </section>
</template>
