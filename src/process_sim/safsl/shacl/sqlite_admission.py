"""Durable single-database SC-01 admission, with transactional audit.

This adapter atomically updates its OWN SQLite RDF snapshot, version and audit.
It does NOT write to GraphDB or AAS repositories, nor certify their revisions.
"""
import json
import sqlite3
from pathlib import Path

from rdflib import Graph

from .admission import Verdict, admit, VersionedGraphStore


class SQLiteAdmissionStore:
    def __init__(self, filename):
        self.filename = str(filename)
        with self._connect() as db:
            db.execute("CREATE TABLE IF NOT EXISTS state (id INTEGER PRIMARY KEY CHECK(id=1), version INTEGER NOT NULL, rdf TEXT NOT NULL, revisions TEXT NOT NULL)")
            db.execute("CREATE TABLE IF NOT EXISTS audit (id INTEGER PRIMARY KEY AUTOINCREMENT, version INTEGER NOT NULL, verdict TEXT NOT NULL, committed INTEGER NOT NULL, reason TEXT NOT NULL, revisions TEXT NOT NULL)")
            db.execute("INSERT OR IGNORE INTO state VALUES (1,0,'','{}')")

    def _connect(self):
        db = sqlite3.connect(self.filename, timeout=10, isolation_level=None)
        db.execute("PRAGMA busy_timeout=10000")
        return db

    def snapshot(self):
        with self._connect() as db:
            version, rdf, revisions = db.execute("SELECT version,rdf,revisions FROM state WHERE id=1").fetchone()
        graph = Graph()
        if rdf:
            graph.parse(data=rdf, format="nt")
        return graph, version, json.loads(revisions)

    def admit(self, *, shapes_ttl, manifest, changed_template_ids, source_revisions,
              expected_version, additions=(), removals=(), evidence_complete=None,
              identity_normalized=False, applicability_confirmed=True):
        """BEGIN IMMEDIATE serializes concurrent writers to this SQLite database.

        Revisions must be independently verified by the caller. A change to
        remote authoritative sources between reading and this transaction is
        NOT prevented by this method.
        """
        if not isinstance(source_revisions, dict) or not source_revisions or any(
            not isinstance(k, str) or not isinstance(v, str) or not v
            for k, v in source_revisions.items()
        ):
            raise ValueError("Explicit nonempty source revision tokens required")
        db = self._connect()
        try:
            db.execute("BEGIN IMMEDIATE")
            version, rdf, stored_revisions = db.execute(
                "SELECT version,rdf,revisions FROM state WHERE id=1"
            ).fetchone()
            if version != expected_version:
                decision = ("U", False, "Stale SQLite version")
            elif stored_revisions != "{}" and json.loads(stored_revisions) != source_revisions:
                decision = ("U", False, "Source revision tokens differ from stored snapshot")
            else:
                graph = Graph()
                if rdf:
                    graph.parse(data=rdf, format="nt")
                local = VersionedGraphStore(graph)
                result = admit(local, shapes_ttl=shapes_ttl, manifest=manifest,
                               changed_template_ids=changed_template_ids,
                               additions=additions, removals=removals,
                               evidence_complete=evidence_complete,
                               identity_normalized=identity_normalized,
                               applicability_confirmed=applicability_confirmed)
                decision = (result.verdict.value, result.committed, result.reason)
                if result.committed:
                    new_graph, _ = local.snapshot()
                    db.execute("UPDATE state SET version=?,rdf=?,revisions=? WHERE id=1",
                               (version + 1, new_graph.serialize(format="nt"),
                                json.dumps(source_revisions, sort_keys=True)))
            verdict, committed, reason = decision
            db.execute("INSERT INTO audit(version,verdict,committed,reason,revisions) VALUES(?,?,?,?,?)",
                       (version + (1 if committed else 0), verdict, int(committed),
                        reason, json.dumps(source_revisions, sort_keys=True)))
            db.execute("COMMIT")
            return {"verdict": verdict, "committed": committed,
                    "version": version + (1 if committed else 0), "reason": reason}
        except Exception:
            db.execute("ROLLBACK")
            raise
        finally:
            db.close()
