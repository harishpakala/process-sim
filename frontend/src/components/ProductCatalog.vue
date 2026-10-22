<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import EngineeringRdfGraph from './EngineeringRdfGraph.vue'
import { ExternalLink, Package, Search, Database, FileText } from 'lucide-vue-next'
import { selectTriples, localName, type Triple } from '../lib/sparql'
import ProductKnowledgeGraph from './ProductKnowledgeGraph.vue'

const props = withDefaults(defineProps<{ focusId?: string }>(), { focusId: '' })
const emit = defineEmits<{ (e:'open-record', destination:string, identifier:string):void }>()
type Product = { id: string; uri: string; manufacturer: string; partNumber: string; designation: string; supplierPartNumber: string; assetId: string; semanticId: string; eclassClass: string; eclassName: string; eclassIrdi: string; category: string; properties: { name: string; value: string }[] }
const triples = ref<Triple[]>([])
const domainGraphOpen = ref(false)
const loading = ref(false)
const error = ref('')
const query = ref('')
const manufacturer = ref('All')
const selectedId = ref('')
const tab = ref<'Details' | 'Knowledge Graph'>('Details')
const relatedAssets = ref<{id:string;tag:string;status:string}[]>([])
const productType = 'https://example.org/productcatalog/Product'
const productNS = 'https://example.org/productcatalog/'
const aasNS = 'https://example.org/aas/'
const catalogGraph = 'http://org.example.com/aHR0cHM6Ly9leGFtcGxlLm9yZy9zbS90ZXAtcHJvZHVjdC1jYXRhbG9nLWluc3RhbmNl/'
const products = computed<Product[]>(() => {
  const uris = [...new Set(triples.value.filter(t => t.predicate === productNS + 'hasAssetIdentifier').map(t => t.subject))]
  return uris.map(uri => {
    const own = triples.value.filter(t => t.subject === uri)
    const get = (key: string) => own.find(t => t.predicate === productNS + 'has' + key)?.object || ''
    const technicalUris = own.filter(t => t.predicate === productNS + 'hasTechnicalProperties' && t.resource).map(t => t.object)
    const technical = triples.value.filter(t => technicalUris.includes(t.subject) && t.predicate.startsWith(productNS) && !t.resource)
    const technicalGet = (key: string) => technical.find(t => t.predicate === productNS + 'has' + key)?.object || ''
    return {
      id: localName(uri), uri,
      manufacturer: get('ManufacturerName'), partNumber: get('ManufacturerPartNumber'), designation: get('ManufacturerProductDesignation'), supplierPartNumber: get('SupplierPartNumber'),
      assetId: get('AssetIdentifier'), semanticId: own.find(t => t.predicate === aasNS + 'semanticId')?.object || '', eclassClass: get('ECLASSClass'), eclassName: get('ECLASSPreferredName'), eclassIrdi: get('ECLASSIRDI'), category: technicalGet('ProductCategory') || 'Uncategorized',
      properties: technical.filter(t => t.predicate !== productNS + 'hasProductCategory').map(t => ({name:localName(t.predicate).replace(/^has/, ''),value:t.object})),
    }
  })
})
async function load() {
  loading.value = true
  error.value = ''
  try {
    triples.value = await selectTriples(`SELECT ?s ?p ?o WHERE { GRAPH <${catalogGraph}> { { ?s <${productNS}hasAssetIdentifier> ?asset ; ?p ?o . } UNION { ?product <${productNS}hasAssetIdentifier> ?asset ; <${productNS}hasTechnicalProperties> ?s . ?s ?p ?o . } } } LIMIT 5000`)
    if (!products.value.length) error.value = 'No lifted product resources found in the ProductCatalog named graph.'
  } catch (e) { triples.value = []; error.value = e instanceof Error ? e.message : 'Unable to query Knowledge Graph.' }
  finally { loading.value = false }
}
watch(products, items => { const focused=items.find(p=>p.assetId===props.focusId || p.uri===props.focusId || p.id===props.focusId)
  if(focused){selectedId.value=focused.id;query.value='';manufacturer.value='All';return}
  if (!items.some(p => p.id === selectedId.value)) selectedId.value = items[0]?.id || '' }, { immediate: true })
