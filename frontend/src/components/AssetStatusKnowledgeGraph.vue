<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { Network } from 'lucide-vue-next'

type AssetRecord = { id: string; fields: Record<string, string> }
const props = defineProps<{ asset: AssetRecord }>()
const loading = ref(false)
const error = ref('')
const triples = ref<{ subject: string; predicate: string; object: string; resource: boolean }[]>([])
const endpoint = import.meta.env.VITE_KG_SPARQL_ENDPOINT || '/kg/repositories/tep'
const base = 'https://example.org/tep/kg/vocab/'
const statusUri = 'https://example.org/tep/status/'
const escapeIri = (s: string) => s.replace(/[<>"{}|^`\\]/g, '')
async function load() {
  const assetId = props.asset.fields.AssetId
  triples.value = []
  error.value = ''
  if (!assetId || !/^https?:\/\//.test(assetId)) { error.value = 'No valid asset IRI is available.'; return }
  loading.value = true
  try {
    const query = `SELECT ?s ?p ?o WHERE { VALUES ?asset { <${escapeIri(assetId)}> } { BIND(?asset AS ?s) ?s ?p ?o } UNION { ?asset <${base}hasAssetInventoryStatus> ?s . ?s ?p ?o } UNION { ?asset ?link ?s . FILTER(?link IN (<${base}hasProductType>, <${base}hasOperationalSignal>)) ?s ?p ?o } } LIMIT 250`
    const response = await fetch(endpoint + (endpoint.includes('?') ? '&' : '?') + new URLSearchParams({ query }), { headers: { Accept: 'application/sparql-results+json' } })
    if (!response.ok) throw new Error(`SPARQL endpoint returned HTTP ${response.status}`)
    const json = await response.json()
    triples.value = (json.results?.bindings || []).map((row: any) => ({ subject: row.s.value, predicate: row.p.value, object: row.o.value, resource: row.o.type === 'uri' }))
    if (!triples.value.length) error.value = 'No RDF statements found for this asset in the KG.'
  } catch (e) { error.value = e instanceof Error ? e.message : 'Knowledge Graph query failed.' }
  finally { loading.value = false }
}
watch(() => props.asset.fields.AssetId, load, { immediate: true })
type GraphNode = { id: string; label: string; kind: string; x: number; y: number; attributes: { name: string; value: string }[] }
type GraphEdge = { from: string; to: string; label: string }
const readable = (s: string) => s.replace(/([a-z])([A-Z])/g, '$1 $2')
const focused = ref('')
watch(() => props.asset.id, () => { focused.value = props.asset.fields.AssetId })
const graph = computed(() => {
  const assetId = props.asset.fields.AssetId
  const resources = new Set([assetId])
  for (const t of triples.value) {
    resources.add(t.subject)
    if (t.resource && [base+'hasAssetInventoryStatus', base+'hasProductType', base+'hasOperationalSignal'].includes(t.predicate)) resources.add(t.object)
  }
  const ids = [...resources]
  const positions = [[170,230],[490,230],[170,455],[490,455]]
  const nodes: GraphNode[] = ids.map((id, i) => {
    const attributes = triples.value.filter(t => t.subject === id && !t.resource).map(t => ({ name: t.predicate.split(/[/#]/).pop() || t.predicate, value: t.object }))
    const kind = id === assetId ? 'SimulatedAsset' : id.startsWith(statusUri) ? 'AssetInventoryStatus' : id.includes('/signals/') ? 'TEP Signal' : 'ProductType'
    const label = attributes.find(a => ['EquipmentTag','ManufacturerPartNumber','signalId'].includes(a.name))?.value || (kind === 'AssetInventoryStatus' ? 'AssetInventoryStatus' : id.split('/').pop() || id)
    return { id, label, kind, x: positions[i % positions.length][0] + Math.floor(i/4)*130, y: positions[i % positions.length][1], attributes }
  })
  const edges: GraphEdge[] = triples.value.filter(t => t.resource && resources.has(t.object) && [base+'hasAssetInventoryStatus',base+'hasProductType',base+'hasOperationalSignal'].includes(t.predicate)).map(t => ({ from: t.subject, to: t.object, label: t.predicate.slice(base.length) }))
  return { nodes, edges }
})
const selected = computed(() => graph.value.nodes.find(n => n.id === focused.value) || graph.value.nodes[0])
const node = (id: string) => graph.value.nodes.find(n => n.id === id)
const connections = computed(() => graph.value.edges.filter(e => e.from === selected.value?.id || e.to === selected.value?.id))
</script>

<template>
  <div class="product-knowledge">
    <div class="graph-toolbar"><span class="pill amber-pill">SPARQL Knowledge Graph</span></div>
    <p class="graph-explanation">Resources and relationships are queried from the RDF repository. Select a node to inspect its KG properties.</p>
    <p v-if="loading" role="status">Loading Knowledge Graph…</p>
    <p v-if="error" role="alert" class="catalog-disclaimer">{{ error }} <button class="secondary" type="button" @click="load">Retry</button></p>
    <div v-if="graph.nodes.length && !error" class="graph-workspace">
      <div class="graph-canvas graph-rdf-scroll" role="group" :aria-label="'AssetInventoryStatus graph for ' + asset.id">
        <svg viewBox="0 0 800 610" width="100%" height="100%" role="img" class="graph-pan-svg">
          <defs><marker id="asset-status-arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6" markerHeight="6" orient="auto"><path d="M0 0 L10 5 L0 10z" fill="#598fa8"/></marker></defs>
          <g v-for="edge in graph.edges" :key="edge.from + edge.to">
            <template v-if="node(edge.from) && node(edge.to)">
              <line :x1="node(edge.from)!.x" :y1="node(edge.from)!.y" :x2="node(edge.to)!.x" :y2="node(edge.to)!.y" stroke="#598fa8" stroke-width="2" marker-end="url(#asset-status-arrow)" />
              <text :x="(node(edge.from)!.x + node(edge.to)!.x)/2" :y="(node(edge.from)!.y + node(edge.to)!.y)/2 - 14" text-anchor="middle" font-size="11" fill="#8edbd9" stroke="#0b1829" stroke-width="3" paint-order="stroke">{{ edge.label }}</text>
            </template>
          </g>
          <g v-for="n in graph.nodes" :key="n.id" class="graph-node graph-rdf-node" :class="{ 'graph-node-active': selected?.id === n.id }" tabindex="0" role="button" :aria-label="n.kind + ': ' + n.label" @click="focused=n.id" @keydown.enter.prevent="focused=n.id" @keydown.space.prevent="focused=n.id">
            <circle :cx="n.x" :cy="n.y" r="67" class="graph-rdf-resource"/>
            <text :x="n.x" :y="n.y-6" text-anchor="middle" font-size="11" font-weight="600" fill="#effaff" pointer-events="none">{{ n.label.length > 21 ? n.label.slice(0,20) + '…' : n.label }}</text>
            <text :x="n.x" :y="n.y+14" text-anchor="middle" font-size="10" fill="#b5d5e2" pointer-events="none">{{ n.kind }}</text>
            <title>{{ n.label }}</title>
          </g>
        </svg>
      </div>
      <aside v-if="selected" class="graph-sidepane" aria-live="polite">
        <div class="panel-title"><h2><Network :size="15"/> Node properties</h2><span class="pill">{{ selected.kind }}</span></div>
        <div class="graph-sidepane-heading"><strong class="catalog-wrap">{{ selected.label }}</strong><small>Selected resource</small></div>
        <div v-for="attribute in selected.attributes" :key="attribute.name" class="graph-attribute"><small>{{ readable(attribute.name) }}</small><strong class="catalog-wrap">{{ attribute.value }}</strong></div>
        <h2 class="catalog-section-title">Relationships <span class="pill muted">{{ connections.length }}</span></h2>
        <div v-for="edge in connections" :key="edge.from+edge.to" class="graph-relationship"><small>{{ edge.label }}</small><button type="button" @click="focused=edge.from === selected.id ? edge.to : edge.from">{{ node(edge.from === selected.id ? edge.to : edge.from)?.label }}</button></div>
      </aside>
    </div>
    <p class="catalog-disclaimer">SPARQL-backed RDF view. The KG repository must contain asset, status, product and signal triples; this view does not read AAS JSON.</p>
  </div>
</template>
