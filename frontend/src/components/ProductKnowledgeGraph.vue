<script setup lang="ts">
import { computed, ref } from 'vue'
import { Network, RotateCcw, ZoomIn, ZoomOut } from 'lucide-vue-next'
import catalog from '../data/product_catalog.json'

type AasElement = { idShort: string; modelType: string; value?: string | AasElement[] }
type TreeNode = { id: string; label: string; kind: string; value?: string; children: TreeNode[] }
type Positioned = TreeNode & { x: number; y: number; parent?: string }
const props = defineProps<{ product: { id: string; manufacturer: string; partNumber: string; category: string; assetId: string; properties: { name: string; value: string }[] } }>()
const rawProducts = catalog.submodelElements[0].value as unknown as AasElement[]
const expanded = ref<string[]>(['root', 'products', 'product:' + props.product.id, 'product:' + props.product.id + '/TechnicalProperties'])
const chosen = ref('product:' + props.product.id)
const scale = ref(1)
const allProducts = ref(false)
const showLiterals = ref(true)
const textLabel = (s: string) => s.replace(/([a-z0-9])([A-Z])/g, '$1 $2').replace(/_/g, ' ')
function makeTree(): TreeNode {
  const children = rawProducts.filter(p => allProducts.value || p.idShort === props.product.id).map(p => {
    const fields = (p.value as AasElement[]) || []
    return {
      id: 'product:' + p.idShort, label: p.idShort, kind: 'SubmodelElementCollection',
      children: fields.map(field => {
        const path = 'product:' + p.idShort + '/' + field.idShort
        const members = Array.isArray(field.value) ? field.value.map(child => ({
          id: path + '/' + child.idShort, label: child.idShort, kind: child.modelType,
          value: typeof child.value === 'string' ? child.value : undefined, children: [] as TreeNode[]
        })) : []
        return { id: path, label: field.idShort, kind: field.modelType, value: typeof field.value === 'string' ? field.value : undefined, children: members }
      })
    }
  })
  return { id: 'root', label: catalog.idShort || 'ProductCatalog', kind: 'Submodel', children: [
    { id: 'products', label: 'Products', kind: 'SubmodelElementCollection', children }
  ] }
}
const tree = computed(makeTree)
const positioned = computed(() => {
  const rows: Positioned[] = []
  const walk = (node: TreeNode, depth: number, parent?: string) => {
    const index = rows.length
    rows.push({ ...node, x: 30 + depth * 225, y: 35 + index * 61, parent })
    if (expanded.value.includes(node.id)) {
      for (const child of node.children) walk(child, depth + 1, node.id)
    }
  }
  walk(tree.value, 0)
  return rows
})
const canvasHeight = computed(() => Math.max(300, positioned.value.length * 61 + 30))
const canvasWidth = computed(() => Math.max(1050, (Math.max(...positioned.value.map(n => n.x), 0) + 220)))
const selected = computed(() => {
  const visit = (n: TreeNode): TreeNode | undefined => n.id === chosen.value ? n : n.children.map(visit).find(Boolean)
  return visit(tree.value) ?? tree.value
})
function toggle(node: TreeNode) {
  chosen.value = node.id
  if (!node.children.length) return
  expanded.value = expanded.value.includes(node.id) ? expanded.value.filter(x => x !== node.id) : [...expanded.value, node.id]
}
function reset() {
  allProducts.value = false
  showLiterals.value = true
  scale.value = 1
  chosen.value = 'product:' + props.product.id
  expanded.value = ['root', 'products', 'product:' + props.product.id, 'product:' + props.product.id + '/TechnicalProperties']
}
</script>

