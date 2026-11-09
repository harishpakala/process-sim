"""Export fault-aware virtual Temporal KG JSON as validated RDF/Turtle.

Read-only transformation; does not upload RDF to GraphDB.
"""
import argparse
import importlib.util
import json
from collections import Counter
from pathlib import Path
from urllib.parse import quote

from rdflib import Graph, Literal, URIRef
from rdflib.namespace import RDF, XSD

spec = importlib.util.spec_from_file_location(
    "tep_rdf_base", Path(__file__).with_name("tep_nexus_rdf_temporal_adapter.py")
)
base = importlib.util.module_from_spec(spec)
spec.loader.exec_module(base)

TEP, EX, PROV, TIME, SOSA = base.TEP, base.EX, base.PROV, base.TIME, base.SOSA


def resource(kind, value):
    return EX[kind + "/" + quote(str(value), safe="")]


def build_fault_rdf(report, limit):
    graph, count = base.build_rdf(report, limit)
    run_id = report["query"]["runId"]
    signal_id = report["resolvedContext"]["operationalSignal"]
    run = EX["run/" + run_id]
    signal = EX["signal/" + signal_id]
    timescale = EX["source/timescaledb"]
    event_nodes = [n for n in report["graph"]["nodes"]
                   if n["type"] == "FaultCommandEvent"]
    interval_nodes = [n for n in report["graph"]["nodes"]
                      if n["type"] == "FaultCommandInterval"]
    for event in event_nodes:
        eid = event.get("event_id", event.get("eventId"))
        node = resource("fault-command", eid)
        graph.add((node, RDF.type, TEP.FaultCommandEvent))
        graph.add((node, PROV.wasDerivedFrom, timescale))
        graph.add((node, TEP.recordedForRun, run))
        graph.add((node, TEP.eventId, Literal(eid)))
        for key, predicate in (
            ("action", TEP.action), ("fault_id", TEP.faultId),
            ("fault_type", TEP.faultType), ("target", TEP.targetSignalId),
            ("event_source", TEP.eventSource),
        ):
            if event.get(key) is not None:
                graph.add((node, predicate, Literal(event[key])))
        if event.get("magnitude") is not None:
            graph.add((node, TEP.magnitude,
                       Literal(float(event["magnitude"]), datatype=XSD.double)))
        graph.add((node, TEP.simulationTimeSeconds,
                   Literal(float(event["simulation_time_hours"]) * 3600,
                           datatype=XSD.double)))
        graph.add((node, PROV.generatedAtTime,
                   base.timestamp_literal(event["observed_at"])))
    interval_by_id = {}
    for interval in interval_nodes:
        start_id = interval["startEventId"]
        node = resource("fault-command-interval", start_id)
        interval_by_id[start_id] = node
        graph.add((node, RDF.type, TEP.FaultCommandInterval))
        graph.add((node, RDF.type, TIME.Interval))
        graph.add((node, TEP.recordedForRun, run))
        graph.add((node, TEP.faultId, Literal(interval["faultId"])))
        graph.add((node, TEP.intervalStatus, Literal(interval["status"])))
        graph.add((node, TEP.provenanceStatus, Literal(interval["provenance"])))
        graph.add((node, TEP.historyComplete,
                   Literal(bool(interval["historyComplete"]), datatype=XSD.boolean)))
        graph.add((node, TEP.targetSignalId, Literal(interval["target"])))
        graph.add((node, TEP.startSimulationSeconds,
                   Literal(float(interval["startSimulationHours"]) * 3600,
                           datatype=XSD.double)))
        graph.add((node, TEP.derivedFromInjectionCommand,
                   resource("fault-command", start_id)))
        graph.add((node, PROV.wasDerivedFrom, resource("fault-command", start_id)))
        if interval["target"] == signal_id:
            graph.add((node, TEP.appliesToSignal, signal))
        if interval.get("endEventId") is not None:
            graph.add((node, TEP.derivedFromClearCommand,
                       resource("fault-command", interval["endEventId"])))
            graph.add((node, TEP.endSimulationSeconds,
                       Literal(float(interval["endSimulationHours"]) * 3600,
                               datatype=XSD.double)))
        # OWL-Time beginning is the recorded wall-clock command instant,
        # NOT a conversion of simulation time to wall-clock time.
        instant = resource("fault-command-instant", start_id)
        graph.add((instant, RDF.type, TIME.Instant))
        graph.add((instant, TIME.inXSDDateTime,
                   base.timestamp_literal(interval["startObservedAt"])))
        graph.add((node, TIME.hasBeginning, instant))
        if interval.get("endObservedAt") is not None:
            end_instant = resource("fault-clear-instant", interval["endEventId"])
            graph.add((end_instant, RDF.type, TIME.Instant))
            graph.add((end_instant, TIME.inXSDDateTime,
                       base.timestamp_literal(interval["endObservedAt"])))
            graph.add((node, TIME.hasEnd, end_instant))

    observations = sorted(
        (n for n in report["graph"]["nodes"] if n["type"] == "TemporalObservation"),
        key=lambda n: (n["simulationTimeSeconds"], n["recordedAt"]),
        reverse=True,
    )[:limit]
    # Reuse precisely the observation identities/order used by base.build_rdf.
    counts = Counter()
    for index, item in enumerate(observations):
        observation = EX[f"observation/{run_id}/{index}"]
        relations = item.get("faultCommandRelations", {})
        for interval in interval_nodes:
            if interval["target"] != signal_id:
                continue
            relation = relations.get(interval["faultId"])
            if relation is None:
                raise ValueError("Missing command-relative classification for observation")
            if relation not in ("BEFORE", "DURING", "AFTER", "DURING_UNCONFIRMED", "UNKNOWN"):
                raise ValueError("Invalid temporal relation: " + str(relation))
            node = interval_by_id[interval["startEventId"]]
            relation_node = resource(
                "observation-interval-relation",
                f"{run_id}/{index}/{interval['startEventId']}",
            )
            graph.add((relation_node, RDF.type, TEP.CommandRelativeObservationRelation))
            graph.add((relation_node, TEP.observation, observation))
            graph.add((relation_node, TEP.faultCommandInterval, node))
            graph.add((relation_node, TEP.temporalRelation, Literal(relation)))
            graph.add((relation_node, TEP.interpretation,
                       Literal("Command-relative; physical fault state unverified")))
            counts[relation] += 1
    return graph, count, counts, len(event_nodes), len(interval_nodes)


