<script setup lang="ts">
import { computed, ref } from 'vue'
import { ExternalLink, Package, Search, Database, Network, FileText } from 'lucide-vue-next'
import catalog from '../data/product_catalog.json'
import ProductKnowledgeGraph from './ProductKnowledgeGraph.vue'

type Element = { modelType: string; idShort: string; value?: string | Element[] }
type Product = { idShort: string; value: Element[] }
const products = (catalog.submodelElements[0].value as unknown as Product[]).map(product => {
  const field = (name: string) => product.value.find(item => item.idShort === name)?.value
  const properties = (field('TechnicalProperties') as Element[] | undefined) ?? []
  const property = (name: string) => String(properties.find(item => item.idShort === name)?.value ?? '')
  return {
    id: product.idShort,
    manufacturer: String(field('ManufacturerName') ?? ''),
    partNumber: String(field('ManufacturerPartNumber') ?? ''),
    assetId: String(field('AssetIdentifier') ?? ''),
    category: property('ProductCategory') || 'Uncategorized',
    properties: properties.map(item => ({ name: item.idShort, value: String(item.value ?? '') })),
  }
})
const query = ref('')
const manufacturer = ref('All')
const selectedId = ref(products[0]?.id ?? '')
const tab = ref<'Details' | 'Knowledge Graph'>('Details')
const manufacturers = [...new Set(products.map(product => product.manufacturer))].sort()
const filtered = computed(() => products.filter(product => {
  const haystack = [product.id, product.manufacturer, product.partNumber, product.category, ...product.properties.map(item => item.value)].join(' ').toLowerCase()
  return haystack.includes(query.value.trim().toLowerCase()) && (manufacturer.value === 'All' || product.manufacturer === manufacturer.value)
}))
const selected = computed(() => products.find(product => product.id === selectedId.value) ?? null)
const sourceLinks = computed(() => selected.value?.properties.filter(item => /source|url|datasheet|documentation/i.test(item.name) && /^https?:\/\//i.test(item.value)) ?? [])
function label(value: string) { return value.replace(/([a-z0-9])([A-Z])/g, '$1 $2').replace(/_/g, ' ') }
</script>

<template>
  <section class="catalog">
    <div class="metric-grid">
      <div class="metric"><Package :size="18"/><small>CATALOG PRODUCTS</small><strong>{{ products.length }}</strong></div>
      <div class="metric"><Database :size="18"/><small>MANUFACTURERS</small><strong>{{ manufacturers.length }}</strong></div>
      <div class="metric"><FileText :size="18"/><small>TECHNICAL PROPERTIES</small><strong>{{ products.reduce((sum, product) => sum + product.properties.length, 0) }}</strong></div>
      
    </div>
    <div class="catalog-layout">
      <section class="panel catalog-list">
        <div class="panel-title"><div><h2>Product explorer</h2><p>Manufacturer and engineering specifications</p></div><span class="pill">{{ filtered.length }} / {{ products.length }}</span></div>
        <label class="search"><Search :size="16"/><input v-model="query" aria-label="Search products" placeholder="Search products, part numbers, properties..."/></label>
        <label class="catalog-filter">Manufacturer
          <select v-model="manufacturer" aria-label="Filter by manufacturer"><option value="All">All manufacturers</option><option v-for="name in manufacturers" :key="name" :value="name">{{ name }}</option></select>
        </label>
        <div class="catalog-results">
          <button v-for="product in filtered" :key="product.id" class="asset-row catalog-item" :class="{ highlight: selectedId === product.id }" @click="selectedId=product.id;tab='Details'">
            <span class="asset-icon"><Package :size="17"/></span><span><strong>{{ product.partNumber }}</strong><small>{{ product.manufacturer }} · {{ product.category }}</small><small class="catalog-id">{{ product.id }}</small></span>
          </button>
          <p v-if="!filtered.length" class="empty">No matching products. Try another search or manufacturer.</p>
        </div>
      </section>
      <section class="panel catalog-detail">
        <template v-if="selected">
          <div class="panel-title"><div><h2>{{ selected.partNumber }}</h2><p>{{ selected.manufacturer }} · {{ selected.category }}</p></div><span class="pill">AAS PRODUCT</span></div>
          <div class="tabs"><button :class="{selected:tab==='Details'}" @click="tab='Details'">Technical details</button><button :class="{selected:tab==='Knowledge Graph'}" @click="tab='Knowledge Graph'">Knowledge graph</button></div>
          <template v-if="tab==='Details'">
            <div class="catalog-identifiers">
              <div><small>Manufacturer</small><strong>{{ selected.manufacturer }}</strong></div>
              <div><small>Part number</small><strong>{{ selected.partNumber }}</strong></div>
              <div><small>AAS collection ID</small><strong>{{ selected.id }}</strong></div>
              <div><small>Asset identifier</small><strong class="catalog-wrap">{{ selected.assetId }}</strong></div>
            </div>
            <h2 class="catalog-section-title">Technical properties <span class="pill muted">{{ selected.properties.length }}</span></h2>
            <div class="catalog-properties">
              <div v-for="property in selected.properties" :key="property.name" class="catalog-property"><span>{{ label(property.name) }}</span><span class="catalog-wrap">{{ property.value || '—' }}</span></div>
            </div>
            <template v-if="sourceLinks.length"><h2 class="catalog-section-title">Documentation & provenance</h2><div class="catalog-links"><a v-for="link in sourceLinks" :key="link.name" :href="link.value" target="_blank" rel="noopener noreferrer"><ExternalLink :size="14"/> {{ label(link.name) }}</a></div></template>
          </template>
          <ProductKnowledgeGraph v-else :key="selected.id" :product="selected" />
        </template>
        <div v-else class="placeholder"><Package :size="38"/><h2>No product selected</h2></div>
      </section>
    </div>
    <p class="catalog-disclaimer">Offline catalog preview · bundled from examples/aas/product_catalog_instance.json · GraphDB and live AAS synchronization are not connected.</p>
  </section>
</template>