<template>
  <div class="product-knowledge">
    <div class="graph-toolbar">
      <span class="pill amber-pill">AAS hierarchy · local snapshot, not GraphDB</span>
      <button class="secondary" @click="reset"><RotateCcw :size="14"/> Reset</button>
    </div>
    <p class="graph-explanation">Explore the actual ProductCatalog submodel hierarchy. Click a node to inspect it and expand or collapse its children. Edges represent AAS containment, not inferred engineering links.</p>
    <div class="graph-filters">
      <label><input v-model="allProducts" type="checkbox" @change="expanded=['root','products','product:' + product.id,'product:' + product.id + '/TechnicalProperties']"/> Show all eight products</label>
      <label><input v-model="showLiterals" type="checkbox"/> Show property values</label>
      <button class="secondary" aria-label="Zoom out" @click="scale=Math.max(0.6, +(scale-0.1).toFixed(1))"><ZoomOut :size="14"/></button>
      <span class="graph-scale">{{ Math.round(scale*100) }}%</span>
      <button class="secondary" aria-label="Zoom in" @click="scale=Math.min(1.5, +(scale+0.1).toFixed(1))"><ZoomIn :size="14"/></button>
    </div>
    <div class="graph-canvas graph-tree-scroll" role="group" :aria-label="'AAS ProductCatalog hierarchy for ' + product.partNumber">
      <svg :viewBox="'0 0 ' + canvasWidth + ' ' + canvasHeight" :width="canvasWidth * scale" :height="canvasHeight * scale" role="img" :aria-label="'Hierarchical AAS graph for ' + product.id">
        <g v-for="node in positioned.filter(n => n.parent)" :key="'edge:' + node.id">
          <path :d="'M '+(positioned.find(p => p.id === node.parent)!.x+182)+' '+(positioned.find(p => p.id === node.parent)!.y+20)+' H '+(node.x-18)+' V '+(node.y+20)+' H '+node.x" fill="none" stroke="#538ca4" stroke-width="1.5"/>
        </g>
        <g v-for="node in positioned" :key="node.id" class="graph-node" :class="{ 'graph-node-active': selected.id === node.id }" role="button" tabindex="0" :aria-label="node.label + ', ' + node.kind + (node.children.length ? ', click to expand or collapse' : '')" @click="toggle(node)" @keydown.enter.prevent="toggle(node)" @keydown.space.prevent="toggle(node)">
          <rect :x="node.x" :y="node.y" width="182" height="42" rx="8" :class="node.kind === 'Submodel' ? 'graph-node-product' : node.kind === 'Property' ? 'graph-node-category' : 'graph-node-manufacturer'"/>
          <text :x="node.x+10" :y="node.y+17" font-size="11" fill="#f1faff" font-weight="600">{{ textLabel(node.label).slice(0,24) }}{{ textLabel(node.label).length > 24 ? '…' : '' }}</text>
          <text :x="node.x+10" :y="node.y+31" font-size="9" fill="#a9c8d8">{{ node.children.length ? (expanded.includes(node.id) ? '▾' : '▸') + ' ' : '' }}{{ node.kind === 'SubmodelElementCollection' ? 'Collection' : node.kind }}</text>
          <title>{{ node.label }}{{ showLiterals && node.value ? ': ' + node.value : '' }}</title>
        </g>
      </svg>
    </div>
    <div class="graph-inspector" aria-live="polite">
      <div class="panel-title"><h2><Network :size="15"/> Node inspector</h2><span class="pill">{{ selected.kind }}</span></div>
      <div class="catalog-property"><span>idShort</span><strong class="catalog-wrap">{{ selected.label }}</strong></div>
      <div class="catalog-property"><span>Model type</span><strong class="catalog-wrap">{{ selected.kind }}</strong></div>
      <div v-if="selected.value && showLiterals" class="catalog-property"><span>Value</span><strong class="catalog-wrap">{{ selected.value }}</strong></div>
      <div class="catalog-property"><span>Child elements</span><strong>{{ selected.children.length }}</strong></div>
    </div>
    <p class="catalog-disclaimer">This is a faithful AAS containment hierarchy generated from the bundled ProductCatalog instance. It is not a live RDF/SPARQL graph; GraphDB-backed semantic links will be a separate layer.</p>
  </div>
</template>
