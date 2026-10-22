<script setup lang="ts">
import { computed, ref } from 'vue'
import { opcuaConnectivityMappings } from '../data/opcuaConnectivityMappings'
const search = ref('')
const matches = computed(() => opcuaConnectivityMappings.filter(x => Object.values(x).join(' ').toLowerCase().includes(search.value.toLowerCase())))
</script>
<template>
 <section class="panel">
  <div class="panel-title"><div><h2>OPC UA Connectivity</h2><p>Standalone AAS mapping · DEXPI and ECAD remain unchanged</p></div><span class="pill">{{ matches.length }} / {{ opcuaConnectivityMappings.length }}</span></div>
  <p class="catalog-disclaimer">Provisional engineering signal mappings, not live-verified connections. Endpoint example: opc.tcp://localhost:4841/process-sim/ · Namespace: urn:process-sim:opcua. ECAD ConnectionPoint association is UNMAPPED pending verified device/interface evidence.</p>
  <label class="search"><input v-model="search" placeholder="Search function, XMEAS, XMV, NodeId…" aria-label="Search OPC UA mappings"/></label>
  <div style="overflow-x:auto;max-height:540px;overflow-y:auto">
   <table style="width:100%;text-align:left">
    <thead><tr><th>Engineering function</th><th>Signal</th><th>NodeId</th><th>Direction</th><th>Status</th></tr></thead>
    <tbody><tr v-for="item in matches" :key="item.name"><td><strong>{{ item.EngineeringFunctionId }}</strong><div><small>{{ item.name }}</small></div></td><td>{{ item.SignalName }}</td><td><code style="overflow-wrap:anywhere">{{ item.OPCUANodeId }}</code></td><td>{{ item.SignalDirection }}</td><td>{{ item.MappingStatus }}</td></tr></tbody>
   </table>
  </div>
  <p v-if="!matches.length" class="empty">No matching mappings.</p>
  <p class="catalog-disclaimer">This view uses a bundled snapshot of the AAS instance, not live OPC UA verification or GraphDB results.</p>
 </section>
</template>
