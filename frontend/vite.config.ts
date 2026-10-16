import { defineConfig } from "vite";
import vue from "@vitejs/plugin-vue";

// Development-only proxy: browser requests /kg/repositories/tep -> GraphDB.
// Override VITE_KG_SPARQL_ENDPOINT in the frontend environment for deployments.
export default defineConfig({
  plugins: [vue()],
  server: { proxy: { "/kg": { target: process.env.GRAPHDB_URL || "http://localhost:7200", changeOrigin: true, rewrite: path => path.replace(/^\/kg/, "") } } }
});
