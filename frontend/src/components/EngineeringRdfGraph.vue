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
  try {
    const classes = props.domain === 'dexpi' ? ['Equipment', 'InstrumentationFunction', 'ActuatingFunction'] : ['Device', 'ElectricalNet', 'Connections']
    const values = classes.map(name => iri(namespace.value + name)).join(' ')
    const rows = await selectTriples(`SELECT ?s ?p ?o WHERE {
      GRAPH ?g { ?s a ?o . VALUES ?o { ${values} } BIND(<${rdfType}> AS ?p) }
    } LIMIT 1`)
    if (token !== generation) return
    if (!rows.length) { error.value = 'No matching RDF instance found in GraphDB.'; return }
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
  } catch { /* Error is shown in the panel. */ }
}
async function focusOn(id: string) {
  ++generation
  triples.value = []
  expanded.value = []
  error.value = ''
  root.value = id
  selected.value = id
  search.value = ''
  try { await neighbors(id, generation) } catch { /* Error shown in panel. */ }
}
function coords(id: string) {
  const i = visible.value.indexOf(id)
  if (i === 0) return { x: 470, y: 360 }
  const angle = (i - 1) * 2.399963229728653
  const radius = 115 + 36 * Math.sqrt(i)
  return { x: 470 + Math.cos(angle) * radius, y: 360 + Math.sin(angle) * radius }
}
</script>

<template>
  <section class="panel">
    <div class="panel-title">
      <div><h2>{{ domain.toUpperCase() }} RDF Knowledge Graph</h2><p>Single-click to inspect · double-click to expand or collapse one hop</p></div>
      <button type="button" class="secondary" @click="load">Reset graph</button>
    </div>
    <label class="search"><input v-model="search" placeholder="Find a loaded RDF resource…" /></label>
    <div v-if="search && suggestions.length" class="graph-relationship">
      <button v-for="id in suggestions" :key="id" type="button" @click="focusOn(id)">{{ label(id) }} ({{ kind(id) }})</button>
    </div>
    <p v-if="loading" role="status">Querying GraphDB…</p>
    <p v-if="error" role="alert" class="catalog-disclaimer">{{ error }}</p>
    <template v-if="!loading && root">
      <p class="catalog-disclaimer">{{ visible.length }} visible resources · {{ edges.length }} RDF relationships. Double-click a node to reveal its immediate neighbors. Literal properties appear on the right.</p>
      <div class="graph-workspace">
        <div class="graph-canvas graph-rdf-scroll" role="group" :aria-label="domain + ' RDF graph'">
          <svg viewBox="0 0 940 720" width="100%" height="100%" role="img">
            <g v-for="(edge, i) in edges" :key="i">
              <line :x1="coords(edge.subject).x" :y1="coords(edge.subject).y" :x2="coords(edge.object).x" :y2="coords(edge.object).y" stroke="#598fa8" stroke-width="1.5"/>
              <title>{{ localName(edge.predicate) }}</title>
            </g>
            <g v-for="id in visible" :key="id" role="button" tabindex="0" style="cursor:pointer" @click="selected=id" @dblclick.prevent="toggle(id)" @keydown.enter.prevent="toggle(id)" @keydown.space.prevent="toggle(id)">
              <circle :cx="coords(id).x" :cy="coords(id).y" :r="selected===id?31:23" :fill="selected===id?'#2563eb':'#365d75'" stroke="#9bc9e2"/>
              <text :x="coords(id).x" :y="coords(id).y-32" text-anchor="middle" fill="#c7e5f5" font-size="15">{{ pending.includes(id)?'…':expanded.includes(id)?'−':'+' }}</text>
              <text :x="coords(id).x" :y="coords(id).y+43" text-anchor="middle" fill="#c7e5f5" font-size="11">{{ label(id).slice(0,22) }}</text>
              <title>{{ kind(id) }}: {{ id }} — double-click to {{ expanded.includes(id)?'collapse':'expand' }}</title>
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
