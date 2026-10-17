<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { selectTriples, localName, type Triple } from '../lib/sparql'

const props = defineProps<{ domain: 'dexpi' | 'ecad' }>()
const triples = ref<Triple[]>([])
const loading = ref(false)
const error = ref('')
const search = ref('')
const selected = ref('')
const namespace = computed(() => 'https://example.org/' + props.domain + '/')
const rdfType = 'http://www.w3.org/1999/02/22-rdf-syntax-ns#type'
const labelPredicate = 'http://www.w3.org/2000/01/rdf-schema#label'

async function load() {
  loading.value = true
  error.value = ''
  triples.value = []
  selected.value = ''
  try {
    // Query domain predicates as well as domain-typed subjects. The AAS hierarchy
    // and schematic links often originate on wrapper collections, not leaf classes.
    const ns = namespace.value
    const query = `SELECT DISTINCT ?s ?p ?o WHERE {
      GRAPH ?g {
        ?s ?p ?o .
        FILTER(STRSTARTS(STR(?p), "${ns}") ||
          (?p = <${rdfType}> && STRSTARTS(STR(?o), "${ns}")))
      }
    } LIMIT 12000`
    triples.value = await selectTriples(query)
    if (!triples.value.length) error.value = 'No matching RDF resources in GraphDB. Import the lifted instance graphs first.'
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e)
  } finally {
    loading.value = false
  }
}
watch(() => props.domain, () => { void load() }, { immediate: true })
const subjects = computed(() => [...new Set(triples.value.map(t => t.subject))])
const kind = (id: string) => localName(triples.value.find(t => t.subject === id && t.predicate === rdfType && t.object.startsWith(namespace.value))?.object || 'Resource')
const label = (id: string) => triples.value.find(t => t.subject === id && t.predicate === labelPredicate)?.object || localName(id)
const resources = computed(() => new Set([...subjects.value, ...triples.value.filter(t => t.resource && t.predicate !== rdfType).map(t => t.object)]))
const filtered = computed(() => [...resources.value].filter(id => (label(id) + ' ' + kind(id)).toLowerCase().includes(search.value.toLowerCase())))
const visible = computed(() => {
  const initial = filtered.value.slice(0, 55)
  if (selected.value && !initial.includes(selected.value)) initial.unshift(selected.value)
  const ids = new Set(initial)
  // Keep the selected resource's immediate neighbors in view.
  if (selected.value) for (const t of triples.value) {
    if (!t.resource || t.predicate === rdfType) continue
    if (t.subject === selected.value) ids.add(t.object)
    if (t.object === selected.value) ids.add(t.subject)
    if (ids.size >= 95) break
  }
  return [...ids]
})
const focus = computed(() => selected.value || visible.value[0] || '')
const attributes = computed(() => triples.value.filter(t => t.subject === focus.value && !t.resource))
const outgoing = computed(() => triples.value.filter(t => t.subject === focus.value && t.resource && t.predicate !== rdfType))
const edges = computed(() => triples.value.filter(t => t.resource && t.predicate !== rdfType && visible.value.includes(t.subject) && visible.value.includes(t.object)))
function coords(id: string) {
  const i = visible.value.indexOf(id)
  const angle = i * 2.399963229728653
  const radius = 35 + 38 * Math.sqrt(Math.max(i, 0))
  return { x: 470 + Math.cos(angle) * radius, y: 360 + Math.sin(angle) * radius }
}
function choose(id: string) {
  selected.value = id
  // Selected neighbors remain visible without changing the search filter.
}
</script>

<template>
  <section class="panel">
    <div class="panel-title">
      <div><h2>{{ domain.toUpperCase() }} RDF Knowledge Graph</h2><p>Live GraphDB SPARQL resources and predicates</p></div>
      <button type="button" class="secondary" @click="load">Refresh</button>
    </div>
    <label class="search"><input v-model="search" placeholder="Search RDF resources…" /></label>
    <p v-if="loading" role="status">Querying GraphDB…</p>
    <p v-if="error" role="alert" class="catalog-disclaimer">{{ error }}</p>
    <template v-if="!loading && !error">
      <p class="catalog-disclaimer">Showing {{ visible.length }} of {{ subjects.length }} returned RDF subjects (query limit: 12,000 triples). Showing {{ edges.length }} visible RDF relationships. The diagram represents RDF relationships, not inferred piping or electrical geometry.</p>
      <div class="graph-workspace">
        <div class="graph-canvas graph-rdf-scroll" role="group" :aria-label="domain + ' RDF graph'">
          <svg viewBox="0 0 940 720" width="100%" height="100%" role="img">
            <g v-for="(edge, i) in edges" :key="i">
              <line :x1="coords(edge.subject).x" :y1="coords(edge.subject).y" :x2="coords(edge.object).x" :y2="coords(edge.object).y" stroke="#598fa8" stroke-width="1.5"/>
              <title>{{ localName(edge.predicate) }}</title>
            </g>
            <g v-for="id in visible" :key="id" role="button" tabindex="0" style="cursor:pointer" @click="choose(id)" @keydown.enter.prevent="choose(id)" @keydown.space.prevent="choose(id)">
              <circle :cx="coords(id).x" :cy="coords(id).y" :r="focus===id?31:23" :fill="focus===id?'#2563eb':'#365d75'" stroke="#9bc9e2"/>
              <text :x="coords(id).x" :y="coords(id).y+40" text-anchor="middle" fill="#c7e5f5" font-size="11">{{ label(id).slice(0,20) }}</text>
              <title>{{ kind(id) }}: {{ id }}</title>
            </g>
          </svg>
        </div>
        <aside v-if="focus" class="graph-sidepane">
          <div class="panel-title"><h2>Node properties</h2><span class="pill">{{ kind(focus) }}</span></div>
          <div class="graph-sidepane-heading"><strong class="catalog-wrap">{{ label(focus) }}</strong><small class="catalog-wrap">{{ focus }}</small></div>
          <div v-for="(t, i) in attributes" :key="i" class="graph-attribute"><small>{{ localName(t.predicate) }}</small><strong class="catalog-wrap">{{ t.object }}</strong></div>
          <h2 class="catalog-section-title">Outgoing RDF relationships</h2>
          <div v-for="(t, i) in outgoing" :key="i" class="graph-relationship"><small>{{ localName(t.predicate) }}</small><button type="button" @click="choose(t.object)">{{ label(t.object) }}</button></div>
        </aside>
      </div>
    </template>
  </section>
</template>
