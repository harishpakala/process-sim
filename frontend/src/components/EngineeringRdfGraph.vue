<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { selectTriples, localName, iri, type Triple } from '../lib/sparql'

const props = defineProps<{ domain: 'dexpi' | 'ecad' }>()
const namespace = computed(() => 'https://example.org/' + props.domain + '/')
const rdfType = 'http://www.w3.org/1999/02/22-rdf-syntax-ns#type'
const labelPredicate = 'http://www.w3.org/2000/01/rdf-schema#label'
const triples = ref<Triple[]>([])
const root = ref('')
const selected = ref('')
const expanded = ref<string[]>([])
const pending = ref<string[]>([])
const search = ref('')
const loading = ref(false)
const error = ref('')
const positions = ref<Record<string, { x: number; y: number }>>({})
const pinned = new Set<string>()
const pan = ref({ x: 0, y: 0 })
const zoom = ref(1)
const svgRef = ref<SVGSVGElement | null>(null)
let gesture: { id: string; x: number; y: number; originX: number; originY: number; moved: boolean } | null = null
let suppressClick = false
let captureTarget: Element | null = null
let generation = 0

const known = computed(() => new Set([root.value, ...triples.value.map(t => t.subject), ...triples.value.filter(t => t.resource && t.predicate !== rdfType).map(t => t.object)].filter(Boolean)))
const label = (id: string) => triples.value.find(t => t.subject === id && t.predicate === labelPredicate)?.object || localName(id)
const kind = (id: string) => localName(triples.value.find(t => t.subject === id && t.predicate === rdfType && t.object.startsWith(namespace.value))?.object || 'Resource')
const links = computed(() => triples.value.filter(t => t.resource && t.predicate !== rdfType && t.subject !== t.object))
const visible = computed(() => {
  if (!root.value) return []
  const visited = new Set([root.value])
  const queue = [root.value]
  while (queue.length) {
    const id = queue.shift()!
    if (!expanded.value.includes(id)) continue
    for (const t of links.value) {
      const neighbor = t.subject === id ? t.object : t.object === id ? t.subject : ''
      if (neighbor && !visited.has(neighbor)) {
        visited.add(neighbor)
        queue.push(neighbor)
      }
    }
  }
  return [...visited]
})
const edges = computed(() => links.value.filter(t => visible.value.includes(t.subject) && visible.value.includes(t.object)))
const attributes = computed(() => triples.value.filter(t => t.subject === selected.value && !t.resource))
const outgoing = computed(() => links.value.filter(t => t.subject === selected.value))
const incoming = computed(() => links.value.filter(t => t.object === selected.value))
const suggestions = computed(() => [...known.value].filter(id => (label(id) + ' ' + kind(id)).toLowerCase().includes(search.value.toLowerCase())).slice(0, 15))

async function neighbors(id: string, token: number) {
  if (pending.value.includes(id)) return
  pending.value = [...pending.value, id]
  try {
    const target = iri(id)
    const query = `SELECT ?s ?p ?o WHERE {
      GRAPH ?g {
        { BIND(${target} AS ?s) ?s ?p ?o }
        UNION
        { ?s ?p ${target} . BIND(${target} AS ?o) FILTER(isIRI(?s)) }
      }
    } LIMIT 1000`
    const result = await selectTriples(query)
    if (token !== generation) return
    const keys = new Set(triples.value.map(t => JSON.stringify(t)))
    for (const t of result) {
      const key = JSON.stringify(t)
      if (!keys.has(key)) { triples.value.push(t); keys.add(key) }
    }
  } catch (e) {
    if (token === generation) error.value = e instanceof Error ? e.message : String(e)
    throw e
  } finally {
    pending.value = pending.value.filter(value => value !== id)
  }
}

