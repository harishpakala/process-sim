"""Registry of the RDF vocabulary emitted by api.temporal_rdf.export_run.

Temporal RDF is not generated from AAS templates. Keep this separate from the
AAS SHACL registry; changes to the exporter must be reflected in tests here.
"""

# Created: 2026-10-23
# Author: Harish
from process_sim.api.temporal_rdf import BASE
from process_sim.api.graph_sync import BASE_GRAPH

NS = BASE + "ontology/"
RUN = BASE + "run/"
SIGNAL = BASE + "signal/"
EVENT = BASE + "event/"

# Subject class -> emitted predicate -> object kind.
SHAPES = {
    "SimulationRun": {
        "runId": "literal", "startedAt": "datetime", "endedAt": "datetime",
        "endReason": "literal", "hasRecordedSignal": "OperationalSignal",
        "hasFaultEvent": "FaultCommandEvent",
    },
    "OperationalSignal": {"signalId": "literal"},
    "FaultCommandEvent": {
        "inSimulationRun": "SimulationRun", "faultId": "literal",
        "action": "literal", "simulationTimeHours": "double",
        "observedAt": "datetime", "targetIdentifier": "literal",
        "faultType": "literal", "magnitude": "double",
    },
}


def temporal_registry():
    return {
        "domain": "temporal",
        "ontologyNamespace": NS,
        "namedGraphPrefix": BASE_GRAPH,
        "classes": [NS + name for name in SHAPES],
        "properties": [
            {"subjectClass": NS + cls, "predicate": NS + pred,
             "valueKind": kind}
            for cls, props in SHAPES.items() for pred, kind in props.items()
        ],
        "source": "process_sim.api.temporal_rdf.export_run",
        "note": "Exporter vocabulary catalog, not formal SHACL or proof of live GraphDB ingestion. Raw samples remain in TimescaleDB.",
    }
