export type Triple = { subject: string; predicate: string; object: string; resource: boolean }
export const KG_ENDPOINT = import.meta.env.VITE_KG_SPARQL_ENDPOINT || '/kg/repositories/AAS'
export const KG_VOCAB = 'https://example.org/tep/kg/vocab/'
export const KG_TYPE = 'http://www.w3.org/1999/02/22-rdf-syntax-ns#type'
export async function selectTriples(query: string): Promise<Triple[]> {
  const response = await fetch(KG_ENDPOINT + (KG_ENDPOINT.includes('?') ? '&' : '?') + new URLSearchParams({ query }), { headers: { Accept: 'application/sparql-results+json' } })
  if (!response.ok) {
    const detail = (await response.text()).slice(0, 900)
    throw new Error(`GraphDB SPARQL HTTP ${response.status} (${KG_ENDPOINT}): ${detail || 'No response details'}`)
  }
  const data = await response.json()
  if (!Array.isArray(data?.results?.bindings)) throw new Error('GraphDB did not return SPARQL JSON bindings.')
  return data.results.bindings.map((row: Record<string, { type: string; value: string }>) => ({
    subject: row.s.value, predicate: row.p.value, object: row.o.value, resource: row.o.type === 'uri',
  }))
}
export function iri(value: string): string {
  if (!/^https?:\/\/[a-zA-Z0-9._~:/?#\[\]@!$&'()*+,;=%-]+$/.test(value)) throw new Error('Invalid RDF IRI')
  return '<' + value + '>'
}
export function localName(value: string) { return value.split(/[/#]/).pop() || value }