def validate_fault_rdf(graph, observation_count, counts, events, intervals):
    base.validate_graph(graph, observation_count)
    if len(set(graph.subjects(RDF.type, TEP.FaultCommandEvent))) != events:
        raise RuntimeError("Fault event RDF count mismatch")
    interval_resources = set(graph.subjects(RDF.type, TEP.FaultCommandInterval))
    if len(interval_resources) != intervals:
        raise RuntimeError("Fault interval RDF count mismatch")
    relation_resources = set(
        graph.subjects(RDF.type, TEP.CommandRelativeObservationRelation)
    )
    if len(relation_resources) != sum(counts.values()):
        raise RuntimeError("Observation classification RDF count mismatch")
    for interval in interval_resources:
        status = str(graph.value(interval, TEP.intervalStatus))
        if status == "OPEN_UNCONFIRMED":
            if list(graph.objects(interval, TIME.hasEnd)):
                raise RuntimeError("Open interval must not have an OWL-Time end")
            if list(graph.objects(interval, TEP.endSimulationSeconds)):
                raise RuntimeError("Open interval must not have an end simulation time")
    return True


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", default="reports/tep_nexus_fault_temporal_kg.json")
    parser.add_argument("--output", default="reports/tep_nexus_fault_temporal_graph.ttl")
    parser.add_argument("--limit", type=int, default=None,
                        help="Maximum observations; default exports all")
    args = parser.parse_args()
    report = json.loads(Path(args.input).read_text(encoding="utf-8"))
    if report.get("representation") != "query-time property graph JSON":
        parser.error("Unexpected input representation")
    available = sum(n["type"] == "TemporalObservation"
                    for n in report["graph"]["nodes"])
    limit = available if args.limit is None else args.limit
    if limit < 1:
        parser.error("Observation limit must be positive")
    graph, count, counts, events, intervals = build_fault_rdf(report, limit)
    validate_fault_rdf(graph, count, counts, events, intervals)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    graph.serialize(destination=str(output), format="turtle")
    reloaded = Graph()
    reloaded.parse(str(output), format="turtle")
    if len(reloaded) != len(graph):
        raise RuntimeError("Turtle round-trip triple count mismatch")
    validate_fault_rdf(reloaded, count, counts, events, intervals)
    print("RDF observations:", count)
    print("Fault command events:", events)
    print("Fault command intervals:", intervals)
    print("Temporal classifications:", dict(counts))
    print("RDF triples:", len(reloaded))
    print("Turtle round-trip validation: PASS")
    print("Saved:", output)


if __name__ == "__main__":
    main()
