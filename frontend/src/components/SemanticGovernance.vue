<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'

type AasElement = {
  idShort: string
  modelType: string
  value?: unknown
  valueType?: string
  min?: unknown
  max?: unknown
  [key: string]: unknown
}
type AasDocument = { id: string; idShort: string; submodelElements: AasElement[] }
type ElementOption = { key: string; document: AasDocument; path: string; parentPath: string; element: AasElement }
type GovernanceResult = {
  message_id: string
  decision: 'ACCEPTED' | 'REJECTED' | 'DEFERRED' | string
  committed: boolean
  repository_version: number
  triggered_policies: string[]
  evaluated_contracts: { contract_id: string; verdict: 'V' | 'F' | 'U' | 'NA' | string }[]
}
type QualificationContext = {
  version: number
  evidence_complete: string[]
  identity_normalized: boolean
  applicability_confirmed: boolean
  source: string
}

const documents = ref<AasDocument[]>([])
const version = ref<number | null>(null)
const qualification = ref<QualificationContext | null>(null)
const selectedDocumentId = ref('')
const selectedElementKey = ref('')
const selectedParentKey = ref('')
const operation = ref<'UPDATE' | 'CREATE' | 'DELETE'>('UPDATE')
const proposed = ref('')
const newIdShort = ref('')
const newValueType = ref('xs:string')
const busy = ref(false)
const error = ref('')
const history = ref<GovernanceResult[]>([])

function walkElements(document: AasDocument): ElementOption[] {
  const result: ElementOption[] = []
  function walk(elements: AasElement[], prefix: string) {
    for (const element of elements) {
      if (!element || typeof element.idShort !== 'string' || !element.idShort) continue
      const path = prefix ? prefix + '.' + element.idShort : element.idShort
      result.push({
        key: document.id + '#' + path,
        document,
        path,
        parentPath: prefix,
        element
      })
      if (element.modelType === 'SubmodelElementCollection' && Array.isArray(element.value)) {
        walk(element.value as AasElement[], path)
      }
    }
  }
  walk(document.submodelElements || [], '')
  return result
}

const elements = computed(() => documents.value.flatMap(walkElements))
const selectedDocument = computed(() => documents.value.find(d => d.id === selectedDocumentId.value))
const documentElements = computed(() => elements.value.filter(e => e.document.id === selectedDocumentId.value))
const selectedElement = computed(() => elements.value.find(e => e.key === selectedElementKey.value))
const parentCollections = computed(() => documentElements.value.filter(
  e => e.element.modelType === 'SubmodelElementCollection' && Array.isArray(e.element.value)
))
const selectedParent = computed(() => parentCollections.value.find(e => e.key === selectedParentKey.value))
const editable = computed(() => {
  const element = selectedElement.value?.element
  return !!element && element.modelType === 'Property' && supportedValueTypes.includes(String(element.valueType || ''))
})
const supportedValueTypes = [
  'xs:string', 'xs:boolean', 'xs:byte', 'xs:short', 'xs:int', 'xs:integer',
  'xs:long', 'xs:decimal', 'xs:float', 'xs:double'
]
const canSubmit = computed(() => {
  if (busy.value || version.value === null || !selectedDocument.value) return false
  if (operation.value === 'CREATE') {
    return !!selectedParent.value && /^[A-Za-z][A-Za-z0-9_]*$/.test(newIdShort.value)
      && !documentElements.value.some(e => e.path === selectedParent.value!.path + '.' + newIdShort.value)
      && isValidValue(proposed.value, newValueType.value)
  }
  if (!selectedElement.value) return false
  if (operation.value === 'DELETE') return true
  return editable.value && isValidValue(proposed.value, String(selectedElement.value.element.valueType))
})

function isValidValue(value: string, valueType: string): boolean {
  if (valueType === 'xs:string') return true
  if (valueType === 'xs:boolean') return value === 'true' || value === 'false'
  if (['xs:byte', 'xs:short', 'xs:int', 'xs:integer', 'xs:long'].includes(valueType)) {
    return /^[-+]?\d+$/.test(value) && Number.isSafeInteger(Number(value))
  }
  if (['xs:decimal', 'xs:float', 'xs:double'].includes(valueType)) {
    return value.trim() !== '' && Number.isFinite(Number(value))
  }
  return false
}

