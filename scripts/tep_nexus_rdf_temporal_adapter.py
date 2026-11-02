"""TEP NEXUS: Virtual temporal KG JSON -> RDF/Turtle adapter.

Uses SOSA, PROV-O, OWL-Time and a local TEP NEXUS vocabulary.
Does not modify GraphDB or TimescaleDB.
"""

import argparse
import json
from datetime import datetime
from pathlib import Path

from rdflib import Graph, Literal, Namespace, URIRef
from rdflib.namespace import RDF, RDFS, XSD


SOSA = Namespace("http://www.w3.org/ns/sosa/")
PROV = Namespace("http://www.w3.org/ns/prov#")
TIME = Namespace("http://www.w3.org/2006/time#")
TEP = Namespace("https://example.org/tep-nexus/")
EX = Namespace("https://example.org/tep-nexus/resource/")


def timestamp_literal(value):
    # Ensure the recorded timestamp is a valid timezone-aware
    # xsd:dateTime value.
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))

    if parsed.tzinfo is None:
        raise ValueError(
            "Observation timestamp has no timezone: " + value
        )

    return Literal(parsed.isoformat(), datatype=XSD.dateTime)


def build_rdf(report, limit):
    graph = Graph()

    graph.bind("sosa", SOSA)
    graph.bind("prov", PROV)
    graph.bind("time", TIME)
    graph.bind("tep", TEP)
    graph.bind("ex", EX)

    context = report["resolvedContext"]
    query = report["query"]

    function_id = query["engineeringFunction"]
    signal_id = context["operationalSignal"]
    run_id = query["runId"]

    function = EX["engineering/" + function_id]
    signal = EX["signal/" + signal_id]
    run = EX["run/" + run_id]

    aas_reference = URIRef(context["aasFunctionReference"])
    asset = URIRef(context["assetURI"])

    graphdb_source = EX["source/graphdb"]
    timescale_source = EX["source/timescaledb"]

    graph.add((graphdb_source, RDF.type, PROV.Entity))
    graph.add((timescale_source, RDF.type, PROV.Entity))

    graph.add((graphdb_source, RDFS.label, Literal("GraphDB AAS repository")))
    graph.add((timescale_source, RDFS.label, Literal("TimescaleDB signal_samples")))

    # Engineering and operational context.
    graph.add((function, RDF.type, TEP.EngineeringFunction))
    graph.add((function, TEP.localId, Literal(function_id)))
    graph.add((function, TEP.hasAASFunctionReference, aas_reference))
    graph.add((
        function,
        TEP.mappingStatus,
        Literal(context["mappingStatus"]),
    ))

    graph.add((aas_reference, RDF.type, TEP.AASFunctionReference))
    graph.add((aas_reference, TEP.mapsToOperationalSignal, signal))

    graph.add((signal, RDF.type, SOSA.ObservableProperty))
    graph.add((signal, TEP.signalId, Literal(signal_id)))
    graph.add((signal, TEP.hasAssociatedAsset, asset))

    graph.add((asset, RDF.type, TEP.AssetInventoryAsset))

    graph.add((function, PROV.wasDerivedFrom, graphdb_source))
    graph.add((signal, PROV.wasDerivedFrom, graphdb_source))

    # Operator-selected database run, not verified shared provenance.
    graph.add((run, RDF.type, TEP.OperatorSelectedRunReference))
    graph.add((run, TEP.runId, Literal(run_id)))
    graph.add((
        run,
        TEP.sharedRunProvenance,
        Literal("NOT_VERIFIED"),
    ))

    observations = [
        node
        for node in report["graph"]["nodes"]
        if node["type"] == "TemporalObservation"
    ]

    # Sort by simulation time so the selection is independent of
    # the order in the source JSON.
    observations.sort(
        key=lambda item: (
            item["simulationTimeSeconds"],
            item["recordedAt"],
        ),
        reverse=True,
    )

    selected = observations[:limit]

    for index, item in enumerate(selected):
        # Local export identity only; not a persistent source ID.
        observation = EX[f"observation/{run_id}/{index}"]
        instant = EX[f"recorded-instant/{run_id}/{index}"]

        graph.add((observation, RDF.type, SOSA.Observation))
        graph.add((observation, SOSA.observedProperty, signal))
        graph.add((
            observation,
            SOSA.hasSimpleResult,
            Literal(float(item["value"]), datatype=XSD.double),
        ))

        graph.add((
            observation,
            TEP.simulationTimeSeconds,
            Literal(
                float(item["simulationTimeSeconds"]),
                datatype=XSD.double,
            ),
        ))

        graph.add((observation, SOSA.resultTime,
                   timestamp_literal(item["recordedAt"])))

        graph.add((observation, TEP.recordedAtInstant, instant))
        graph.add((instant, RDF.type, TIME.Instant))
        graph.add((
            instant,
            TIME.inXSDDateTime,
            timestamp_literal(item["recordedAt"]),
        ))

        graph.add((observation, PROV.wasDerivedFrom, timescale_source))
        graph.add((observation, TEP.retrievedUsingRunReference, run))
        graph.add((
            observation,
            TEP.identityScope,
            Literal("QUERY_RESULT_ONLY"),
        ))

    return graph, len(selected)


