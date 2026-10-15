<script setup lang="ts">
import { computed, ref } from 'vue'
import { Network, RotateCcw } from 'lucide-vue-next'

type Property = { name: string; value: string }
const props = defineProps<{ product: { id: string; manufacturer: string; partNumber: string; category: string; assetId: string; properties: Property[] } }>()
type NodeKind = 'product' | 'manufacturer' | 'category' | 'property'
type GraphNode = { id: string; label: string; kind: NodeKind; detail: string; x: number; y: number }
const showProperties = ref(true)
const showManufacturer = ref(true)
const showCategory = ref(true)
const activeNode = ref('product')
const showAll = ref(false)
const graph = computed(() => {
  const nodes: GraphNode[] = [{ id: 'product', label: props.product.partNumber, kind: 'product', detail: props.product.id, x: 310, y: 225 }]
  if (showManufacturer.value) nodes.push({ id: 'manufacturer', label: props.product.manufacturer, kind: 'manufacturer', detail: 'ManufacturerName', x: 135, y: 80 })
  if (showCategory.value) nodes.push({ id: 'category', label: props.product.category, kind: 'category', detail: 'ProductCategory', x: 485, y: 80 })
  if (showProperties.value) {
    const technical = props.product.properties.filter(p => p.name !== 'ProductCategory' && !/source|url|datasheet|documentation/i.test(p.name))
    const visible = showAll.value ? technical : technical.slice(0, 8)
    visible.forEach((p, i) => {
      const x = visible.length === 1 ? 310 : 65 + (490 * i / (visible.length - 1))
      nodes.push({ id: 'property:' + p.name, label: p.name.replace(/([a-z0-9])([A-Z])/g, '$1 $2'), kind: 'property', detail: p.value, x, y: 350 + (i % 2) * 58 })
    })
  }
  return nodes
})
const selected = computed(() => graph.value.find(node => node.id === activeNode.value) ?? graph.value[0])
const totalProperties = computed(() => props.product.properties.filter(p => p.name !== 'ProductCategory' && !/source|url|datasheet|documentation/i.test(p.name)).length)
function reset() { showProperties.value = true; showManufacturer.value = true; showCategory.value = true; showAll.value = false; activeNode.value = 'product' }
</script>

<template>
  <div class="product-knowledge">
    <div class="graph-toolbar">
      <span class="pill amber-pill">AAS-derived preview · not GraphDB</span>
      <button class="secondary" @click="reset"><RotateCcw :size="14"/> Reset</button>
    </div>
    <p class="graph-explanation">Explore relationships derived directly from this product's AAS fields. No external semantic links are inferred.</p>
    <div class="graph-filters">
      <label><input v-model="showManufacturer" type="checkbox"/> Manufacturer</label>
      <label><input v-model="showCategory" type="checkbox"/> Category</label>
      <label><input v-model="showProperties" type="checkbox"/> Technical properties</label>
      <label v-if="totalProperties > 8 && showProperties"><input v-model="showAll" type="checkbox"/> All {{ totalProperties }} properties</label>
    </div>
    <div class="graph-canvas" role="group" :aria-label="'Knowledge graph preview for ' + product.partNumber">
      <svg viewBox="0 0 620 485" class="product-graph-svg" role="img" :aria-label="'AAS-derived relationships for ' + product.partNumber">
        <g v-for="node in graph.filter(n => n.id !== 'product')" :key="'edge:' + node.id">
          <line x1="310" y1="225" :x2="node.x" :y2="node.y" stroke="#4d7f98" stroke-width="1.7"/>
        </g>
        <g v-for="node in graph" :key="node.id" tabindex="0" role="button" :aria-label="node.kind + ': ' + node.label" @click="activeNode=node.id" @keydown.enter.prevent="activeNode=node.id" @keydown.space.prevent="activeNode=node.id" class="graph-node" :class="{ 'graph-node-active': selected.id === node.id }">
          <rect :x="node.x-(node.kind==='product'?82:68)" :y="node.y-23" :width="node.kind==='product'?164:136" height="46" rx="10" :class="'graph-node-'+node.kind"/>
          <text :x="node.x" :y="node.y-3" text-anchor="middle" font-size="11" font-weight="600" fill="#effaff">{{ node.label.length > 19 ? node.label.slice(0, 18) + '…' : node.label }}</text>
          <text :x="node.x" :y="node.y+12" text-anchor="middle" font-size="9" fill="#b4d2e0">{{ node.kind === 'property' ? 'Technical property' : node.kind }}</text>
          <title>{{ node.label }}: {{ node.detail }}</title>
        </g>
      </svg>
    </div>
    <div class="graph-inspector" aria-live="polite">
      <div class="panel-title"><h2><Network :size="15"/> Selected node</h2><span class="pill">{{ selected.kind }}</span></div>
      <div class="catalog-property"><span>Name</span><strong class="catalog-wrap">{{ selected.label }}</strong></div>
      <div class="catalog-property"><span>{{ selected.kind === 'property' ? 'Value' : 'AAS field / identifier' }}</span><strong class="catalog-wrap">{{ selected.detail }}</strong></div>
    </div>
    <p class="catalog-disclaimer">Only attributes of the selected product are shown. This is an AAS snapshot visualization, not a queried RDF graph. GraphDB integration is pending.</p>
  </div>
</template>