function parseValue(value: string, valueType: string): string | number | boolean {
  if (valueType === 'xs:boolean') return value === 'true'
  if (['xs:byte', 'xs:short', 'xs:int', 'xs:integer', 'xs:long'].includes(valueType)) return Number(value)
  if (['xs:decimal', 'xs:float', 'xs:double'].includes(valueType)) return Number(value)
  return value
}

function selectDocument() {
  const first = documentElements.value[0]
  selectedElementKey.value = first?.key || ''
  const firstParent = parentCollections.value[0]
  selectedParentKey.value = firstParent?.key || ''
  loadSelectedValue()
}

function loadSelectedValue() {
  const element = selectedElement.value?.element
  proposed.value = element && element.value !== undefined ? String(element.value) : ''
}

watch(selectedDocumentId, () => selectDocument())
watch(selectedElementKey, () => loadSelectedValue())

function domainFor(document: AasDocument): string {
  const names: Record<string, string> = {
    AssetInventory: 'assetinventory',
    TEP_ProductCatalog: 'productcatalog'
  }
  const domain = names[document.idShort]
  if (!domain) throw new Error('No registered governance domain for Submodel ' + document.idShort)
  return domain
}

async function readJson(response: Response) {
  const data = await response.json().catch(() => ({}))
  if (!response.ok) throw new Error(data.error || data.detail || 'Request failed (' + response.status + ')')
  return data
}

async function load() {
  const [stateResponse, contextResponse] = await Promise.all([
    fetch('/api/governance/state'),
    fetch('/api/governance/context')
  ])
  const [state, context] = await Promise.all([readJson(stateResponse), readJson(contextResponse)])
  if (!Array.isArray(state.documents)) throw new Error('Governance state returned no document list')
  documents.value = state.documents
  version.value = state.version
  qualification.value = context
  if (!documents.value.some(d => d.id === selectedDocumentId.value)) {
    selectedDocumentId.value = documents.value[0]?.id || ''
  } else {
    selectDocument()
  }
  if (!selectedDocumentId.value) selectDocument()
}

async function refresh() {
  busy.value = true
  error.value = ''
  try {
    await load()
  } catch (e) {
    version.value = null
    qualification.value = null
    error.value = e instanceof Error ? e.message : String(e)
  } finally {
    busy.value = false
  }
}

async function submit() {
  if (!canSubmit.value || !selectedDocument.value || version.value === null) return
  const document = selectedDocument.value
  const element = selectedElement.value
  let path = ''
  let payload: Record<string, unknown> | undefined

  if (operation.value === 'CREATE') {
    if (!selectedParent.value) return
    path = selectedParent.value.path + '.' + newIdShort.value
    payload = {
      modelType: 'Property',
      idShort: newIdShort.value,
      valueType: newValueType.value,
      value: parseValue(proposed.value, newValueType.value)
    }
  } else if (element) {
    path = element.path
    if (operation.value === 'UPDATE') {
      payload = {
        ...element.element,
        value: parseValue(proposed.value, String(element.element.valueType))
      }
    }
  } else {
    return
  }

  const action = operation.value.toLowerCase()
  const description = operation.value === 'CREATE'
    ? 'Create ' + path
    : operation.value === 'DELETE'
      ? 'Delete ' + path
      : 'Update ' + path
  if (!window.confirm(description + ' in the configured governed repository?')) return

  const message = {
    header: { message_id: crypto.randomUUID(), source: 'TEP-NEXUS-UI' },
    domain: { name: domainFor(document), submodel_id: document.id },
    operation: { type: operation.value, id_short_path: path, expected_version: version.value },
    payload
  }

  busy.value = true
  error.value = ''
  try {
    const response = await fetch('/api/governance/change', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(message)
    })
    const data = await readJson(response) as GovernanceResult
    history.value.unshift(data)
    if (data.committed) {
      await load()
      operation.value = 'UPDATE'
    } else {
      // A rejected or deferred request is not treated as a committed state change.
      await refresh()
    }
  } catch (e) {
    version.value = null
    qualification.value = null
    error.value = (e instanceof Error ? e.message : String(e))
      + ' — outcome may be unconfirmed. Refresh and verify repository state before another submission. Message: '
      + message.header.message_id
  } finally {
    busy.value = false
  }
}

