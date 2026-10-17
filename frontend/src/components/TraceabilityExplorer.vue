<script setup lang="ts">
import { computed, ref, onMounted } from 'vue'
import { selectTriples, localName, type Triple } from '../lib/sparql'

const domains = ['dexpi', 'ecad', 'productcatalog', 'assetinventory'] as const
const namespace = 'https://example.org/'
const triples = ref<Triple[]>([])
const loading = ref(false)
const error = ref('')
const search = ref('')
const selected = ref('')
const labels = ref<Record<string, string>>({})
const typeMap = ref<Record<string, string>>({})
const status = ref('')
const domainOf = (id: string) => {
  const type = typeMap.value[id] || ''
  const match = domains.find(d => type.startsWith(namespace + d + '/'))
  return match || ''
}
const crossLinks = computed(() => triples.value.filter(t => t.resource && t.subject !== t.object && domainOf(t.subject) && domainOf(t.object) && domainOf(t.subject) !== domainOf(t.object)))
const filtered = computed(() => crossLinks.value.filter(t => !search.value || [t.subject, t.object, labels.value[t.subject], labels.value[t.object], localName(t.predicate)].join(' ').toLowerCase().includes(search.value.toLowerCase())))
const connected = computed(() => filtered.value.filter(t => !selected.value || t.subject === selected.value || t.object === selected.value))
const nodes = computed(() => [...new Set(connected.value.flatMap(t => [t.subject, t.object]))])
const label = (id: string) => labels.value[id] || localName(id)
const color = (id: string) => ({dexpi:'#0e7490',ecad:'#0369a1',productcatalog:'#7c3aed',assetinventory:'#0f766e'}[domainOf(id)] || '#475569')
async function load() {
  loading.value = true
  error.value = ''
  status.value = ''
  try {
    // Only asserted RDF IRI links are considered; matching names never create edges.
    // Fetch class declarations for both ends so a link is shown only when
    // it actually connects resources typed in different engineering domains.
    const result = await selectTriples(`SELECT ?s ?p ?o WHERE {
      GRAPH ?g {
        ?s ?p ?o .
        FILTER(isIRI(?o) && ?s != ?o)
        ?s a ?st .
        ?o a ?ot .
        FILTER(
          (STRSTARTS(STR(?st), "https://example.org/dexpi/") ||
           STRSTARTS(STR(?st), "https://example.org/ecad/") ||
           STRSTARTS(STR(?st), "https://example.org/productcatalog/") ||
           STRSTARTS(STR(?st), "https://example.org/assetinventory/")) &&
          (STRSTARTS(STR(?ot), "https://example.org/dexpi/") ||
           STRSTARTS(STR(?ot), "https://example.org/ecad/") ||
           STRSTARTS(STR(?ot), "https://example.org/productcatalog/") ||
           STRSTARTS(STR(?ot), "https://example.org/assetinventory/"))
        )
        FILTER(STRBEFORE(STRAFTER(STR(?st), "https://example.org/"), "/") !=
               STRBEFORE(STRAFTER(STR(?ot), "https://example.org/"), "/"))
      }
    } LIMIT 3000`)
    triples.value = result
    const ids = [...new Set(result.flatMap(t => [t.subject, t.object]))]
    if (ids.length) {
      const values = ids.map(id => '<' + id + '>').join(' ')
      const meta = await selectTriples(`SELECT ?s ?p ?o WHERE {
        GRAPH ?g { VALUES ?s { ${values} }
          { ?s a ?o . BIND(<http://www.w3.org/1999/02/22-rdf-syntax-ns#type> AS ?p) }
          UNION
          { ?s <http://www.w3.org/2000/01/rdf-schema#label> ?o .
            BIND(<http://www.w3.org/2000/01/rdf-schema#label> AS ?p) }
        }
      } LIMIT 6000`)
      const types: Record<string, string> = {}
      const names: Record<string, string> = {}
      for (const t of meta) {
        if (t.predicate.endsWith('#type') && domains.some(d => t.object.startsWith(namespace+d+'/'))) types[t.subject] = t.object
        if (t.predicate.endsWith('#label')) names[t.subject] = t.object
      }
      typeMap.value = types
      labels.value = names
    } else { typeMap.value = {}; labels.value = {} }
    status.value = result.length ? 'Verified RDF links only' : 'No cross-domain RDF links found. Domain graphs may exist independently; mappings must be asserted before traceability can be shown.'
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e)
    triples.value = []
  } finally { loading.value = false }
}
onMounted(() => { void load() })
</script>

<template>
  <section class="panel">
    <div class="panel-title"><div><h2>Cross-domain Traceability Explorer</h2><p>DEXPI · ECAD · ProductCatalog · AssetInventory</p></div><button class="secondary" type="button" @click="load">Refresh RDF links</button></div>
    <p class="catalog-disclaimer">Only explicitly asserted, cross-domain RDF resource relationships are displayed. No links are inferred from matching names.</p>
    <p v-if="loading" role="status">Querying GraphDB for verified cross-domain links…</p>
    <p v-if="error" role="alert" class="catalog-disclaimer">{{ error }}</p>
    <p v-if="status" role="status">{{ status }}</p>
    <template v-if="!loading && !error">
      <div class="metric-grid"><div class="metric"><small>VERIFIED RELATIONSHIPS</small><strong>{{ crossLinks.length }}</strong></div><div class="metric"><small>CONNECTED RESOURCES</small><strong>{{ nodes.length }}</strong></div></div>
      <label class="search"><input v-model="search" placeholder="Filter resources, labels, predicates…" aria-label="Filter traceability links"/></label>
      <div v-if="selected" class="graph-toolbar"><button class="secondary" @click="selected=''">Show all relationships</button><span>Selected: {{ label(selected) }}</span></div>
      <div v-if="connected.length" class="graph-workspace">
        <div class="graph-canvas graph-rdf-scroll" style="padding:18px;overflow:auto;max-height:650px">
          <div v-for="(link,i) in connected" :key="i" class="graph-relationship" style="display:flex;align-items:center;gap:12px;flex-wrap:wrap;margin-bottom:12px">
            <button type="button" @click="selected=link.subject" :style="{borderLeft:'4px solid '+color(link.subject)}">{{ label(link.subject) }} <small>({{ domainOf(link.subject) }})</small></button>
            <span aria-label="RDF predicate">→ {{ localName(link.predicate) }} →</span>
            <button type="button" @click="selected=link.object" :style="{borderLeft:'4px solid '+color(link.object)}">{{ label(link.object) }} <small>({{ domainOf(link.object) }})</small></button>
          </div>
        </div>
        <aside class="graph-sidepane"><h2>Resource details</h2><template v-if="selected"><strong>{{ label(selected) }}</strong><p class="catalog-wrap">{{ selected }}</p><p>Domain: {{ domainOf(selected) }}</p><p>Class: {{ localName(typeMap[selected] || '') }}</p><p>{{ connected.length }} visible verified relationships</p></template><p v-else>Select a resource to filter its verified relationships.</p></aside>
      </div>
      <p v-else-if="crossLinks.length" class="catalog-disclaimer">No relationships match the current filter.</p>
    </template>
  </section>
</template>