async function load() {
  const token = ++generation
  loading.value = true
  error.value = ''
  triples.value = []
  expanded.value = []
  selected.value = ''
  root.value = ''
  resetView()
  try {
    // The AAS Submodel root is typed aas:Submodel, not a domain Equipment/Device.
    // Resolve it by its lifted rdfs:label (TEP_DEXPI / TEP_ECAD).
    const rootLabel = props.domain === 'dexpi' ? 'TEP_DEXPI' : 'TEP_ECAD'
    const rows = await selectTriples(`SELECT ?s ?p ?o WHERE {
      GRAPH ?g {
        ?s a <https://example.org/aas/Submodel> ;
           <${labelPredicate}> ?name .
        FILTER(STR(?name) = "${rootLabel}")
        BIND(<${rdfType}> AS ?p)
        BIND(<https://example.org/aas/Submodel> AS ?o)
      }
    } LIMIT 1`)
    if (token !== generation) return
    if (!rows.length) { error.value = 'No AAS Submodel root named ' + rootLabel + ' found in GraphDB.'; return }
    root.value = rows[0].subject
    selected.value = root.value
    await neighbors(root.value, token)
  } catch (e) {
    if (token === generation) error.value = e instanceof Error ? e.message : String(e)
  } finally {
    if (token === generation) loading.value = false
  }
}
watch(() => props.domain, () => { void load() }, { immediate: true })

async function toggle(id: string) {
  selected.value = id
  if (expanded.value.includes(id)) {
    expanded.value = expanded.value.filter(value => value !== id)
    return
  }
  try {
    await neighbors(id, generation)
    expanded.value = [...expanded.value, id]
    layoutGraph(id)
  } catch { /* Error is shown in the panel. */ }
}
async function focusOn(id: string) {
  ++generation
  triples.value = []
  expanded.value = []
  error.value = ''
  root.value = id
  resetView()
  selected.value = id
  search.value = ''
  try { await neighbors(id, generation) } catch { /* Error shown in panel. */ }
}
function nodeColor(id: string) {
  const type = kind(id)
  const colors: Record<string, string> = { Equipment: '#0e7490', InstrumentationFunction: '#7c3aed', ActuatingFunction: '#b45309', Device: '#0369a1', EndPoint: '#0f766e', PLCEndPoint: '#15803d', ConnectionPoints: '#0d9488', Connections: '#a16207', ElectricalNet: '#be185d' }
  return colors[type] || '#475569'
}
function layoutGraph(center: string) {
  const ids = visible.value
  if (ids.length < 2) return
  const next: Record<string, { x: number; y: number }> = {}
  ids.forEach((id, i) => {
    const existing = positions.value[id]
    const parent = positions.value[center] || coords(center)
    const angle = i * 2.399963229728653
    next[id] = existing || (id === center ? { ...parent } : { x: parent.x + Math.cos(angle) * (130 + 35 * Math.sqrt(i)), y: parent.y + Math.sin(angle) * (130 + 35 * Math.sqrt(i)) })
  })
  // Bounded deterministic force relaxation; dragged nodes stay fixed.
  for (let step = 0; step < 100; step++) {
    const force: Record<string, { x: number; y: number }> = {}
    ids.forEach(id => { force[id] = { x: 0, y: 0 } })
    for (let i = 0; i < ids.length; i++) for (let j = i + 1; j < ids.length; j++) {
      const a = ids[i], b = ids[j], dx = next[a].x - next[b].x, dy = next[a].y - next[b].y
      const dist2 = Math.max(dx * dx + dy * dy, 100)
      const strength = Math.min(18, 100000 / dist2) / Math.sqrt(dist2)
      force[a].x += dx * strength; force[a].y += dy * strength
      force[b].x -= dx * strength; force[b].y -= dy * strength
    }
    for (const edge of edges.value) {
      const a = next[edge.subject], b = next[edge.object]
      if (!a || !b) continue
      const dx = b.x - a.x, dy = b.y - a.y, dist = Math.max(Math.hypot(dx, dy), 1)
      const strength = (dist - 165) * 0.008
      force[edge.subject].x += dx * strength; force[edge.subject].y += dy * strength
      force[edge.object].x -= dx * strength; force[edge.object].y -= dy * strength
    }
    for (const id of ids) {
      if (pinned.has(id) || id === root.value) continue
      next[id].x += Math.max(-15, Math.min(15, force[id].x))
      next[id].y += Math.max(-15, Math.min(15, force[id].y))
    }
  }
  positions.value = { ...positions.value, ...next }
}
function coords(id: string) {
  if (positions.value[id]) return positions.value[id]
  const i = visible.value.indexOf(id)
  if (i <= 0) return { x: 470, y: 360 }
  const angle = (i - 1) * 2.399963229728653
  const radius = 115 + 36 * Math.sqrt(i)
  return { x: 470 + Math.cos(angle) * radius, y: 360 + Math.sin(angle) * radius }
}
function resetView() {
  positions.value = {}
  pinned.clear()
  pan.value = { x: 0, y: 0 }
  zoom.value = 1
}
function pointerDown(event: PointerEvent, id = '') {
  if (event.button !== 0) return
  suppressClick = false
  const point = coords(id)
  gesture = { id, x: event.clientX, y: event.clientY, originX: id ? point.x : pan.value.x, originY: id ? point.y : pan.value.y, moved: false }
  // Capture on the actual node, not the SVG root: root capture retargets
  // click/dblclick to the canvas and prevents expansion.
  // Pointer capture on a node can suppress the browser's native dblclick.
  // Only capture background pans; node drags track movement via SVG bubbling.
  captureTarget = id ? null : event.currentTarget as Element
  if (captureTarget && 'setPointerCapture' in captureTarget) (captureTarget as Element & { setPointerCapture(id: number): void }).setPointerCapture(event.pointerId)
}
function pointerMove(event: PointerEvent) {
  if (!gesture || !svgRef.value) return
  const rect = svgRef.value.getBoundingClientRect()
  if (!rect.width || !rect.height) return
  const dx = (event.clientX - gesture.x) * 940 / rect.width
  const dy = (event.clientY - gesture.y) * 720 / rect.height
  if (Math.abs(event.clientX - gesture.x) + Math.abs(event.clientY - gesture.y) > 4) gesture.moved = true
  if (!gesture.moved) return
  if (gesture.id) {
    positions.value = { ...positions.value, [gesture.id]: { x: gesture.originX + dx / zoom.value, y: gesture.originY + dy / zoom.value } }
  } else {
    pan.value = { x: gesture.originX + dx, y: gesture.originY + dy }
  }
}
function pointerUp(event: PointerEvent) {
  if (gesture?.moved) {
    if (gesture.id) pinned.add(gesture.id)
    suppressClick = true
    // A drag must not accidentally select or expand a node.
  }
  gesture = null
  if (captureTarget && 'hasPointerCapture' in captureTarget && (captureTarget as Element & { hasPointerCapture(id: number): boolean }).hasPointerCapture(event.pointerId)) (captureTarget as Element & { releasePointerCapture(id: number): void }).releasePointerCapture(event.pointerId)
  captureTarget = null
}
function selectNode(id: string) {
  if (suppressClick) { suppressClick = false; return }
  selected.value = id
}
function doubleClickNode(id: string) {
  // A double-click is an explicit expansion gesture; never let a previous
  // drag's click-suppression flag swallow it.
  suppressClick = false
  void toggle(id)
}
function wheel(event: WheelEvent) {
  if (!svgRef.value) return
  event.preventDefault()
  const rect = svgRef.value.getBoundingClientRect()
  const px = (event.clientX - rect.left) * 940 / rect.width
  const py = (event.clientY - rect.top) * 720 / rect.height
  const next = Math.max(0.25, Math.min(4, zoom.value * Math.exp(-event.deltaY * 0.0015)))
  const ratio = next / zoom.value
  pan.value = { x: px - (px - pan.value.x) * ratio, y: py - (py - pan.value.y) * ratio }
  zoom.value = next
}
</script>