onMounted(refresh)
</script>

<template>
 <section class="panel governance">
  <div class="panel-title">
   <div><h2>SELiRA Automation Manager</h2><p>Native AAS changes · SC-01 · LP-01</p></div>
   <span class="pill">Version {{ version ?? 'unavailable' }}</span>
  </div>
  <p class="intro">Propose an engineering information change and review its qualification and admission outcome. Changes are applied only when the governance service confirms commitment.</p>

  <section class="qualification-context" aria-labelledby="qualification-context-title">
   <div class="context-heading">
    <div><h3 id="qualification-context-title">Qualification context</h3><p>Current server-supplied inputs for the committed snapshot.</p></div>
    <span class="context-tag">{{ qualification?.source === 'server_operator_attestation' ? 'Operator supplied' : 'Unavailable' }}</span>
   </div>
   <div v-if="qualification" class="context-grid">
    <article class="context-item">
     <strong>Information completeness</strong>
     <span class="context-value">{{ qualification.evidence_complete.length }} scope(s) attested complete</span>
     <ul v-if="qualification.evidence_complete.length"><li v-for="scope in qualification.evidence_complete" :key="scope">{{ scope }}</li></ul>
     <span v-else class="context-note">No completeness scopes are currently attested.</span>
    </article>
    <article class="context-item">
     <strong>Identity normalization</strong>
     <span class="context-value" :class="qualification.identity_normalized ? 'state-yes' : 'state-no'">{{ qualification.identity_normalized ? 'Confirmed by operator' : 'Not confirmed' }}</span>
    </article>
    <article class="context-item">
     <strong>Contract applicability</strong>
     <span class="context-value" :class="qualification.applicability_confirmed ? 'state-yes' : 'state-no'">{{ qualification.applicability_confirmed ? 'Confirmed by operator' : 'Not confirmed' }}</span>
    </article>
   </div>
   <p v-else class="context-footnote">Qualification context is unavailable. Refresh the governance state before submitting a change.</p>
   <p class="context-footnote">These values are operator-supplied attestations read from the configured server-side evidence source. The interface does not authenticate their truth or provenance.</p>
  </section>

  <div class="section-head"><div><h3>Engineering information</h3><p>Select the Submodel and element to change.</p></div></div>
  <label>Native AAS Submodel
   <select v-model="selectedDocumentId" :disabled="busy || !documents.length">
    <option value="" disabled>Select a Submodel</option>
    <option v-for="document in documents" :key="document.id" :value="document.id">{{ document.idShort }} · {{ document.id }}</option>
   </select>
  </label>
  <label>Change operation
   <select v-model="operation" :disabled="busy">
    <option value="UPDATE">Update existing element</option>
    <option value="CREATE">Create Property in collection</option>
    <option value="DELETE">Delete existing element</option>
   </select>
  </label>

  <template v-if="operation === 'CREATE'">
   <label>Parent collection
    <select v-model="selectedParentKey" :disabled="busy || !parentCollections.length">
     <option value="" disabled>Select a collection</option>
     <option v-for="parent in parentCollections" :key="parent.key" :value="parent.key">{{ parent.path }}</option>
    </select>
   </label>
   <label>New Property idShort
    <input v-model="newIdShort" :disabled="busy" placeholder="e.g. EngineeringNote" />
   </label>
   <label>Value type
    <select v-model="newValueType" :disabled="busy">
     <option v-for="type in supportedValueTypes" :key="type" :value="type">{{ type }}</option>
    </select>
   </label>
   <label>Property value
    <input v-model="proposed" :disabled="busy" :type="newValueType === 'xs:boolean' ? 'text' : 'text'" :placeholder="newValueType === 'xs:boolean' ? 'true or false' : 'Enter value'" />
   </label>
  </template>
  <template v-else>
   <label>Native AAS element
    <select v-model="selectedElementKey" :disabled="busy || !documentElements.length">
     <option value="" disabled>Select an element</option>
     <option v-for="entry in documentElements" :key="entry.key" :value="entry.key">{{ entry.path }} · {{ entry.element.modelType }}</option>
    </select>
   </label>
   <label v-if="operation === 'UPDATE'">Committed value
    <input :value="selectedElement?.element.value === undefined ? JSON.stringify(selectedElement?.element) : String(selectedElement.element.value)" readonly />
   </label>
   <label v-if="operation === 'UPDATE'">Proposed value
    <select v-if="selectedElement?.element.valueType === 'xs:boolean'" v-model="proposed" :disabled="busy || !editable">
     <option value="true">true</option><option value="false">false</option>
    </select>
    <input v-else v-model="proposed" :disabled="busy || !editable" />
   </label>
   <p v-if="operation === 'UPDATE' && selectedElement && !editable" class="context-note">This element type or value type is displayed but is not editable through this value editor.</p>
   <p v-if="operation === 'DELETE' && selectedElement" class="context-note">The selected element and its nested content, if any, will be removed from the proposed Submodel.</p>
  </template>

  <div class="action-row">
   <button class="primary" :disabled="!canSubmit" @click="submit">{{ busy ? 'Processing…' : operation === 'CREATE' ? 'Submit Property creation' : operation === 'DELETE' ? 'Submit element deletion' : 'Submit native AAS update' }}</button>
   <button class="secondary" :disabled="busy" @click="refresh">Refresh committed state</button>
  </div>
  <p v-if="error" class="error" role="alert">{{ error }}</p>

  <section class="results">
   <div class="section-head"><div><h3>Governance responses</h3><p>Responses received during this page session.</p></div></div>
   <p v-if="!history.length" class="context-note">No changes submitted in this page session.</p>
   <article v-for="result in history" :key="result.message_id" class="response">
    <div class="response-head">
     <strong>{{ result.decision }}</strong>
     <span class="decision-tag" :class="result.committed ? 'state-yes' : 'state-no'">{{ result.committed ? 'Committed' : 'Not committed' }}</span>
    </div>
    <p>Repository version: {{ result.repository_version }}</p>
    <p>Triggered policies: {{ result.triggered_policies.join(', ') || 'None reported' }}</p>
    <div v-if="result.evaluated_contracts.length" class="contract-list">
     <div v-for="contract in result.evaluated_contracts" :key="contract.contract_id">
      <strong>{{ contract.contract_id }}</strong><span class="verdict">{{ contract.verdict }}</span>
     </div>
    </div>
    <small>Message ID: {{ result.message_id }}</small>
   </article>
  </section>
 </section>
