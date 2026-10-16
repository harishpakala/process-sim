<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { Network } from 'lucide-vue-next'

type AssetRecord = { id: string; fields: Record<string, string> }
const props = defineProps<{ asset: AssetRecord; product?: Record<string, string> }>()
type GraphNode = { id: string; label: string; kind: string; x: number; y: number; attributes: { name: string; value: string }[] }
type GraphEdge = { from: string; to: string; label: string }
const statusKeys = ['ModelingStatus', 'SimulationStatus', 'MonitoringStatus', 'FaultInjectionStatus', 'FaultDetectionStatus']
const readable = (s: string) => s.replace(/([a-z])([A-Z])/g, '$1 $2')
const focused = ref('asset')
watch(() => props.asset.id, () => { focused.value = 'asset' })
const graph = computed(() => {
  const fields = props.asset.fields
  const nodes: GraphNode[] = [
    { id: 'asset', label: fields.EquipmentTag || props.asset.id, kind: 'SimulatedAsset', x: 170, y: 230,
      attributes: [{ name: 'AssetId', value: fields.AssetId || props.asset.id }, { name: 'AssetName', value: fields.AssetName || '' }, { name: 'AssetType', value: fields.AssetType || '' }] },
    { id: 'status', label: 'AssetInventoryStatus', kind: 'Status', x: 490, y: 230,
      attributes: statusKeys.map(name => ({ name, value: fields[name] || 'Not assigned' })) }
  ]
  const edges: GraphEdge[] = [{ from: 'asset', to: 'status', label: 'hasAssetInventoryStatus' }]
  if (fields.OperationalReference) {
    nodes.push({ id: 'signal', label: fields.OperationalReference, kind: 'TEP Signal', x: 170, y: 455,
      attributes: [{ name: 'OperationalReference', value: fields.OperationalReference }] })
    edges.push({ from: 'asset', to: 'signal', label: 'hasOperationalSignal' })
  }
  if (fields.ProductReference && props.product) {
    nodes.push({ id: 'product', label: props.product.ManufacturerPartNumber || 'Product type', kind: 'ProductType', x: 490, y: 455,
      attributes: [{ name: 'ProductId', value: fields.ProductReference }, { name: 'Manufacturer', value: props.product.ManufacturerName || '' }] })
    edges.push({ from: 'asset', to: 'product', label: 'hasProductType' })
  }
  return { nodes, edges }
})
const selected = computed(() => graph.value.nodes.find(n => n.id === focused.value) || graph.value.nodes[0])
const node = (id: string) => graph.value.nodes.find(n => n.id === id)
const connections = computed(() => graph.value.edges.filter(e => e.from === selected.value.id || e.to === selected.value.id))
</script>

<template>
  <div class="product-knowledge">
    <div class="graph-toolbar"><span class="pill amber-pill">Local AAS status KG preview · not live GraphDB</span></div>
    <p class="graph-explanation">Select a resource to inspect its properties and relationships. Status values are read from the selected asset's AAS snapshot; no live runtime state is inferred.</p>
    <div class="graph-workspace">
      <div class="graph-canvas graph-rdf-scroll" role="group" :aria-label="'AssetInventoryStatus graph for ' + asset.id">
        <svg viewBox="0 0 800 610" width="100%" height="100%" role="img" class="graph-pan-svg">
          <defs><marker id="asset-status-arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6" markerHeight="6" orient="auto"><path d="M0 0 L10 5 L0 10z" fill="#598fa8"/></marker></defs>
          <g v-for="edge in graph.edges" :key="edge.from + edge.to">
            <template v-if="node(edge.from) && node(edge.to)">
              <line :x1="node(edge.from)!.x" :y1="node(edge.from)!.y" :x2="node(edge.to)!.x" :y2="node(edge.to)!.y" stroke="#598fa8" stroke-width="2" marker-end="url(#asset-status-arrow)" />
              <text :x="(node(edge.from)!.x + node(edge.to)!.x)/2" :y="(node(edge.from)!.y + node(edge.to)!.y)/2 - 14" text-anchor="middle" font-size="11" fill="#8edbd9" stroke="#0b1829" stroke-width="3" paint-order="stroke">{{ edge.label }}</text>
            </template>
          </g>
          <g v-for="n in graph.nodes" :key="n.id" class="graph-node graph-rdf-node" :class="{ 'graph-node-active': selected.id === n.id }" tabindex="0" role="button" :aria-label="n.kind + ': ' + n.label" @click="focused=n.id" @keydown.enter.prevent="focused=n.id" @keydown.space.prevent="focused=n.id">
            <circle :cx="n.x" :cy="n.y" r="67" class="graph-rdf-resource"/>
            <text :x="n.x" :y="n.y-6" text-anchor="middle" font-size="11" font-weight="600" fill="#effaff" pointer-events="none">{{ n.label.length > 21 ? n.label.slice(0,20) + '…' : n.label }}</text>
            <text :x="n.x" :y="n.y+14" text-anchor="middle" font-size="10" fill="#b5d5e2" pointer-events="none">{{ n.kind }}</text>
            <title>{{ n.label }}</title>
          </g>
        </svg>
      </div>
      <aside class="graph-sidepane" aria-live="polite">
        <div class="panel-title"><h2><Network :size="15"/> Node properties</h2><span class="pill">{{ selected.kind }}</span></div>
        <div class="graph-sidepane-heading"><strong class="catalog-wrap">{{ selected.label }}</strong><small>Selected resource</small></div>
        <div v-for="attribute in selected.attributes" :key="attribute.name" class="graph-attribute"><small>{{ readable(attribute.name) }}</small><strong class="catalog-wrap">{{ attribute.value }}</strong></div>
        <h2 class="catalog-section-title">Relationships <span class="pill muted">{{ connections.length }}</span></h2>
        <div v-for="edge in connections" :key="edge.from+edge.to" class="graph-relationship"><small>{{ edge.label }}</small><button type="button" @click="focused=edge.from === selected.id ? edge.to : edge.from">{{ node(edge.from === selected.id ? edge.to : edge.from)?.label }}</button></div>
      </aside>
    </div>
    <p class="catalog-disclaimer">AAS-derived semantic preview. The status resource and hasAssetInventoryStatus edge are proposed mappings; GraphDB ingestion and live SPARQL queries are not connected.</p>
  </div>
</template>
