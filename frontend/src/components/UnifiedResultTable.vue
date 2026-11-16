<script setup lang="ts">
import { computed } from 'vue'

const props = defineProps<{ rows: Array<Record<string, unknown>> }>()
const columns = computed(() => [...new Set(props.rows.flatMap(row => Object.keys(row)))])
const cell = (value: unknown): string =>
 value == null ? '—' : typeof value === 'string' ? value : JSON.stringify(value)
</script>

<template>
 <div v-if="rows.length" class="results-scroll">
  <table class="results-table">
   <thead><tr><th scope="col">#</th><th v-for="column in columns" :key="column" scope="col">{{column}}</th></tr></thead>
   <tbody><tr v-for="(row, index) in rows" :key="index">
    <td>{{index + 1}}</td>
    <td v-for="column in columns" :key="column" :title="cell(row[column])">{{cell(row[column])}}</td>
   </tr></tbody>
  </table>
 </div>
 <p v-else class="empty-results">No rows returned.</p>
</template>

<style scoped>
.results-scroll { max-width: 100%; max-height: 520px; overflow: auto; border: 1px solid #334a62; border-radius: 8px; }
.results-table { border-collapse: collapse; width: 100%; min-width: 420px; font-size: 13px; }
.results-table th, .results-table td { padding: 10px 12px; text-align: left; border-bottom: 1px solid #334a62; white-space: nowrap; }
.results-table thead { position: sticky; top: 0; background: #172d42; }
.results-table tbody tr:nth-child(even) { background: rgba(100,140,180,.08); }
.empty-results { opacity: .8; }
</style>
