<script setup lang="ts">
import { computed, ref } from 'vue'
import { dexpiOpcuaMappings } from '../data/dexpiOpcuaMappings'

const search = ref('')
const kind = ref('All')
const filtered = computed(() => dexpiOpcuaMappings.filter(item =>
  (kind.value === 'All' || item.kind === kind.value) &&
  Object.values(item).join(' ').toLowerCase().includes(search.value.trim().toLowerCase())
))
</script>

<template>
 <section class="panel" style="margin-bottom:16px">
  <div class="panel-title"><div><h2>DEXPI → OPC UA function mapping</h2><p>Engineering functions linked to TEP simulator signal nodes</p></div><span class="pill">{{ filtered.length }} / {{ dexpiOpcuaMappings.length }}</span></div>
  <p class="catalog-disclaimer">These are provisional engineering matches, not runtime-verified OPC UA bindings. The NodeIds use the stable namespace URI urn:process-sim:opcua. Restart the OPC UA server after updating its code. No device installation or physical sensor identity is implied.</p>
  <div style="display:flex;gap:12px;flex-wrap:wrap;margin-bottom:12px">
   <label>Function type <select v-model="kind" aria-label="Filter function type"><option>All</option><option>Instrumentation</option><option>Actuating</option></select></label>
   <label>Search <input v-model="search" aria-label="Search DEXPI OPC UA mappings" placeholder="FI_101, XMEAS9, reactor..." /></label>
  </div>
  <div style="overflow-x:auto;max-height:480px;overflow-y:auto">
   <table style="width:100%;text-align:left;border-collapse:collapse">
    <thead><tr><th>DEXPI function</th><th>Type</th><th>TEP signal</th><th>OPC UA NodeId</th><th>Status</th></tr></thead>
    <tbody>
     <tr v-for="item in filtered" :key="item.LocalId">
      <td><strong>{{ item.LocalId }}</strong><div>{{ item.name }}</div></td>
      <td>{{ item.kind }}</td>
      <td><code>{{ item.kind === 'Instrumentation' ? item.MeasuredVariable : item.ActuatedVariable }}</code></td>
      <td><code style="overflow-wrap:anywhere">{{ item.OPCUANodeId }}</code><div><small>{{ item.OPCUABrowsePath }}</small></div></td>
      <td><small>{{ item.OPCUAMappingStatus }}</small></td>
     </tr>
    </tbody>
   </table>
  </div>
  <p v-if="!filtered.length" class="empty">No mappings match the current filter.</p>
  <p class="catalog-disclaimer">Mapping table is bundled from the versioned DEXPI example JSON; the engineering knowledge graph below is loaded independently from GraphDB. Rebuild the frontend when mappings change.</p>
 </section>
</template>
