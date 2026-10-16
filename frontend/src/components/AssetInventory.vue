<script setup lang="ts">
import { computed, ref } from 'vue'
import { Factory, Search, Network, Database } from 'lucide-vue-next'
import inventory from '../data/asset_inventory.json'
type Field = { idShort: string; value?: string }
type Asset = { idShort: string; value: Field[] }
const assets = (inventory.submodelElements[0].value as Asset[]).map(asset => ({
  id: asset.idShort,
  fields: Object.fromEntries(asset.value.map(field => [field.idShort, field.value ?? ''])) as Record<string,string>
}))
const query = ref('')
const selectedId = ref(assets[0]?.id ?? '')
const filtered = computed(() => assets.filter(asset => Object.values(asset.fields).join(' ').toLowerCase().includes(query.value.toLowerCase())))
const selected = computed(() => assets.find(asset => asset.id === selectedId.value))
const readable = (s: string) => s.replace(/([a-z])([A-Z])/g, '$1 $2')
</script>
<template>
 <section class="catalog">
  <div class="metric-grid">
   <div class="metric"><Factory :size="18"/><small>ASSET INSTANCES</small><strong>{{ assets.length }}</strong></div>
   <div class="metric"><Network :size="18"/><small>OPERATIONAL SIGNALS</small><strong>{{ assets.filter(a => a.fields.OperationalReference).length }}</strong></div>
   <div class="metric"><Database :size="18"/><small>DATA SOURCE</small><strong>AAS JSON snapshot</strong></div>
  </div>
  <div class="catalog-layout">
   <section class="panel catalog-list">
    <div class="panel-title"><div><h2>Asset explorer</h2><p>TEP asset-instance reference inventory</p></div><span class="pill">{{ filtered.length }} / {{ assets.length }}</span></div>
    <label class="search"><Search :size="16"/><input v-model="query" aria-label="Search assets" placeholder="Search tags, signals, assets..."/></label>
    <div class="catalog-results">
     <button v-for="asset in filtered" :key="asset.id" class="asset-row catalog-item" :class="{highlight:selectedId===asset.id}" @click="selectedId=asset.id">
      <span class="asset-icon"><Factory :size="17"/></span><span><strong>{{ asset.fields.EquipmentTag }}</strong><small>{{ asset.fields.AssetName }}</small><small>{{ asset.fields.AssetType }}</small></span>
     </button>
     <p v-if="!filtered.length" class="empty">No matching assets.</p>
    </div>
   </section>
   <section class="panel catalog-detail" v-if="selected">
    <div class="panel-title"><div><h2>{{ selected.fields.AssetName }}</h2><p>{{ selected.fields.EquipmentTag }} · {{ selected.fields.AssetType }}</p></div><span class="pill">AAS ASSET</span></div>
    <div class="catalog-properties">
     <div v-for="(value,key) in selected.fields" :key="key" class="catalog-property"><span>{{ readable(String(key)) }}</span><span class="catalog-wrap">{{ value || 'Not assigned' }}</span></div>
    </div>
    <p class="catalog-disclaimer">Engineering and operational references are identifiers only; cross-domain identity resolution and live OPC UA verification are pending.</p>
   </section>
  </div>
  <p class="catalog-disclaimer">Offline AssetInventory prototype · synthetic TEP asset identities · not a verified physical plant inventory or live GraphDB view.</p>
 </section>
</template>
