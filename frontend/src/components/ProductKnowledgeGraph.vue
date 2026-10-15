<script setup lang="ts">
import { computed, ref } from 'vue'
import { Network, RotateCcw, ZoomIn, ZoomOut } from 'lucide-vue-next'
import catalog from '../data/product_catalog.json'
type E = { idShort: string; modelType: string; value?: string | E[] }
type N = { id: string; label: string; kind: string; value: string; x: number; y: number }
type R = { from: string; to: string; predicate: string }
const props = defineProps<{ product: { id: string; partNumber: string } }>()
const raw = catalog.submodelElements[0].value as unknown as E[]
const nodes = ref<N[]>([])
const edges = ref<R[]>([])
const focused = ref('')
const zoom = ref(1)
const allProducts = ref(false)
const literals = ref(true)
const dragging = ref<{id:string;x:number;y:number}|null>(null)
const selected = computed(() => nodes.value.find(n => n.id === focused.value))
const connections = computed(() => edges.value.filter(e => e.from === focused.value || e.to === focused.value))
const get = (id:string) => nodes.value.find(n => n.id === id)
function node(id:string,label:string,kind:string,value:string,x:number,y:number) {
  if (!get(id)) nodes.value.push({id,label,kind,value,x,y})
}
function edge(from:string,to:string,predicate:string) {
  if (!edges.value.some(e=>e.from===from && e.to===to && e.predicate===predicate)) edges.value.push({from,to,predicate})
}
function expand(id:string) {
  const current = get(id)
  if (!current) return
  if (id==='catalog') {
    node('products','Products','Collection','AAS SubmodelElementCollection',320,280)
    edge('catalog','products','hasProducts')
  } else if (id==='products') {
    const ids = allProducts.value ? raw.map(p=>p.idShort) : [props.product.id]
    ids.forEach((p,i)=>{
      node('p:'+p,p,'Product','AAS SubmodelElementCollection',570+(i%3)*170,160+Math.floor(i/3)*180)
      edge('products','p:'+p,'hasProduct')
    })
  } else if (id.startsWith('p:') && !id.includes('/')) {
    const fields = (raw.find(p=>p.idShort===id.slice(2))?.value as E[]) || []
    fields.forEach((f,i)=>{
      const a=i*Math.PI*2/Math.max(fields.length,1)
      const fid=id+'/'+f.idShort
      node(fid,f.idShort,f.modelType,typeof f.value==='string'?f.value:'AAS collection',610+Math.cos(a)*230,330+Math.sin(a)*210)
      edge(id,fid,'has'+f.idShort)
    })
  } else if (id.endsWith('/TechnicalProperties')) {
    const product=raw.find(p=>p.idShort===id.split('/')[0].slice(2))
    const field=((product?.value as E[])||[]).find(f=>f.idShort==='TechnicalProperties')
    const properties=(field?.value as E[])||[]
    properties.forEach((p,i)=>{
      const a=i*Math.PI*2/Math.max(properties.length,1)
      const pid=id+'/'+p.idShort
      node(pid,p.idShort,'Property',typeof p.value==='string'?p.value:'',590+Math.cos(a)*340,340+Math.sin(a)*270)
      edge(id,pid,'hasProperty')
    })
  } else if (current.kind==='Property' && literals.value && current.value) {
    const vid=id+'/literal'
    node(vid,current.value,'Literal',current.value,Math.min(1010,current.x+150),Math.min(680,current.y+85))
    edge(id,vid,'value')
  }
  focused.value=id
}
function reset() {
  nodes.value=[];edges.value=[];zoom.value=1
  node('catalog','ProductCatalog','Submodel',String(catalog.id),100,280)
  expand('catalog');expand('products');expand('p:'+props.product.id)
  focused.value='p:'+props.product.id
}
function start(e:PointerEvent,n:N) {
  if(e.button!==0)return
  dragging.value={id:n.id,x:e.clientX,y:e.clientY}
  ;(e.currentTarget as Element).setPointerCapture(e.pointerId)
}
function move(e:PointerEvent) {
  if(!dragging.value)return
  const n=get(dragging.value.id)
  if(!n)return
  const svg=(e.currentTarget as SVGElement).ownerSVGElement
  const factor=1100/(svg?.getBoundingClientRect().width||1100)
  n.x=Math.max(60,Math.min(1040,n.x+(e.clientX-dragging.value.x)*factor))
  n.y=Math.max(50,Math.min(690,n.y+(e.clientY-dragging.value.y)*factor))
  dragging.value.x=e.clientX;dragging.value.y=e.clientY
}
reset()
</script>
<template>
 <div class="product-knowledge">
  <div class="graph-toolbar"><span class="pill amber-pill">GraphDB-style preview · AAS snapshot</span><button class="secondary" @click="reset"><RotateCcw :size="14"/> Reset graph</button></div>
  <p class="graph-explanation">Interactive node-edge graph with labeled relationships. Click nodes to expand, drag to rearrange, and inspect connections. Predicate labels are AAS-derived previews, not verified RDF IRIs.</p>
  <div class="graph-filters">
   <label><input v-model="allProducts" type="checkbox" @change="reset"/> All eight products</label>
   <label><input v-model="literals" type="checkbox"/> Literal nodes</label>
   <button class="secondary" aria-label="Zoom out" @click="zoom=Math.max(.6,+(zoom-.1).toFixed(1))"><ZoomOut :size="14"/></button><span>{{ Math.round(zoom*100) }}%</span>
   <button class="secondary" aria-label="Zoom in" @click="zoom=Math.min(1.6,+(zoom+.1).toFixed(1))"><ZoomIn :size="14"/></button>
  </div>
  <div class="graph-canvas graph-rdf-scroll" role="group" :aria-label="'ProductCatalog graph for '+product.id">
   <svg viewBox="0 0 1100 740" :width="1100*zoom" :height="740*zoom" role="img">
    <defs><marker id="product-rdf-arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6" markerHeight="6" orient="auto"><path d="M0 0 L10 5 L0 10z" fill="#598fa8"/></marker></defs>
    <g v-for="e in edges" :key="e.from+'|'+e.to">
     <template v-if="get(e.from) && get(e.to)">
      <line :x1="get(e.from)!.x" :y1="get(e.from)!.y" :x2="get(e.to)!.x" :y2="get(e.to)!.y" stroke="#598fa8" stroke-width="1.5" marker-end="url(#product-rdf-arrow)"/>
      <text :x="(get(e.from)!.x+get(e.to)!.x)/2" :y="(get(e.from)!.y+get(e.to)!.y)/2-8" fill="#8edbd9" font-size="10" text-anchor="middle" stroke="#0b1829" stroke-width="3" paint-order="stroke">{{ e.predicate }}</text>
     </template>
    </g>
    <g v-for="n in nodes" :key="n.id" class="graph-node graph-rdf-node" :class="{'graph-node-active':focused===n.id}" tabindex="0" role="button" :aria-label="n.kind+': '+n.label" @click="expand(n.id)" @keydown.enter.prevent="expand(n.id)" @pointerdown="start($event,n)" @pointermove="move" @pointerup="dragging=null" @pointercancel="dragging=null">
     <circle :cx="n.x" :cy="n.y" :r="n.kind==='Literal'?34:46" :class="n.kind==='Literal'?'graph-rdf-literal':n.kind==='Property'?'graph-rdf-property':'graph-rdf-resource'"/>
     <text :x="n.x" :y="n.y-3" fill="#effaff" text-anchor="middle" font-size="10" font-weight="600" pointer-events="none">{{ n.label.length>17?n.label.slice(0,16)+'…':n.label }}</text>
     <text :x="n.x" :y="n.y+12" fill="#b5d5e2" text-anchor="middle" font-size="9" pointer-events="none">{{ n.kind }}</text>
     <title>{{ n.label }}: {{ n.value }}</title>
    </g>
   </svg>
  </div>
  <div class="graph-inspector" aria-live="polite"><div class="panel-title"><h2><Network :size="15"/> Node inspector</h2><span v-if="selected" class="pill">{{ selected.kind }}</span></div><template v-if="selected"><div class="catalog-property"><span>Resource</span><strong class="catalog-wrap">{{ selected.label }}</strong></div><div class="catalog-property"><span>Value / source</span><strong class="catalog-wrap">{{ selected.value }}</strong></div><div class="catalog-property"><span>Visible edges</span><strong>{{ connections.length }}</strong></div></template></div>
  <p class="catalog-disclaimer">GraphDB-style local visualization only. Live RDF/SPARQL and actual ontology predicates require GraphDB integration.</p>
 </div>
</template>