<template>
  <section class="panel">
    <div class="panel-title">
      <div><h2>{{ domain.toUpperCase() }} RDF Knowledge Graph</h2><p>Single-click to inspect · double-click to expand or collapse one hop</p></div>
      <div style="display:flex;gap:8px;align-items:center"><button type="button" class="secondary" @click="resetView">Reset view</button><button type="button" class="secondary" @click="load">Reset graph</button></div>
    </div>
    <label class="search"><input v-model="search" placeholder="Find a loaded RDF resource…" /></label>
    <div v-if="search && suggestions.length" class="graph-relationship">
      <button v-for="id in suggestions" :key="id" type="button" @click="focusOn(id)">{{ label(id) }} ({{ kind(id) }})</button>
    </div>
    <p v-if="loading" role="status">Querying GraphDB…</p>
    <p v-if="error" role="alert" class="catalog-disclaimer">{{ error }}</p>
    <template v-if="!loading && root">
      <p class="catalog-disclaimer">{{ visible.length }} visible resources · {{ edges.length }} RDF relationships. Drag nodes to reposition, drag the background to pan, scroll to zoom, and double-click to expand. Node colors indicate RDF types; arrows show predicate direction. Dragged nodes retain their positions. Literal properties appear on the right.</p>
      <div class="graph-workspace">
        <div class="graph-canvas graph-rdf-scroll" role="group" :aria-label="domain + ' RDF graph'">
          <svg ref="svgRef" viewBox="0 0 940 720" width="100%" height="100%" role="img" style="touch-action:none;cursor:grab;user-select:none" @pointerdown="pointerDown($event)" @pointermove="pointerMove" @pointerup="pointerUp" @pointercancel="pointerUp" @wheel="wheel">
            <defs><marker id="rdf-arrow" markerWidth="7" markerHeight="7" refX="18" refY="3" orient="auto" markerUnits="userSpaceOnUse"><path d="M0 0 L6 3 L0 6" fill="none" stroke="#598fa8" stroke-width="1.2"/></marker></defs>
            <g :transform="`translate(${pan.x} ${pan.y}) scale(${zoom})`">
            <g v-for="(edge, i) in edges" :key="i">
              <line :x1="coords(edge.subject).x" :y1="coords(edge.subject).y" :x2="coords(edge.object).x" :y2="coords(edge.object).y" stroke="#598fa8" stroke-width="1.5" marker-end="url(#rdf-arrow)"/>
              <text :x="(coords(edge.subject).x+coords(edge.object).x)/2" :y="(coords(edge.subject).y+coords(edge.object).y)/2-6" text-anchor="middle" font-size="10" fill="#93c5d9" stroke="#142a3a" stroke-width="2" paint-order="stroke">{{ localName(edge.predicate).slice(0,22) }}</text>
              <title>{{ localName(edge.predicate) }}</title>
            </g>
            <g v-for="id in visible" :key="id" role="button" tabindex="0" style="cursor:move" @pointerdown.stop="pointerDown($event, id)" @click.stop="selectNode(id)" @dblclick.stop.prevent="doubleClickNode(id)" @keydown.enter.prevent="toggle(id)" @keydown.space.prevent="toggle(id)">
              <circle :cx="coords(id).x" :cy="coords(id).y" :r="selected===id?31:23" :fill="selected===id?'#2563eb':nodeColor(id)" stroke="#9bc9e2"/>
              <text :x="coords(id).x" :y="coords(id).y-32" text-anchor="middle" fill="#c7e5f5" font-size="15">{{ pending.includes(id)?'…':expanded.includes(id)?'−':'+' }}</text>
              <text :x="coords(id).x" :y="coords(id).y+43" text-anchor="middle" fill="#c7e5f5" font-size="11">{{ label(id).slice(0,22) }}</text>
              <title>{{ kind(id) }}: {{ id }} — double-click to {{ expanded.includes(id)?'collapse':'expand' }}</title>
            </g>
            </g>
          </svg>
        </div>
        <aside v-if="selected" class="graph-sidepane">
          <div class="panel-title"><h2>Node properties</h2><span class="pill">{{ kind(selected) }}</span></div>
          <div class="graph-sidepane-heading"><strong class="catalog-wrap">{{ label(selected) }}</strong><small class="catalog-wrap">{{ selected }}</small></div>
          <div v-for="(t, i) in attributes" :key="i" class="graph-attribute"><small>{{ localName(t.predicate) }}</small><strong class="catalog-wrap">{{ t.object }}</strong></div>
          <h2 class="catalog-section-title">Outgoing RDF relationships</h2>
          <div v-for="(t, i) in outgoing" :key="i" class="graph-relationship"><small>{{ localName(t.predicate) }}</small><button type="button" @click="selected=t.object">{{ label(t.object) }}</button></div>
          <h2 class="catalog-section-title">Incoming RDF relationships</h2>
          <div v-for="(t, i) in incoming" :key="i" class="graph-relationship"><small>{{ localName(t.predicate) }}</small><button type="button" @click="selected=t.subject">{{ label(t.subject) }}</button></div>
        </aside>
      </div>
    </template>
  </section>
</template>
