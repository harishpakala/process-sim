<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import EngineeringRdfGraph from './EngineeringRdfGraph.vue'
import { Factory, Search, Network, Package } from 'lucide-vue-next'
import { selectTriples, KG_TYPE, KG_VOCAB, localName, type Triple } from '../lib/sparql'
import AssetStatusKnowledgeGraph from './AssetStatusKnowledgeGraph.vue'

type AssetRecord = { id: string; fields: Record<string, string> }
const assetType = 'https://example.org/assetinventory/Asset'
const assetNS = 'https://example.org/assetinventory/'
const productNS = 'https://example.org/productcatalog/'
const productType = 'https://example.org/productcatalog/Product'
const statusKeys = ['ModelingStatus', 'SimulationStatus', 'MonitoringStatus', 'FaultInjectionStatus', 'FaultDetectionStatus']
const triples = ref<Triple[]>([])
const domainGraphOpen = ref(false)
const loading = ref(false)
const error = ref('')
const query = ref('')
const selectedId = ref('')
const detailTab = ref<'Status' | 'Knowledge Graph'>('Status')

const assets = computed<AssetRecord[]>(() => {
  const ids = [...new Set(triples.value.filter(t => t.predicate === KG_TYPE && t.object === assetType).map(t => t.subject))]
  return ids.map(id => {
    const fields: Record<string, string> = { AssetId: id }
    const own = triples.value.filter(t => t.subject === id)
    for (const t of own) {
      if (t.predicate.startsWith(assetNS)) {
        if (t.predicate === assetNS + 'hasProductReference') fields.ProductReference = t.object
        else if (t.predicate === assetNS + 'hasOperationalReference') fields.OperationalSignalIRI = t.object
        else if (t.predicate === assetNS + 'hasAssetInventoryStatus') fields.StatusReference = t.object
        else { const key = localName(t.predicate).replace(/^has/, ''); if (key !== 'AssetId') fields[key] = t.object }
      }
    }
    if (fields.StatusReference) {
      for (const t of triples.value.filter(t => t.subject === fields.StatusReference && (t.predicate.startsWith(assetNS) || t.predicate.startsWith(productNS)))) {
        fields[localName(t.predicate)] = t.object
      }
    }
    if (!fields.OperationalReference && fields.OperationalSignalIRI) fields.OperationalReference = localName(fields.OperationalSignalIRI)
    return { id, fields }
  }).sort((a, b) => (a.fields.EquipmentTag || a.id).localeCompare(b.fields.EquipmentTag || b.id))
})
const products = computed<Record<string, Record<string, string>>>(() => {
  const result: Record<string, Record<string, string>> = {}
  const ids = [...new Set(triples.value.filter(t => t.predicate === KG_TYPE && t.object === productType).map(t => t.subject))]
  for (const id of ids) {
    const fields: Record<string, string> = {}
    for (const t of triples.value.filter(t => t.subject === id && t.predicate.startsWith(KG_VOCAB))) fields[localName(t.predicate)] = t.object
    result[id] = fields
  }
  return result
})
async function load() {
  loading.value = true
  error.value = ''
  try {
    const data = await selectTriples(`SELECT ?s ?p ?o WHERE {
      GRAPH ?g {
        { ?s a <${assetType}> ; ?p ?o . }
        UNION { ?s a <${productType}> ; ?p ?o . }
        UNION { ?s <${productNS}hasManufacturerPartNumber> ?part ; ?p ?o . }
      }
    } LIMIT 20000`)
    triples.value = data
    if (!assets.value.length) error.value = 'No lifted Asset resources found. Check the AssetInventory named graph and SPARQL query.'
  } catch (e) {
    triples.value = []
    error.value = e instanceof Error ? e.message : 'Unable to query GraphDB AAS.'
  } finally {
    loading.value = false
  }
}
watch(assets, list => {
  if (!list.some(a => a.id === selectedId.value)) selectedId.value = list[0]?.id || ''
}, { immediate: true })
void load()
const filtered = computed(() => {
  const term = query.value.trim().toLowerCase()
  return assets.value.filter(a => [a.id, ...Object.values(a.fields)].join(' ').toLowerCase().includes(term))
})
const selected = computed(() => filtered.value.find(a => a.id === selectedId.value) ?? filtered.value[0] ?? null)
const productTypeCount = computed(() => new Set(assets.value.map(a => a.fields.ProductReference).filter(ref => ref && products.value[ref])).size)
const signalCount = computed(() => assets.value.filter(a => a.fields.OperationalReference).length)
const readable = (s: string) => s.replace(/([a-z])([A-Z])/g, '$1 $2')
const statusLabel = (value: string) => readable(value || 'Unknown')
</script>
<template>
  <div class="graph-toolbar" style="display:flex;gap:8px;margin-bottom:12px"><button type="button" class="secondary" :aria-pressed="domainGraphOpen" @click="domainGraphOpen=!domainGraphOpen">{{ domainGraphOpen ? 'Show catalog details' : 'Domain Knowledge Graph' }}</button></div>
  <EngineeringRdfGraph v-if="domainGraphOpen" domain="assetinventory" />
  <template v-else>
 <section class="catalog asset-inventory">
  <p v-if="loading" role="status">Loading AssetInventory from GraphDB AAS…</p>
  <p v-if="error" role="alert" class="catalog-disclaimer">{{ error }} <button class="secondary" type="button" @click="load">Retry</button></p>
  <div class="metric-grid">
   <div class="metric"><Factory :size="18"/><small>ASSET INSTANCES</small><strong>{{ assets.length }}</strong></div>
   <div class="metric"><Network :size="18"/><small>OPERATIONAL SIGNALS</small><strong>{{ signalCount }}</strong></div>
   <div class="metric"><Package :size="18"/><small>PRODUCT TYPES</small><strong>{{ productTypeCount }}</strong></div>
  </div>
  <div class="catalog-layout">
   <section class="panel catalog-list">
    <div class="panel-title"><div><h2>Asset explorer</h2><p>GraphDB AAS · simulated engineering assets</p></div><span class="pill">{{ filtered.length }} / {{ assets.length }}</span></div>
    <label class="search"><Search :size="16"/><input v-model="query" aria-label="Search assets" placeholder="Search tags, signals, assets..."/></label>
    <button v-if="query" class="secondary" type="button" @click="query=''">Clear search</button>
    <div class="catalog-results">
     <button v-for="asset in filtered" :key="asset.id" class="asset-row catalog-item" :class="{highlight:selected?.id===asset.id}" @click="selectedId=asset.id;detailTab='Status'">
      <span class="asset-icon"><Factory :size="17"/></span><span><strong>{{ asset.fields.EquipmentTag || localName(asset.id) }}</strong><small>{{ asset.fields.AssetName || 'Unnamed simulated asset' }}</small><small>{{ asset.fields.AssetType || 'SimulatedAsset' }}</small></span>
     </button>
     <p v-if="!filtered.length && !loading" class="empty">No matching assets in the KG.</p>
    </div>
   </section>
   <section class="panel catalog-detail" v-if="selected">
    <div class="panel-title"><div><h2>{{ selected.fields.AssetName || localName(selected.id) }}</h2><p>{{ selected.fields.EquipmentTag || localName(selected.id) }} · {{ selected.fields.AssetType || 'SimulatedAsset' }}</p></div><span class="pill">KG ASSET</span></div>
    <div class="tabs"><button :class="{selected:detailTab==='Status'}" @click="detailTab='Status'">Asset status</button><button :class="{selected:detailTab==='Knowledge Graph'}" @click="detailTab='Knowledge Graph'">Knowledge graph</button></div>
    <AssetStatusKnowledgeGraph v-if="detailTab==='Knowledge Graph'" :key="selected.id" :asset="selected" />
    <template v-else>
     <h2 class="catalog-section-title">Asset status</h2>
     <div class="catalog-properties">
      <div v-for="key in statusKeys" :key="key" class="catalog-property"><span>{{ readable(key) }}</span><span>{{ statusLabel(selected.fields[key]) }}</span></div>
     </div>
     <h2 class="catalog-section-title">Product catalog</h2>
     <div class="catalog-properties" v-if="selected.fields.ProductReference && products[selected.fields.ProductReference]">
      <div class="catalog-property"><span>Manufacturer</span><span>{{ products[selected.fields.ProductReference].ManufacturerName || 'Not assigned' }}</span></div>
      <div class="catalog-property"><span>Part number</span><span>{{ products[selected.fields.ProductReference].ManufacturerPartNumber || 'Not assigned' }}</span></div>
      <div class="catalog-property"><span>Product RDF IRI</span><span class="catalog-wrap">{{ selected.fields.ProductReference }}</span></div>
     </div>
     <p v-else class="catalog-disclaimer">No matching product type is defined in the KG for this simulated asset.</p>
     <h2 class="catalog-section-title">Engineering & identification</h2>
     <div class="catalog-properties">
      <div v-for="(value,key) in Object.fromEntries(Object.entries(selected.fields).filter(([key]) => !statusKeys.includes(key)))" :key="key" class="catalog-property"><span>{{ readable(String(key)) }}</span><span class="catalog-wrap">{{ value || 'Not assigned' }}</span></div>
     </div>
     <p class="catalog-disclaimer">Engineering associations are RDF references, not evidence of verified physical installation. Simulation, monitoring and fault states are research placeholders unless runtime services update the KG.</p>
    </template>
   </section>
  </div>
  <p class="catalog-disclaimer">AssetInventory list, counters, statuses, product references and KG visualization are queried from GraphDB repository AAS. No bundled AAS JSON fallback; real-time synchronization is not implemented.</p>
 </section>
  </template>
</template>