def validate_graph(graph, expected_count):
    observations = set(graph.subjects(RDF.type, SOSA.Observation))

    if len(observations) != expected_count:
        raise RuntimeError("Unexpected RDF observation count")

    for observation in observations:
        if not list(graph.objects(observation, SOSA.observedProperty)):
            raise RuntimeError("Missing observed property")

        if not list(graph.objects(observation, SOSA.hasSimpleResult)):
            raise RuntimeError("Missing observation result")

        if not list(graph.objects(observation, SOSA.resultTime)):
            raise RuntimeError("Missing result timestamp")

        if not list(graph.objects(observation, TEP.simulationTimeSeconds)):
            raise RuntimeError("Missing simulation time")

    return True


def query_graph(graph):
    sparql = """
PREFIX sosa: <http://www.w3.org/ns/sosa/>
PREFIX tep: <https://example.org/tep-nexus/>

SELECT ?signal ?simulationSeconds ?value ?recordedAt
WHERE {
    ?observation a sosa:Observation ;
                 sosa:observedProperty ?signal ;
                 sosa:hasSimpleResult ?value ;
                 sosa:resultTime ?recordedAt ;
                 tep:simulationTimeSeconds ?simulationSeconds .
}
ORDER BY DESC(?simulationSeconds)
LIMIT 5
"""

    return list(graph.query(sparql))


def main():
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--input",
        default="reports/tep_nexus_virtual_temporal_kg.json",
    )
    parser.add_argument(
        "--output",
        default="reports/tep_nexus_temporal_graph.ttl",
    )
    parser.add_argument("--limit", type=int, default=20)

    args = parser.parse_args()

    if args.limit < 1:
        parser.error("--limit must be positive")

    source = Path(args.input)
    if not source.exists():
        parser.error("Input JSON does not exist: " + str(source))

    report = json.loads(source.read_text(encoding="utf-8"))

    if report.get("representation") != "query-time property graph JSON":
        parser.error("Unexpected source representation")

    graph, observation_count = build_rdf(report, args.limit)

    validate_graph(graph, observation_count)

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)

    graph.serialize(destination=str(output), format="turtle")

    # Independently parse the generated Turtle file.
    reloaded = Graph()
    reloaded.parse(str(output), format="turtle")

    if len(reloaded) != len(graph):
        raise RuntimeError("RDF round-trip triple count mismatch")

    rows = query_graph(reloaded)

    print("\n=== TEP NEXUS RDF TEMPORAL GRAPH ===")
    print("Engineering function:", report["query"]["engineeringFunction"])
    print("Operational signal:", report["resolvedContext"]["operationalSignal"])
    print("RDF observations:", observation_count)
    print("RDF triples:", len(reloaded))
    print("Turtle round-trip validation: PASS")
    print("Local SPARQL query: PASS")

    print("\nLatest observations (SPARQL):")

    for row in rows:
        print(
            f"  t={float(row.simulationSeconds):.3f}s"
            f"  value={float(row.value):.9f}"
            f"  recordedAt={row.recordedAt}"
        )

    print("\nShared run provenance: NOT VERIFIED")
    print("Mapping: PROVISIONAL_ENGINEERING_MATCH")
    print("Saved:", output)


if __name__ == "__main__":
    main()
