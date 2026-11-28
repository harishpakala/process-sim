"""Small dependency-free HTTP bridge between TEP NEXUS and GraphDB.

Run with: python -m process_sim.api.server
The browser sends SPARQL SELECT queries to /api/kg/select; only this service
knows the GraphDB URL. Bind to loopback by default and put authentication in
front of this API before any public deployment.
"""

# Created: 2026-10-17
# Author: Harish
from __future__ import annotations

import asyncio
import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlsplit, parse_qs
from urllib.request import Request, urlopen

GRAPHDB_ENDPOINT = os.environ.get("GRAPHDB_SPARQL_ENDPOINT", "http://localhost:7200/repositories/AAST")
MAX_BODY = 100_000
MAX_RESPONSE = 8_000_000


class Handler(BaseHTTPRequestHandler):
    governance = None

    def do_GET(self):
        if urlsplit(self.path).path == "/api/governance/context":
            if self.governance is None:
                self.send_json(503, {"error": "Governance disabled"})
                return
            try:
                self.send_json(200, self.governance.qualification_context())
            except Exception:
                self.send_json(503, {"error": "Qualification context unavailable; check governance and reconciliation status"})
            return
        if urlsplit(self.path).path == "/api/governance/state":
            if self.governance is None:
                self.send_json(503, {"error": "Governance disabled"})
                return
            try:
                docs, _, version = self.governance.snapshot()
                self.send_json(200, {"version": version, "documents": list(docs.values()), "templates": self.governance.template_snapshot()})
            except Exception:
                self.send_json(503, {"error": "Governance unavailable; check reconciliation status"})
            return
        if urlsplit(self.path).path == "/api/ai/shacl/benchmark/questions":
            try:
                from pathlib import Path
                manifest = Path(__file__).resolve().parents[3] / "benchmarks/shacl_phase1/benchmark_queries_aast_candidate.json"
                data = json.loads(manifest.read_text(encoding="utf-8"))
                scenarios = data["scenarios"]
                if not isinstance(scenarios, list):
                    raise ValueError("Invalid SHACL benchmark manifest")
                self.send_json(200, {
                    "benchmark_id": data.get("benchmark_id"),
                    "scenario_count": len(scenarios),
                    "query_count": sum(len(s["paraphrases"]) for s in scenarios),
                    "scenarios": scenarios,
                })
            except (OSError, ValueError, KeyError, TypeError) as exc:
                self.send_json(503, {"error": f"SHACL benchmark catalog unavailable: {exc}"})
            return
        if urlsplit(self.path).path == "/api/ai/vtkg/historian/runs":
            try:
                from process_sim.api.vtkg_query import discover_historian_runs
                self.send_json(200, discover_historian_runs())
            except Exception:
                import logging
                logging.exception("Historian run discovery failed")
                self.send_json(503, {"error": "Historian run discovery unavailable; check backend logs"})
            return
        if urlsplit(self.path).path == "/api/ai/vtkg/historian/measurement-types":
            try:
                from process_sim.api.signal_historian import discover_measurement_types
                self.send_json(200, discover_measurement_types())
            except Exception:
                import logging
                logging.exception("Measurement type discovery failed")
                self.send_json(503, {"error": "Measurement types unavailable; apply signal metadata migration"})
            return
        if urlsplit(self.path).path == "/api/ai/vtkg/historian/signals":
            try:
                from process_sim.api.signal_historian import discover_signals
                ids = parse_qs(urlsplit(self.path).query).get("run_id", [])
                if len(ids) != 1:
                    raise ValueError("Exactly one run_id is required")
                kinds = parse_qs(urlsplit(self.path).query).get("measurement_type", [])
                if len(kinds) > 1:
                    raise ValueError("At most one measurement_type is allowed")
                self.send_json(200, discover_signals(ids[0], measurement_type=kinds[0] if kinds else None))
            except ValueError as exc:
                self.send_json(400, {"error": str(exc)})
            except Exception:
                import logging
                logging.exception("Signal discovery failed")
                self.send_json(503, {"error": "Signal discovery unavailable; check backend logs"})
            return
        if urlsplit(self.path).path == "/api/ai/vtkg/historian/functions":
            try:
                from process_sim.api.vtkg_query import discover_historian_functions
                ids = parse_qs(urlsplit(self.path).query).get("run_id", [])
                if len(ids) != 1:
                    raise ValueError("Exactly one run_id is required")
                domains = parse_qs(urlsplit(self.path).query).get("domain", ["DEXPI"])
                if len(domains) != 1:
                    raise ValueError("Exactly one domain is required")
                self.send_json(200, discover_historian_functions(ids[0], domain=domains[0]))
            except ValueError as exc:
                self.send_json(400, {"error": str(exc)})
            except Exception:
                import logging
                logging.exception("Historian function discovery failed")
                self.send_json(503, {"error": "Historian function discovery unavailable; check backend logs"})
            return

        if urlsplit(self.path).path == "/api/ai/vtkg/functions":
            try:
                from process_sim.api.vtkg_query import discover_functions, VtkgUnavailable
                params = parse_qs(urlsplit(self.path).query)
                run_ids = params.get("run_id", [])
                if len(run_ids) != 1:
                    raise ValueError("Exactly one run_id is required")
                self.send_json(200, discover_functions(run_ids[0]))
            except ValueError as exc:
                self.send_json(400, {"error": str(exc)})
            except (VtkgUnavailable, OSError, RuntimeError, KeyError) as exc:
                self.send_json(503, {"error": f"VTKG function discovery unavailable: {exc}"})
            return
        if urlsplit(self.path).path == "/api/ai/benchmarks/42/questions":
            try:
                from process_sim.api.frozen_benchmark import pilot_questions
                self.send_json(200, pilot_questions())
            except (OSError, ValueError) as exc:
                self.send_json(503, {"error": str(exc)})
            return
        if urlsplit(self.path).path == "/api/ai/benchmarks/37/questions":
            try:
                from process_sim.api.frozen_benchmark import questions
                self.send_json(200, questions())
            except (OSError, ValueError) as exc:
                self.send_json(503, {"error": str(exc)})
            return
        if urlsplit(self.path).path == "/api/ai/benchmarks/questions":
            try:
                from process_sim.api.benchmark_reports import list_questions
                self.send_json(200, list_questions())
            except (OSError, ValueError) as exc:
                self.send_json(503, {"error": f"Benchmark questions unavailable: {exc}"})
            return
        if urlsplit(self.path).path == "/api/ai/benchmarks/reports":
            try:
                from process_sim.api.benchmark_reports import list_reports
                self.send_json(200, list_reports())
            except (OSError, ValueError) as exc:
                self.send_json(503, {"error": f"Benchmark reports unavailable: {exc}"})
            return
        if urlsplit(self.path).path in ("/api/ai/q13/ontology/live/status", "/api/ai/q13/ontology/live/result"):
            from process_sim.api import q13_live
            if os.getenv("TEP_Q13_LIVE_ENABLED") != "1":
                self.send_json(503, {"error": "Live Q13 is disabled"})
                return
            if urlsplit(self.path).path.endswith("/status"):
                self.send_json(200, q13_live.status())
            else:
                try:
                    self.send_json(200, q13_live.result())
                except LookupError as exc:
                    self.send_json(409, {"error": str(exc)})
                except (OSError, ValueError) as exc:
                    self.send_json(503, {"error": str(exc)})
            return
        if urlsplit(self.path).path == "/api/ai/q13/ontology/result":
            # Read-only integration of an explicitly configured, completed audit.
            # This does not run Ollama or GraphDB on the request thread.
            try:
                from pathlib import Path
                configured = os.environ.get("TEP_Q13_ONTOLOGY_AUDIT")
                if not configured:
                    self.send_json(503, {"error": "Set TEP_Q13_ONTOLOGY_AUDIT to a completed Q13 audit JSON"})
                    return
                source = Path(configured).expanduser().resolve()
                if not source.is_file() or source.stat().st_size > 8_000_000:
                    self.send_json(503, {"error": "Configured Q13 audit is missing or too large"})
                    return
                audit = json.loads(source.read_text(encoding="utf-8"))
                if not isinstance(audit, dict) or not audit.get("method", "").startswith("q13_v9_6_"):
                    raise ValueError("Configured file is not a Q13 ontology-guided audit")
                domains = audit.get("domains", [])
                acceptance = audit.get("acceptance", {})
                if not isinstance(domains, list) or not isinstance(acceptance, dict):
                    raise ValueError("Invalid Q13 audit structure")
                if not audit.get("final_answer") or not acceptance.get("six_domain_coverage"):
                    self.send_json(409, {"error": "Q13 audit is incomplete"})
                    return
                self.send_json(200, {
                    "question": audit.get("question"),
                    "answer": audit["final_answer"],
                    "status": audit.get("status"),
                    "method": audit.get("method"),
                    "synthesisMode": audit.get("synthesis_mode"),
                    "fallbackReason": audit.get("fallback_reason"),
                    "acceptance": acceptance,
                    "historian": audit.get("historian"),
                    "domains": [{
                        "domain": d.get("domain"),
                        "status": d.get("status"),
                        "summarySource": (d.get("finding") or {}).get("summary_source"),
                        "verifiedTriples": d.get("verified_triples", []),
                        "finding": d.get("finding"),
                    } for d in domains],
                })
            except (ValueError, TypeError, json.JSONDecodeError) as exc:
                self.send_json(422, {"error": f"Invalid Q13 audit: {exc}"})
            except OSError as exc:
                self.send_json(503, {"error": f"Q13 audit unavailable: {exc}"})
            return
        if urlsplit(self.path).path == "/api/ai/paper/questions":
            try:
                from process_sim.api.paper_query import questions
                self.send_json(200, {"questions": questions()})
            except Exception as exc:
                self.send_json(503, {"error": f"Paper questions unavailable: {exc}"})
            return
        if urlsplit(self.path).path == '/api/engineering/physical-bom/revisions':
            try:
                from process_sim.api.physical_bom import list_revisions
                self.send_json(200, list_revisions())
            except Exception as exc:
                self.send_json(503, {'error': f'Physical BOM unavailable: {exc}'})
            return
        if urlsplit(self.path).path == '/api/engineering/reviews':
            try:
                from process_sim.api.engineering_reviews import list_events
                self.send_json(200, list_events())
            except Exception as exc:
                self.send_json(503, {'error': f'Engineering review store unavailable: {exc}'})
            return
        if urlsplit(self.path).path == "/api/semantic/asset-specifications":
            try:
                from process_sim.api.asset_specifications import asset_specifications
                params = parse_qs(urlsplit(self.path).query)
                asset_id = params.get("assetId", [""])[0]
                self.send_json(200, asset_specifications(asset_id, GRAPHDB_ENDPOINT))
            except ValueError as exc:
                self.send_json(400, {"error": str(exc)})
            except LookupError as exc:
                self.send_json(404, {"error": str(exc)})
            except Exception as exc:
                self.send_json(503, {"error": f"GraphDB asset specifications unavailable: {exc}"})
            return
        if urlsplit(self.path).path == "/api/simulation/runs":
            try:
                from process_sim.api.timeseries import query_runs
                params = parse_qs(urlsplit(self.path).query)
                limit = int(params.get("limit", ["100"])[0])
                self.send_json(200, {"runs": query_runs(limit)})
            except ValueError as exc:
                self.send_json(400, {"error": str(exc)})
            except Exception as exc:
                self.send_json(503, {"error": f"Simulation run discovery unavailable: {exc}"})
            return
        if urlsplit(self.path).path == "/api/semantic/asset-history":
            try:
                from uuid import UUID
                from process_sim.api.asset_history import asset_history
                params = parse_qs(urlsplit(self.path).query)
                asset = params.get("assetIri", [""])[0]
                run_id = str(UUID(params.get("runId", [""])[0]))
                limit = int(params.get("limit", ["1000"])[0])
                self.send_json(200, asset_history(asset, run_id, limit))
            except ValueError as exc:
                self.send_json(400, {"error": str(exc)})
            except Exception as exc:
                self.send_json(503, {"error": f"Asset history unavailable: {exc}"})
            return
        if urlsplit(self.path).path == "/api/semantic/sync/status":
            from process_sim.api.graph_sync import status
            self.send_json(200, status())
            return
        if urlsplit(self.path).path == "/api/semantic/run":
            try:
                from uuid import UUID
                from process_sim.api.temporal_rdf import export_run
                params = parse_qs(urlsplit(self.path).query)
                run_id = str(UUID(params.get("runId", [""])[0]))
                rdf = export_run(run_id).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "text/turtle; charset=utf-8")
                self.send_header("Content-Length", str(len(rdf)))
                self.end_headers()
                self.wfile.write(rdf)
            except ValueError as exc:
                self.send_json(400, {"error": str(exc)})
            except LookupError as exc:
                self.send_json(404, {"error": str(exc)})
            except Exception as exc:
                self.send_json(503, {"error": f"Semantic run export unavailable: {exc}"})
            return
        if urlsplit(self.path).path == "/api/simulation/series":
            try:
                from uuid import UUID
                import re
                from process_sim.api.timeseries import query_samples
                params = parse_qs(urlsplit(self.path).query)
                run_id = str(UUID(params.get("runId", [""])[0]))
                signal = params.get("signal", [""])[0].upper()
                if not re.fullmatch(r"XMEAS(?:[1-9]|[1-3][0-9]|4[01])|XMV(?:[1-9]|1[0-2])", signal):
                    raise ValueError("Invalid signal ID")
                limit = int(params.get("limit", ["1000"])[0])
                if not 1 <= limit <= 5000:
                    raise ValueError("Limit must be 1..5000")
                rows = query_samples(run_id, signal, limit)
                self.send_json(200, {"runId": run_id, "signal": signal,
                                     "points": [{"time": t, "value": v, "observedAt": stamp.isoformat()}
                                                for t, v, stamp in rows]})
            except (ValueError, KeyError) as exc:
                self.send_json(400, {"error": str(exc)})
            except Exception as exc:
                self.send_json(503, {"error": f"Time-series database unavailable: {exc}"})
            return
        if urlsplit(self.path).path == "/api/simulation/fault-events/history":
            try:
                from uuid import UUID
                from process_sim.api.timeseries import query_fault_events
                params = parse_qs(urlsplit(self.path).query)
                run_id = str(UUID(params.get("runId", [""])[0]))
                limit = int(params.get("limit", ["500"])[0])
                if not 1 <= limit <= 5000:
                    raise ValueError("Limit must be 1..5000")
                events = query_fault_events(run_id, limit)
                for event in events:
                    event["event_id"] = str(event["event_id"])
                    event["run_id"] = str(event["run_id"])
                    event["observed_at"] = event["observed_at"].isoformat()
                self.send_json(200, {"runId": run_id, "events": events})
            except ValueError as exc:
                self.send_json(400, {"error": str(exc)})
            except Exception as exc:
                self.send_json(503, {"error": f"Fault history unavailable: {exc}"})
            return
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
        if urlsplit(self.path).path == "/api/governance/context":
            if self.governance is None:
                self.send_json(503, {"error": "Governance disabled"})
                return
            try:
                if self.headers.get("Content-Type", "").split(";")[0] != "application/json":
                    raise ValueError("JSON required")
                length = int(self.headers.get("Content-Length", "0"))
                if not 0 < length <= 16_384:
                    raise ValueError("Invalid request size")
                payload = json.loads(self.rfile.read(length))
                if not isinstance(payload, dict) or set(payload) != {
                        "expected_version", "evidence_complete",
                        "identity_normalized", "applicability_confirmed"}:
                    raise ValueError("Invalid qualification context request")
                expected_version = payload.pop("expected_version")
                result = self.governance.update_qualification_context(
                    payload, expected_version=expected_version)
                self.send_json(200, result)
            except ValueError as exc:
                self.send_json(422, {"error": str(exc)})
            except Exception:
                self.send_json(503, {"error": "Qualification context was not updated; inspect backend logs"})
            return
        if urlsplit(self.path).path == "/api/governance/change":
            if self.governance is None:
                self.send_json(503, {"error": "Governance disabled"})
                return
            try:
                from selira.runtime.aas_messages import AASChangeRequest
                if self.headers.get("Content-Type", "").split(";")[0] != "application/json":
                    raise ValueError("JSON required")
                length = int(self.headers.get("Content-Length", "0"))
                if not 0 < length <= MAX_BODY:
                    raise ValueError("Invalid request size")
                change = AASChangeRequest.model_validate_json(self.rfile.read(length))
                result = self.governance.submit(change)
                self.send_json(200, result.model_dump(mode="json"))
            except ValueError as exc:
                self.send_json(422, {"error": str(exc)})
            except Exception:
                self.send_json(503, {"error": "Outcome unconfirmed; do not retry automatically"})
            return
        if urlsplit(self.path).path == "/api/ai/vtkg/semantic/answer":
            try:
                from process_sim.api.vtkg_query import run_semantic_join_question
                length = int(self.headers.get("Content-Length", "0"))
                if not 0 < length <= 4096:
                    self.send_json(413, {"error": "Invalid request size"})
                    return
                payload = json.loads(self.rfile.read(length))
                self.send_json(200, run_semantic_join_question(payload))
            except (ValueError, TypeError, KeyError, json.JSONDecodeError) as exc:
                self.send_json(400, {"error": str(exc)})
            except RuntimeError as exc:
                self.send_json(422, {"error": str(exc)})
            except Exception:
                import logging
                logging.exception("Semantic join query failed")
                self.send_json(503, {"error": "Semantic join unavailable; check backend logs"})
            return
        if urlsplit(self.path).path == "/api/ai/unified/experimental/answer":
            try:
                from process_sim.api.unified_nl_experimental import run_unified_experiment
                length = int(self.headers.get("Content-Length", "0"))
                if not 0 < length <= 4096:
                    self.send_json(413, {"error": "Invalid request size"})
                    return
                payload = json.loads(self.rfile.read(length))
                if not isinstance(payload, dict) or set(payload) - {"question", "context"} or "question" not in payload:
                    raise ValueError("Expected question and optional context")
                self.send_json(200, run_unified_experiment(payload["question"], context=payload.get("context")))
            except (ValueError, TypeError, KeyError, json.JSONDecodeError) as exc:
                self.send_json(400, {"error": str(exc)})
            except Exception:
                import logging
                logging.exception("Unified experimental NL query failed")
                self.send_json(503, {"error": "Unified experimental query unavailable; check backend logs"})
            return
        if urlsplit(self.path).path == "/api/ai/vtkg/historian/experimental/answer":
            try:
                from process_sim.api.historian_nl_experimental import run_historian_nl_experiment
                length = int(self.headers.get("Content-Length", "0"))
                if not 0 < length <= 4096:
                    self.send_json(413, {"error": "Invalid request size"})
                    return
                payload = json.loads(self.rfile.read(length))
                if not isinstance(payload, dict) or set(payload) != {"question"}:
                    raise ValueError("Expected only a question")
                self.send_json(200, run_historian_nl_experiment(payload["question"]))
            except (ValueError, TypeError, KeyError, json.JSONDecodeError) as exc:
                self.send_json(400, {"error": str(exc)})
            except Exception:
                import logging
                logging.exception("Experimental NL historian query failed")
                self.send_json(503, {"error": "Experimental historian unavailable; check backend logs"})
            return
        if urlsplit(self.path).path == "/api/ai/vtkg/historian/explore-signal":
            try:
                from process_sim.api.vtkg_query import explore_signal_knowledge
                length = int(self.headers.get("Content-Length", "0"))
                if not 0 < length <= 4096:
                    self.send_json(413, {"error": "Invalid request size"})
                    return
                payload = json.loads(self.rfile.read(length))
                self.send_json(200, explore_signal_knowledge(payload))
            except (ValueError, TypeError, KeyError, json.JSONDecodeError) as exc:
                self.send_json(400, {"error": str(exc)})
            except Exception:
                import logging
                logging.exception("Signal-first knowledge exploration failed")
                self.send_json(503, {"error": "Knowledge explorer unavailable; check backend logs"})
            return
        if urlsplit(self.path).path == "/api/ai/vtkg/historian/signal-values":
            try:
                from process_sim.api.signal_historian import retrieve_signal
                length = int(self.headers.get("Content-Length", "0"))
                if not 0 < length <= 4096:
                    self.send_json(413, {"error": "Invalid request size"})
                    return
                payload = json.loads(self.rfile.read(length))
                self.send_json(200, retrieve_signal(payload))
            except (ValueError, TypeError, KeyError, json.JSONDecodeError) as exc:
                self.send_json(400, {"error": str(exc)})
            except Exception:
                import logging
                logging.exception("Direct signal historian retrieval failed")
                self.send_json(503, {"error": "Signal retrieval unavailable; check backend logs"})
            return
        if urlsplit(self.path).path == "/api/ai/vtkg/historian/answer":
            try:
                from process_sim.api.vtkg_query import run_historian_question
                length = int(self.headers.get("Content-Length", "0"))
                if not 0 < length <= 4096:
                    self.send_json(413, {"error": "Invalid request size"})
                    return
                payload = json.loads(self.rfile.read(length))
                self.send_json(200, run_historian_question(payload))
            except (ValueError, TypeError, KeyError, json.JSONDecodeError) as exc:
                self.send_json(400, {"error": str(exc)})
            except RuntimeError as exc:
                self.send_json(422, {"error": str(exc)})
            except Exception:
                import logging
                logging.exception("Historian query failed")
                self.send_json(503, {"error": "Historian query unavailable; check backend logs"})
            return

        if urlsplit(self.path).path in ("/api/ai/benchmarks/37/run", "/api/ai/benchmarks/42/run"):
            pilot = urlsplit(self.path).path.endswith("/42/run")
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if not 0 < length <= 4096:
                    self.send_json(413, {"error": "Invalid benchmark request size"})
                    return
                payload = json.loads(self.rfile.read(length))
                if not isinstance(payload, dict) or set(payload) != {"caseId", "indexSha256", "execute"}:
                    raise ValueError("Expected caseId, indexSha256 and execute only")
                from process_sim.api.frozen_benchmark import run_case
                self.send_json(200, run_case(payload["caseId"], payload["indexSha256"], payload["execute"], pilot=pilot))
            except (ValueError, TypeError, KeyError, json.JSONDecodeError) as exc:
                self.send_json(400, {"error": str(exc)})
            except RuntimeError as exc:
                self.send_json(409, {"error": str(exc)})
            except Exception as exc:
                import logging
                logging.exception("Benchmark 37 execution failed")
                self.send_json(503, {"error": "Benchmark execution failed; check backend logs"})
            return
        if urlsplit(self.path).path == "/api/ai/q13/ontology/live/start":
            from process_sim.api import q13_live
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if length != 0:
                    self.send_json(400, {"error": "Live Q13 start accepts no request body"})
                    return
                self.send_json(202, q13_live.start())
            except PermissionError as exc:
                self.send_json(403, {"error": str(exc)})
            except RuntimeError as exc:
                self.send_json(409, {"error": str(exc)})
            except (ValueError, OSError) as exc:
                self.send_json(503, {"error": str(exc)})
            except Exception as exc:
                import logging
                logging.exception("Unexpected Q13 live start failure")
                self.send_json(500, {"error": f"Q13 live start failed ({type(exc).__name__}); check backend logs"})
            return
        if urlsplit(self.path).path == "/api/ai/vtkg/answer":
            from process_sim.api.vtkg_query import VtkgUnavailable, run_question as run_vtkg_question
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if not 0 < length <= 4096:
                    self.send_json(413, {"error": "Invalid request size"})
                    return
                payload = json.loads(self.rfile.read(length))
                self.send_json(200, run_vtkg_question(payload))
            except (ValueError, TypeError, json.JSONDecodeError) as exc:
                self.send_json(400, {"error": str(exc)})
            except VtkgUnavailable as exc:
                self.send_json(503, {"error": str(exc)})
            except Exception:
                import logging
                logging.exception("VTKG query failed")
                self.send_json(503, {"error": "VTKG query failed; check backend logs"})
            return
        if urlsplit(self.path).path == "/api/ai/shacl/benchmark/execute":
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if not 0 < length <= 1024:
                    self.send_json(413, {"error": "Invalid request size"})
                    return
                payload = json.loads(self.rfile.read(length))
                if not isinstance(payload, dict) or "id" not in payload or not set(payload) <= {"id", "question"}:
                    raise ValueError("Expected benchmark question ID and optional edited question")
                from process_sim.api.shacl_benchmark_query import run_benchmark_question
                self.send_json(200, run_benchmark_question(payload["id"], payload.get("question")))
            except (ValueError, TypeError, json.JSONDecodeError) as exc:
                self.send_json(400, {"error": str(exc)})
            except Exception:
                import logging
                logging.exception("SHACL benchmark execution failed")
                self.send_json(503, {"error": "SHACL benchmark execution unavailable; check backend logs"})
            return
        if urlsplit(self.path).path == "/api/ai/dtwise/answer":
            from process_sim.api.dtwise_query import (
                DtwiseUnavailable, run_question,
            )
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if not 0 < length <= 4096:
                    self.send_json(413, {"error": "Invalid request size"})
                    return
                payload = json.loads(self.rfile.read(length))
                if not isinstance(payload, dict) or set(payload) != {"question"}:
                    raise ValueError("Expected only a question")
                self.send_json(200, run_question(payload["question"]))
            except (ValueError, TypeError, json.JSONDecodeError) as exc:
                self.send_json(400, {"error": str(exc)})
            except DtwiseUnavailable as exc:
                self.send_json(503, {"error": str(exc)})
            except Exception:
                import logging
                logging.exception("DTwise query failed")
                self.send_json(503, {"error": "DTwise query failed; check backend logs"})
            return
        if urlsplit(self.path).path == "/api/ai/custom/answer":
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if not 0 < length <= 4096:
                    self.send_json(413, {"error": "Invalid request size"})
                    return
                payload = json.loads(self.rfile.read(length))
                if not isinstance(payload, dict):
                    raise ValueError("Expected a JSON object")
                from process_sim.api.paper_query import custom_answer
                result = custom_answer(payload.get("question"), payload.get("runId") or None,
                                       payload.get("eventId") or None)
                self.send_json(200, result)
            except (ValueError, TypeError, json.JSONDecodeError) as exc:
                self.send_json(400, {"error": str(exc)})
            except Exception as exc:
                self.send_json(503, {"error": f"Exploratory query unavailable: {exc}"})
            return
        if urlsplit(self.path).path == "/api/ai/paper/answer":
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if not 0 < length <= 4096:
                    self.send_json(413, {"error": "Invalid request size"})
                    return
                payload = json.loads(self.rfile.read(length))
                if not isinstance(payload, dict):
                    raise ValueError("Expected a JSON object")
                from process_sim.api.paper_query import answer
                result = answer(payload.get("questionId"), payload.get("runId") or None,
                                payload.get("eventId") or None)
                self.send_json(200, result)
            except (ValueError, TypeError, json.JSONDecodeError) as exc:
                self.send_json(400, {"error": str(exc)})
            except Exception as exc:
                self.send_json(503, {"error": f"Paper query unavailable: {exc}"})
            return
        if urlsplit(self.path).path == '/api/engineering/physical-bom/revisions':
            try:
                length = int(self.headers.get('Content-Length', '0'))
                if not 0 < length <= 25000:
                    self.send_json(413, {'error': 'Invalid or oversized BOM revision'})
                    return
                from process_sim.api.physical_bom import create_revision
                self.send_json(201, create_revision(json.loads(self.rfile.read(length))))
            except (ValueError, TypeError, json.JSONDecodeError) as exc:
                self.send_json(400, {'error': str(exc)})
            except Exception as exc:
                self.send_json(503, {'error': f'Physical BOM unavailable: {exc}'})
            return
        if urlsplit(self.path).path == '/api/engineering/reviews':
            try:
                length = int(self.headers.get('Content-Length', '0'))
                if not 0 < length <= 10000:
                    self.send_json(413, {'error': 'Invalid or oversized review'})
                    return
                payload = json.loads(self.rfile.read(length))
                from process_sim.api.engineering_reviews import append_event
                self.send_json(201, append_event(payload))
            except (ValueError, TypeError, json.JSONDecodeError) as exc:
                self.send_json(400, {'error': str(exc)})
            except Exception as exc:
                self.send_json(503, {'error': f'Engineering review store unavailable: {exc}'})
            return
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
                    from process_sim.api.historian import history
                    run_id = history()["runId"]
                    warnings = []
                    if action == "clear_all":
                        for fault in before["faults"]:
                            warning = record("clear", fault["fault_id"], now, fault.get("target", ""),
                                             run_id=run_id, fault_type=fault.get("fault_type"),
                                             magnitude=fault.get("magnitude"), metadata={"command": "clear_all"})
                            if warning:
                                warnings.append(warning)
                    else:
                        known = next((f for f in before["faults"] if f["fault_id"] == payload.get("faultId")), None)
                        warning = record(action, payload.get("faultId", ""), now,
                                         payload.get("target", "") or (known or {}).get("target", ""),
                                         run_id=run_id, fault_type=payload.get("faultType") or (known or {}).get("fault_type"),
                                         magnitude=payload.get("magnitude") if action == "inject" else (known or {}).get("magnitude"))
                        if warning:
                            warnings.append(warning)
                    if warnings:
                        result = {**result, "warning": "; ".join(dict.fromkeys(warnings))}
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
        except Exception as exc:
            import logging
            logging.exception("Unexpected /api/kg/select backend error")
            self.send_json(500, {"error": f"Knowledge API internal error ({type(exc).__name__}); see backend logs"})

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
    if os.getenv("TEP_SELIRA_ENABLED") == "1":
        if host != "127.0.0.1" or os.getenv("TEP_SELIRA_EXCLUSIVE_WRITER") != "1":
            raise RuntimeError("Embedded governance requires loopback and exclusive writer confirmation")
        from selira.runtime.governance_server import build_service
        Handler.governance = build_service(GRAPHDB_ENDPOINT, os.environ["TEP_SELIRA_JOURNAL"],
            mode="recover", evidence_file=os.environ["TEP_SELIRA_EVIDENCE"], embedded=True)
    from process_sim.api.historian import start, stop
    start()
    from process_sim.api.graph_sync import start as start_graph_sync
    start_graph_sync()
    server = ThreadingHTTPServer((host, port), Handler)
    print(f"TEP NEXUS API listening at http://{host}:{port}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        try:
            stop()
        finally:
            server.server_close()


if __name__ == "__main__":
    main()
