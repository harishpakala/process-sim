<script setup lang="ts">
import { computed, ref } from 'vue'
import { Network, RotateCcw, ZoomIn, ZoomOut } from 'lucide-vue-next'
import catalog from '../data/product_catalog.json'

type AasElement = { idShort: string; modelType: string; value?: string | AasElement[] }
type Attribute = { predicate: string; value: string }
type GraphNode = { id: string; label: string; kind: string; x: number; y: number; attributes: Attribute[] }
type GraphEdge = { from: string; to: string; predicate: string }
const props = defineProps<{ product: { id: string; partNumber: string } }>()
const raw = catalog.submodelElements[0].value as unknown as AasElement[]
const nodes = ref<GraphNode[]>([])
const edges = ref<GraphEdge[]>([])
const focused = ref('')
const zoom = ref(1)
const allProducts = ref(false)
const dragging = ref<{ id: string; x: number; y: number } | null>(null)
const get = (id: string) => nodes.value.find(n => n.id === id)
const selected = computed(() => get(focused.value))
const connections = computed(() => edges.value.filter(e => e.from === focused.value || e.to === focused.value))
function node(id: string, label: string, kind: string, x: number, y: number, attributes: Attribute[] = []) {
  if (!get(id)) nodes.value.push({ id, label, kind, x, y, attributes })
}
function edge(from: string, to: string, predicate: string) {
  if (!edges.value.some(e => e.from === from && e.to === to && e.predicate === predicate)) edges.value.push({ from, to, predicate })
}
function fieldsFor(id: string): AasElement[] {
  return (raw.find(p => p.idShort === id)?.value as AasElement[]) || []
}
function propertiesFor(id: string): AasElement[] {
  const collection = fieldsFor(id).find(f => f.idShort === 'TechnicalProperties')
  return (collection?.value as AasElement[]) || []
}
function expand(id: string) {
  if (!get(id)) return
  if (id === 'catalog') {
    node('products', 'Products', 'Collection', 320, 290, [{ predicate: 'rdf:type', value: 'SubmodelElementCollection' }])
    edge('catalog', 'products', 'hasProducts')
  } else if (id === 'products') {
    const ids = allProducts.value ? raw.map(p => p.idShort) : [props.product.id]
    ids.forEach((pid, i) => {
      const fields = fieldsFor(pid)
      const attributes: Attribute[] = [{ predicate: 'rdf:type', value: 'Product (AAS collection)' }]
      for (const field of fields) {
        if (typeof field.value === 'string') attributes.push({ predicate: 'has' + field.idShort, value: field.value })
      }
      node('p:' + pid, pid, 'Product', 570 + (i % 3) * 170, 170 + Math.floor(i / 3) * 175, attributes)
      edge('products', 'p:' + pid, 'hasProduct')
    })
  } else if (id.startsWith('p:') && !id.includes('/')) {
    const pid = id.slice(2)
    const technical = fieldsFor(pid).find(f => f.idShort === 'TechnicalProperties')
    if (technical) {
      const attributes: Attribute[] = [{ predicate: 'rdf:type', value: 'SubmodelElementCollection' }]
      node(id + '/TechnicalProperties', 'TechnicalProperties', 'Collection', 775, 450, attributes)
      edge(id, id + '/TechnicalProperties', 'hasTechnicalProperties')
    }
  } else if (id.endsWith('/TechnicalProperties')) {
    const pid = id.slice(2, -'/TechnicalProperties'.length)
    const properties = propertiesFor(pid)
    properties.forEach((property, i) => {
      const angle = i * Math.PI * 2 / Math.max(properties.length, 1)
      const key = id + '/' + property.idShort
      node(key, property.idShort, 'Property', 650 + Math.cos(angle) * 310, 365 + Math.sin(angle) * 255, [
        { predicate: 'rdf:type', value: property.modelType },
        { predicate: 'value', value: typeof property.value === 'string' ? property.value : '' }
      ])
      edge(id, key, 'hasProperty')
    })
  }
  focused.value = id
}
function reset() {
  nodes.value = []
  edges.value = []
  zoom.value = 1
  node('catalog', catalog.idShort || 'ProductCatalog', 'Submodel', 105, 290, [
    { predicate: 'rdf:type', value: 'Submodel' },
    { predicate: 'id', value: String(catalog.id) }
  ])
  expand('catalog')
  expand('products')
  expand('p:' + props.product.id)
  focused.value = 'p:' + props.product.id
}
function start(event: PointerEvent, n: GraphNode) {
  if (event.button !== 0) return
  dragging.value = { id: n.id, x: event.clientX, y: event.clientY }
  ;(event.currentTarget as Element).setPointerCapture(event.pointerId)
}
function move(event: PointerEvent) {
  if (!dragging.value) return
  const current = get(dragging.value.id)
  if (!current) return
  const svg = (event.currentTarget as SVGElement).ownerSVGElement
  const factor = 1100 / (svg?.getBoundingClientRect().width || 1100)
  current.x = Math.max(60, Math.min(1040, current.x + (event.clientX - dragging.value.x) * factor))
  current.y = Math.max(50, Math.min(690, current.y + (event.clientY - dragging.value.y) * factor))
  dragging.value.x = event.clientX
  dragging.value.y = event.clientY
}
reset()
</script>