void load()
const manufacturers = computed(() => [...new Set(products.value.map(p => p.manufacturer).filter(Boolean))].sort())
const filtered = computed(() => products.value.filter(product => {
  const haystack = [product.id, product.manufacturer, product.partNumber, product.designation, product.supplierPartNumber, product.eclassClass, product.eclassName, product.eclassIrdi, product.category, ...product.properties.map(item => item.value)].join(' ').toLowerCase()
  return haystack.includes(query.value.trim().toLowerCase()) && (manufacturer.value === 'All' || product.manufacturer === manufacturer.value)
}))
const selected = computed(() => products.value.find(product => product.id === selectedId.value) ?? null)
watch(selected,async product=>{
 relatedAssets.value=[]
 if(!product)return
 try{
  const rows=await selectTriples(`SELECT ?s ?p ?o WHERE { GRAPH ?g { ?s <https://example.org/assetinventory/hasCandidateProductReference> <${product.assetId}> ; ?p ?o . } } LIMIT 200`)
  relatedAssets.value=[...new Set(rows.map(t=>t.subject))].map(id=>({id,tag:rows.find(t=>t.subject===id && t.predicate==='https://example.org/assetinventory/hasEquipmentTag')?.object||id,status:rows.find(t=>t.subject===id && t.predicate==='https://example.org/assetinventory/hasCandidateSelectionStatus')?.object||'PROVISIONAL'}))
 }catch { relatedAssets.value=[] }
},{immediate:true})
const sourceLinks = computed(() => selected.value?.properties.filter(item => /source|url|datasheet|documentation/i.test(item.name) && /^https?:\/\//i.test(item.value)) ?? [])
function label(value: string) { return value.replace(/([a-z0-9])([A-Z])/g, '$1 $2').replace(/_/g, ' ') }
</script>

<template>
  <div class="graph-toolbar" style="display:flex;gap:8px;margin-bottom:12px"><button type="button" class="secondary" :aria-pressed="domainGraphOpen" @click="domainGraphOpen=!domainGraphOpen">{{ domainGraphOpen ? 'Show catalog details' : 'Domain Knowledge Graph' }}</button></div>
  <EngineeringRdfGraph v-if="domainGraphOpen" domain="productcatalog" />
  <template v-else>
  <section class="catalog">
    <p v-if="loading" role="status">Loading products from GraphDB AAS…</p>
    <p v-if="error" role="alert" class="catalog-disclaimer">{{ error }} <button class="secondary" type="button" @click="load">Retry</button></p>
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
            <span class="asset-icon"><Package :size="17"/></span><span><strong>{{ product.partNumber || product.designation || product.supplierPartNumber || product.id }}</strong><small>{{ product.manufacturer }} · {{ product.category }}</small><small v-if="product.eclassClass">ECLASS {{ product.eclassClass }} · {{ product.eclassName }}</small><small class="catalog-id">{{ product.id }}</small></span>
          </button>
          <p v-if="!filtered.length" class="empty">No matching products. Try another search or manufacturer.</p>
        </div>
      </section>
      <section class="panel catalog-detail">
        <template v-if="selected">
          <div class="panel-title"><div><h2>{{ selected.partNumber || selected.designation || selected.supplierPartNumber || selected.id }}</h2><p>{{ selected.manufacturer }} · {{ selected.category }}</p></div><span class="pill">AAS PRODUCT</span></div>
          <div class="tabs"><button :class="{selected:tab==='Details'}" @click="tab='Details'">Technical details</button><button :class="{selected:tab==='Knowledge Graph'}" @click="tab='Knowledge Graph'">Knowledge graph</button></div>
          <template v-if="tab==='Details'">
            <div class="catalog-identifiers">
              <div><small>Manufacturer</small><strong>{{ selected.manufacturer }}</strong></div>
              <div><small>Manufacturer part number</small><strong>{{ selected.partNumber || 'Not verified' }}</strong></div>
              <div v-if="selected.supplierPartNumber"><small>Supplier part number</small><strong>{{ selected.supplierPartNumber }}</strong></div>
              <div><small>AAS collection ID</small><strong>{{ selected.id }}</strong></div>
              <div><small>Product asset identifier</small><strong class="catalog-wrap">{{ selected.assetId }}</strong></div>
              <div><small>Referenced by AssetInventory</small><div v-if="relatedAssets.length"><button v-for="asset in relatedAssets" :key="asset.id" class="secondary" type="button" @click="emit('open-record','Asset Inventory',asset.id)">{{ asset.tag }} ↗ ({{ asset.status }})</button></div><strong v-else>No linked assets found</strong></div>
              <div><small>ECLASS class</small><strong>{{ selected.eclassClass || '—' }}</strong></div>
              <div><small>ECLASS preferred name</small><strong>{{ selected.eclassName || '—' }}</strong></div>
              <div><small>AAS Semantic ID</small><strong class="catalog-wrap">{{ selected.semanticId || 'Not present in lifted RDF' }}</strong></div>
              <div><small>ECLASS IRDI</small><strong class="catalog-wrap">{{ selected.eclassIrdi || '—' }}</strong></div>
              <div v-if="selected.semanticId && selected.eclassIrdi"><small>Semantic ID / ECLASS consistency</small><strong>{{ selected.semanticId === selected.eclassIrdi ? 'Match' : 'Mismatch — verify source and lifting' }}</strong></div>
            </div>
            <h2 class="catalog-section-title">Technical properties <span class="pill muted">{{ selected.properties.length }}</span></h2>
            <div class="catalog-properties">
              <div v-for="property in selected.properties" :key="property.name" class="catalog-property"><span>{{ label(property.name) }}</span><span class="catalog-wrap">{{ property.value || '—' }}</span></div>
            </div>
            <template v-if="sourceLinks.length"><h2 class="catalog-section-title">Documentation & provenance</h2><div class="catalog-links"><a v-for="link in sourceLinks" :key="link.name" :href="link.value" target="_blank" rel="noopener noreferrer"><ExternalLink :size="14"/> {{ label(link.name) }}</a></div></template>
          </template>
          <ProductKnowledgeGraph v-else :key="selected.uri" :product="selected" />
        </template>
        <div v-else class="placeholder"><Package :size="38"/><h2>No product selected</h2></div>
      </section>
    </div>
    <p class="catalog-disclaimer">ProductCatalog is queried from the GraphDB AAS RDF repository. This is a snapshot query, not live AAS synchronization.</p>
  </section>
  </template>
</template>