</template>

<style scoped>
.governance{display:grid;gap:16px}.governance label{display:grid;gap:6px;font-weight:600}.governance select,.governance input{width:100%;box-sizing:border-box;padding:10px;border:1px solid #8794a3;border-radius:6px;max-width:100%;color:inherit;background:transparent;font:inherit}.governance button{justify-self:start}.intro{margin:0;opacity:.86}.qualification-context{border:1px solid #8794a3;border-radius:8px;padding:16px;display:grid;gap:12px}.context-heading,.response-head{display:flex;justify-content:space-between;align-items:flex-start;gap:12px}.context-heading h3,.section-head h3{margin:0 0 4px}.context-heading p,.section-head p{margin:0;font-size:.9rem;opacity:.8}.context-tag,.decision-tag,.verdict{border:1px solid #8794a3;border-radius:999px;padding:4px 9px;font-size:.78rem;white-space:nowrap}.context-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(190px,1fr));gap:10px}.context-item{border:1px solid #8794a3;border-radius:6px;padding:12px;display:grid;gap:7px;align-content:start;overflow-wrap:anywhere}.context-item ul{margin:0;padding-left:18px;font-size:.82rem}.context-value{font-size:.9rem}.context-note,.context-footnote{font-size:.82rem;opacity:.76;margin:0}.context-footnote{border-top:1px solid #8794a3;padding-top:10px}.state-yes{color:#23834b}.state-no{color:#b66b24}.section-head{display:flex;justify-content:space-between;align-items:center}.action-row{display:flex;gap:10px;flex-wrap:wrap}.error{color:#b42318;overflow-wrap:anywhere}.results{display:grid;gap:10px}.response{border-top:1px solid #8794a3;padding:12px 0;display:grid;gap:7px;overflow-wrap:anywhere}.response p{margin:0;font-size:.9rem}.response small{opacity:.72}.contract-list{display:grid;gap:6px}.contract-list>div{display:flex;justify-content:space-between;align-items:center;gap:10px}.verdict{font-weight:700}.decision-tag{font-weight:600}
</style>
