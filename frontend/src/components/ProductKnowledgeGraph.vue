<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { Network } from 'lucide-vue-next'
import { selectTriples, iri, localName, type Triple } from '../lib/sparql'

const props = defineProps<{ product: { uri: string; partNumber: string } }>()
const triples = ref<Triple[]>([])
const loading = ref(false)
const error = ref('')
const focused = ref('')
async function load() {
  loading.value = true
  error.value = ''
  triples.value = []
  try {
    const product = iri(props.product.uri)
    triples.value = await selectTriples(`SELECT ?s ?p ?o WHERE {
      GRAPH ?g {
        { VALUES ?s { ${product} } ?s ?p ?o }
        UNION {
          ${product} <https://example.org/productcatalog/hasTechnicalProperties> ?s .
          ?s ?p ?o .
        }
      }
    } LIMIT 500`)
    if (!triples.value.length) error.value = 'No triples found for this product in GraphDB AAS.'
    focused.value = props.product.uri
  } catch (e) { error.value = e instanceof Error ? e.message : 'Unable to query GraphDB.' }
  finally { loading.value = false }
}
watch(() => props.product.uri, load, { immediate: true })
const technicalPredicate = 'https://example.org/productcatalog/hasTechnicalProperties'
const technicalUris = computed(() => new Set(triples.value.filter(t =>
  t.subject === props.product.uri && t.predicate === technicalPredicate && t.resource
).map(t => t.object)))
const nodes = computed(() => {
  const ids = [props.product.uri, ...technicalUris.value]
  return ids.map((id, i) => ({
    id,
    label: id === props.product.uri ? props.product.partNumber : triples.value.find(t => t.subject === id && localName(t.predicate) === 'label')?.object || 'TechnicalProperties',
    kind: id === props.product.uri ? 'Product (SMC)' : 'TechnicalProperties (SMC)',
    x: 210 + i * 350, y: 280,
    attributes: triples.value.filter(t => t.subject === id && !t.resource).map(t => ({ name: localName(t.predicate).replace(/^has/, ''), value: t.object })),
  }))
})
const edges = computed(() => triples.value.filter(t =>
  t.subject === props.product.uri && t.predicate === technicalPredicate && t.resource
).map(t => ({from:t.subject,to:t.object,label:localName(t.predicate)})))
const selected = computed(() => nodes.value.find(n => n.id === focused.value) || nodes.value[0])
const node = (id: string) => nodes.value.find(n => n.id === id)
const connections = computed(() => edges.value.filter(e => e.from === selected.value?.id || e.to === selected.value?.id))
</script>

<template>
  <div class="product-knowledge">
    <div class="graph-toolbar"><span class="pill amber-pill">GraphDB AAS · SPARQL</span></div>
    <p class="graph-explanation">Product and TechnicalProperties collections are separate RDF nodes. Select either node to inspect its semantically lifted properties.</p>
    <p v-if="loading" role="status">Querying GraphDB…</p>
    <p v-if="error" role="alert" class="catalog-disclaimer">{{ error }} <button class="secondary" type="button" @click="load">Retry</button></p>
    <div v-if="!loading && !error" class="graph-workspace">
      <div class="graph-canvas graph-rdf-scroll" role="group" :aria-label="'Product Knowledge Graph for ' + product.partNumber">
        <svg viewBox="0 0 800 650" width="100%" height="100%" role="img" class="graph-pan-svg">
          <defs><marker id="product-kg-arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6" markerHeight="6" orient="auto"><path d="M0 0 L10 5 L0 10z" fill="#598fa8"/></marker></defs>
          <g v-for="e in edges" :key="e.from+e.to">
            <template v-if="node(e.from) && node(e.to)">
              <line :x1="node(e.from)!.x" :y1="node(e.from)!.y" :x2="node(e.to)!.x" :y2="node(e.to)!.y" stroke="#598fa8" stroke-width="2" marker-end="url(#product-kg-arrow)"/>
              <text :x="(node(e.from)!.x+node(e.to)!.x)/2" :y="(node(e.from)!.y+node(e.to)!.y)/2-12" text-anchor="middle" font-size="11" fill="#8edbd9" stroke="#0b1829" stroke-width="3" paint-order="stroke">{{ e.label }}</text>
            </template>
          </g>
          <g v-for="n in nodes" :key="n.id" class="graph-node graph-rdf-node" :class="{'graph-node-active':selected?.id===n.id}" tabindex="0" role="button" :aria-label="n.kind+': '+n.label" @click="focused=n.id" @keydown.enter.prevent="focused=n.id" @keydown.space.prevent="focused=n.id">
            <circle :cx="n.x" :cy="n.y" r="64" class="graph-rdf-resource"/>
            <text :x="n.x" :y="n.y-5" fill="#effaff" text-anchor="middle" font-size="11" font-weight="600" pointer-events="none">{{ n.label.length>19?n.label.slice(0,18)+'…':n.label }}</text>
            <text :x="n.x" :y="n.y+13" fill="#b5d5e2" text-anchor="middle" font-size="10" pointer-events="none">{{ n.kind }}</text>
            <title>{{ n.id }}</title>
          </g>
        </svg>
      </div>
      <aside v-if="selected" class="graph-sidepane" aria-live="polite">
        <div class="panel-title"><h2><Network :size="15"/> Node properties</h2><span class="pill">{{ selected.kind }}</span></div>
        <div class="graph-sidepane-heading"><strong class="catalog-wrap">{{ selected.label }}</strong><small>{{ selected.id }}</small></div>
        <div v-for="attribute in selected.attributes" :key="attribute.name+attribute.value" class="graph-attribute"><small>{{ attribute.name }}</small><strong class="catalog-wrap">{{ attribute.value }}</strong></div>
        <h2 class="catalog-section-title">Relationships <span class="pill muted">{{ connections.length }}</span></h2>
        <div v-for="e in connections" :key="e.from+e.to" class="graph-relationship"><small>{{ e.label }}</small><button type="button" @click="focused=e.from===selected.id?e.to:e.from">{{ node(e.from===selected.id?e.to:e.from)?.label }}</button></div>
      </aside>
    </div>
    <p class="catalog-disclaimer">KG query results only. No live device or AAS synchronization is implied.</p>
  </div>
</template>
