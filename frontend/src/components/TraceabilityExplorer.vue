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
const referenceTriples = ref<Triple[]>([])
const resolvedReferences = ref<{source:string;predicate:string;value:string;target:string;domain:string}[]>([])
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
  referenceTriples.value = []
  resolvedReferences.value = []
  try {
    // Only asserted RDF IRI links are considered; matching names never create edges.
    // Fetch class declarations for both ends so a link is shown only when
    // it actually connects resources typed in different engineering domains.
    const result = await selectTriples(`SELECT DISTINCT ?s ?p ?o WHERE {
      GRAPH ?g { ?s ?p ?o . FILTER(?s != ?o) }
      GRAPH ?gs { ?s a ?st }
      GRAPH ?go { ?o a ?ot }
      FILTER(isIRI(?o))
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
    } LIMIT 3000`)
    referenceTriples.value = await selectTriples(`SELECT DISTINCT ?s ?p ?o WHERE {
      GRAPH ?g { ?s ?p ?o . FILTER(isLiteral(?o))
        FILTER(REGEX(STR(?p), "(EngineeringReference|ProductReference|OperationalReference)$", "i"))
      }
    } LIMIT 3000`)
    // Resolve literal reference values only through exact RDF identifier values.
    // Do not guess from labels or substrings; preserve the original evidence.
    if (referenceTriples.value.length) {
      const values = [...new Set(referenceTriples.value.map(t => t.object).filter(v => v.startsWith('http://') || v.startsWith('https://')))]
      const found: {source:string;predicate:string;value:string;target:string;domain:string}[] = []
      for (let i = 0; i < values.length; i += 80) {
        const batch = values.slice(i, i + 80)
        const quoted = batch.map(v => JSON.stringify(v)).join(' ')
        const matches = await selectTriples(`SELECT DISTINCT ?s ?p ?o WHERE {
          VALUES ?value { ${quoted} }
          GRAPH ?g {
            ?s ?p ?o .
            FILTER(isLiteral(?o) && STR(?o) = STR(?value))
            FILTER(REGEX(STR(?p), "(Identifier|Reference|AssetId|id)$", "i"))
          }
          GRAPH ?gt { ?s a ?type }
          FILTER(STRSTARTS(STR(?type), "https://example.org/dexpi/") ||
                 STRSTARTS(STR(?type), "https://example.org/ecad/") ||
                 STRSTARTS(STR(?type), "https://example.org/productcatalog/") ||
                 STRSTARTS(STR(?type), "https://example.org/assetinventory/"))
        } LIMIT 1000`)
        for (const m of matches) {
          for (const ref of referenceTriples.value.filter(t => t.object === m.object && t.subject !== m.subject)) {
            found.push({source:ref.subject,predicate:ref.predicate,value:ref.object,target:m.subject,domain:localName(m.predicate)})
          }
        }
      }
      resolvedReferences.value = [...new Map(found.map(r => [r.source+'|'+r.predicate+'|'+r.target,r])).values()]
    }
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
    status.value = result.length ? 'Verified RDF resource links found.' : 'No direct cross-domain RDF resource links matched. Reference properties are shown separately below.'
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e)
    triples.value = []
    referenceTriples.value = []
    resolvedReferences.value = []
  } finally { loading.value = false }
}
onMounted(() => { void load() })
</script>

<template>
  <section class="panel">
    <div class="panel-title"><div><h2>Cross-domain Traceability Explorer</h2><p>DEXPI · ECAD · ProductCatalog · AssetInventory</p></div><button class="secondary" type="button" @click="load">Refresh RDF links</button></div>
    <p class="catalog-disclaimer">Only explicitly asserted, cross-domain RDF resource relationships are displayed. Literal reference properties are listed separately and are not claimed as resolved RDF edges.</p>
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
      <section class="panel" v-if="resolvedReferences.length"><h2>Resolved reference paths</h2><p class="catalog-disclaimer">Each path matches an exact identifier literal on a typed RDF resource. This is a validated reference mapping, not an asserted object-property edge.</p><div v-for="(r,i) in resolvedReferences" :key="i" class="graph-relationship" style="margin-bottom:12px"><strong class="catalog-wrap">{{ r.source }}</strong><span>→ {{ localName(r.predicate) }} ({{ r.value }}) →</span><strong class="catalog-wrap">{{ r.target }}</strong></div></section>
      <section class="panel" v-if="referenceTriples.length"><h2>Declared cross-domain references</h2><p class="catalog-disclaimer">These values are present in RDF as literal reference properties. They are not asserted resource-to-resource edges.</p><div v-for="(t,i) in referenceTriples" :key="i" class="graph-relationship"><small>{{ localName(t.predicate) }}</small><strong class="catalog-wrap">{{ t.subject }}</strong><span class="catalog-wrap">→ {{ t.object }}</span></div></section>
    </template>
  </section>
</template>