<template>
  <div class="product-knowledge">
    <div class="graph-toolbar">
      <span class="pill amber-pill">GraphDB-style preview · AAS snapshot</span>
      <button class="secondary" @click="reset"><RotateCcw :size="14"/> Reset graph</button>
    </div>
    <p class="graph-explanation">Resource relationships appear as labeled edges. Scalar attributes such as hasAssetIdentifier are displayed in the selected node's side panel rather than as separate graph nodes. Labels are derived from AAS fields, not confirmed RDF predicates.</p>
    <div class="graph-filters">
      <label><input v-model="allProducts" type="checkbox" @change="reset"/> Show all eight products</label>
      <button class="secondary" aria-label="Zoom out" @click="zoom=Math.max(.6,+(zoom-.1).toFixed(1))"><ZoomOut :size="14"/></button>
      <span>{{ Math.round(zoom*100) }}%</span>
      <button class="secondary" aria-label="Zoom in" @click="zoom=Math.min(1.6,+(zoom+.1).toFixed(1))"><ZoomIn :size="14"/></button>
    </div>
    <div class="graph-workspace">
      <div class="graph-canvas graph-rdf-scroll" role="group" :aria-label="'ProductCatalog resource graph for ' + product.id">
        <svg viewBox="0 0 1100 740" :width="1100*zoom" :height="740*zoom" role="img">
          <defs><marker id="product-rdf-arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6" markerHeight="6" orient="auto"><path d="M0 0 L10 5 L0 10z" fill="#598fa8"/></marker></defs>
          <g v-for="e in edges" :key="e.from+'|'+e.to">
            <template v-if="get(e.from) && get(e.to)">
              <line :x1="get(e.from)!.x" :y1="get(e.from)!.y" :x2="get(e.to)!.x" :y2="get(e.to)!.y" stroke="#598fa8" stroke-width="1.5" marker-end="url(#product-rdf-arrow)"/>
              <text :x="(get(e.from)!.x+get(e.to)!.x)/2" :y="(get(e.from)!.y+get(e.to)!.y)/2-8" fill="#8edbd9" font-size="10" text-anchor="middle" stroke="#0b1829" stroke-width="3" paint-order="stroke">{{ e.predicate }}</text>
            </template>
          </g>
          <g v-for="n in nodes" :key="n.id" class="graph-node graph-rdf-node" :class="{'graph-node-active':focused===n.id}" tabindex="0" role="button" :aria-label="n.kind+': '+n.label" @click="expand(n.id)" @keydown.enter.prevent="expand(n.id)" @pointerdown="start($event,n)" @pointermove="move" @pointerup="dragging=null" @pointercancel="dragging=null">
            <circle :cx="n.x" :cy="n.y" r="46" class="graph-rdf-resource"/>
            <text :x="n.x" :y="n.y-3" fill="#effaff" text-anchor="middle" font-size="10" font-weight="600" pointer-events="none">{{ n.label.length>17?n.label.slice(0,16)+'…':n.label }}</text>
            <text :x="n.x" :y="n.y+12" fill="#b5d5e2" text-anchor="middle" font-size="9" pointer-events="none">{{ n.kind }}</text>
            <title>{{ n.label }}</title>
          </g>
        </svg>
      </div>
      <aside class="graph-sidepane" aria-live="polite">
        <div class="panel-title"><h2><Network :size="15"/> Node properties</h2><span v-if="selected" class="pill">{{ selected.kind }}</span></div>
        <template v-if="selected">
          <div class="graph-sidepane-heading"><strong class="catalog-wrap">{{ selected.label }}</strong><small>Selected resource</small></div>
          <div class="graph-attribute" v-for="(attribute, index) in selected.attributes" :key="attribute.predicate+index">
            <small>{{ attribute.predicate }}</small>
            <strong class="catalog-wrap">{{ attribute.value || '—' }}</strong>
          </div>
          <h2 class="catalog-section-title">Relationships <span class="pill muted">{{ connections.length }}</span></h2>
          <div v-for="e in connections" :key="e.from+e.to" class="graph-relationship">
            <small>{{ e.predicate }}</small>
            <button @click="focused=e.from===selected.id?e.to:e.from">{{ get(e.from===selected.id?e.to:e.from)?.label }}</button>
          </div>
          <p v-if="!selected.attributes.length" class="empty">No scalar attributes for this resource.</p>
        </template>
      </aside>
    </div>
    <p class="catalog-disclaimer">GraphDB-style local AAS visualization. Predicate labels and resource grouping are preview mappings; live RDF/SPARQL integration is not yet connected.</p>
  </div>
</template>
