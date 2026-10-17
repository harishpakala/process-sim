"""Small dependency-free HTTP bridge between TEP NEXUS and GraphDB.

Run with: python -m process_sim.api.server
The browser sends SPARQL SELECT queries to /api/kg/select; only this service
knows the GraphDB URL. Bind to loopback by default and put authentication in
front of this API before any public deployment.
"""
from __future__ import annotations

import asyncio
import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

GRAPHDB_ENDPOINT = os.environ.get("GRAPHDB_SPARQL_ENDPOINT", "http://localhost:7200/repositories/AAS")
MAX_BODY = 100_000
MAX_RESPONSE = 8_000_000


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/api/simulation/history":
            from process_sim.api.historian import history
            self.send_json(200, history())
            return
        if self.path == "/api/simulation/fault-events":
            from process_sim.api.fault_events import list_events
            self.send_json(200, {"events": list_events()})
            return
        if self.path == "/api/simulation/faults":
            try:
                from process_sim.api.opcua_client import faults_list
                self.send_json(200, asyncio.run(faults_list()))
            except Exception as exc:
                self.send_json(503, {"error": f"OPC UA fault listing failed: {exc}"})
            return
        if self.path == "/api/simulation/status":
            try:
                from process_sim.api.opcua_client import snapshot
                self.send_json(200, asyncio.run(snapshot()))
            except Exception as exc:
                self.send_json(503, {"connected": False, "error": f"OPC UA unavailable: {exc}"})
            return
        if self.path != "/api/health":
            self.send_json(404, {"error": "Not found"})
            return
        self.send_json(200, {"status": "ok", "service": "process-sim-api"})

    def do_POST(self):
        if self.path == "/api/simulation/faults":
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if not 0 < length <= 4096:
                    self.send_json(400, {"error": "Invalid request length"})
                    return
                payload = json.loads(self.rfile.read(length))
                if not isinstance(payload, dict):
                    raise ValueError("Expected a JSON object")
                from process_sim.api.opcua_client import fault_command
                action = payload.get("action")
                if action not in ("inject", "clear", "clear_all"):
                    raise ValueError("Unsupported fault action")
                from process_sim.api.opcua_client import snapshot, faults_list
                before = asyncio.run(faults_list()) if action != "inject" else {"faults": []}
                result = asyncio.run(fault_command(action, payload))
                if result["success"]:
                    from process_sim.api.fault_events import record
                    try:
                        now = float(asyncio.run(snapshot())["simulation"]["TimeHours"])
                    except Exception:
                        now = None
                    if now is None:
                        self.send_json(200, {**result, "warning": "Fault operation succeeded but event timestamp could not be recorded"})
                        return
                    if action == "clear_all":
                        for fault in before["faults"]:
                            record("clear", fault["fault_id"], now, fault.get("target", ""))
                    else:
                        known = next((f for f in before["faults"] if f["fault_id"] == payload.get("faultId")), None)
                        record(action, payload.get("faultId", ""), now, payload.get("target", "") or (known or {}).get("target", ""))
                self.send_json(200 if result["success"] else 502, result)
            except (ValueError, TypeError) as exc:
                self.send_json(400, {"error": str(exc)})
            except Exception as exc:
                self.send_json(503, {"error": f"OPC UA fault command failed: {exc}"})
            return
        if self.path == "/api/simulation/control":
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if not 0 < length <= 1024:
                    self.send_json(400, {"error": "Invalid request length"})
                    return
                action = json.loads(self.rfile.read(length)).get("action")
                if action not in ("Start", "Stop", "Reset"):
                    self.send_json(400, {"error": "Unsupported simulation action"})
                    return
                from process_sim.api.opcua_client import control
                result = asyncio.run(control(action))
                self.send_json(200 if result["success"] else 502, result)
            except Exception as exc:
                self.send_json(503, {"error": f"OPC UA command failed: {exc}"})
            return
        if self.path != "/api/kg/select":
            self.send_json(404, {"error": "Not found"})
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if not 0 < length <= MAX_BODY:
                self.send_json(413, {"error": "Invalid or oversized request"})
                return
            body = json.loads(self.rfile.read(length))
            query = body.get("query")
            if not isinstance(query, str) or not query.lstrip().upper().startswith(("SELECT ", "SELECT\n", "PREFIX ", "BASE ")):
                self.send_json(400, {"error": "A SPARQL SELECT query is required"})
                return
            # Reject SPARQL update commands, even after PREFIX/BASE declarations.
            import re
            if re.search(r"\b(INSERT|DELETE|LOAD|CLEAR|DROP|CREATE|MOVE|COPY|ADD)\b", query, re.I) or not re.search(r"\bSELECT\b", query, re.I):
                self.send_json(400, {"error": "Only read-only SELECT queries are supported"})
                return
            request = Request(
                GRAPHDB_ENDPOINT,
                data=urlencode({"query": query}).encode("utf-8"),
                headers={"Accept": "application/sparql-results+json", "Content-Type": "application/x-www-form-urlencoded"},
                method="POST",
            )
            try:
                with urlopen(request, timeout=30) as response:
                    payload = response.read(MAX_RESPONSE + 1)
                    if len(payload) > MAX_RESPONSE:
                        self.send_json(502, {"error": "GraphDB response too large"})
                        return
                    parsed = json.loads(payload)
                    if not isinstance(parsed.get("results", {}).get("bindings"), list):
                        self.send_json(502, {"error": "GraphDB returned unexpected SPARQL JSON"})
                        return
                    self.send_json(200, parsed)
            except HTTPError as exc:
                detail = exc.read(1200).decode("utf-8", errors="replace")
                self.send_json(502, {"error": f"GraphDB HTTP {exc.code}: {detail}"})
            except (URLError, TimeoutError) as exc:
                self.send_json(502, {"error": f"GraphDB unavailable: {exc}"})
        except (ValueError, TypeError, json.JSONDecodeError) as exc:
            self.send_json(400, {"error": f"Invalid request: {exc}"})
        except Exception:
            self.send_json(500, {"error": "Unexpected backend error"})

    def send_json(self, status, data):
        payload = json.dumps(data).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)


def main():
    host = os.environ.get("PROCESS_SIM_API_HOST", "127.0.0.1")
    port = int(os.environ.get("PROCESS_SIM_API_PORT", "8000"))
    from process_sim.api.historian import start
    start()
    server = ThreadingHTTPServer((host, port), Handler)
    print(f"TEP NEXUS API listening at http://{host}:{port}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
