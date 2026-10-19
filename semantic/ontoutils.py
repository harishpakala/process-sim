'''
Created on Aug 01, 2026

@author: haris

ontoutils.py

Shared utilities for AAS semantic lifting.

Used by:
    - template_lifting.py
    - instance_lifting.py

Responsibilities:
    - RDF namespaces
    - URI generation
    - semantic predicate generation
    - datatype mapping
    - qualifier extraction
    - cardinality handling
    - SHACL helper functions
    - SemanticId classification
    - GraphDB communication
'''

import base64
import requests

from rdflib import (
    Graph,
    Namespace,
    URIRef,
    Literal,
    RDF,
    RDFS,
    XSD,
    OWL,
)


# ============================================================
# Namespaces
# ============================================================

semanticDict = {}

semanticDict["AAS"] = Namespace(
    "https://example.org/aas/"
)

semanticDict["ECAD"] = Namespace(
    "https://example.org/ecad/"
)

semanticDict["PRODUCTCATALOG"] = Namespace("https://example.org/productcatalog/")
semanticDict["ASSETINVENTORY"] = Namespace("https://example.org/assetinventory/")

semanticDict["DEXPI"] = Namespace(
    "https://example.org/dexpi/"
)

semanticDict["EX"] = Namespace(
    "http://example.org/ex#"
)

semanticDict["ECLASS"] = Namespace(
    "http://example.org/eclass#"
)

semanticDict["SH"] = Namespace(
    "http://www.w3.org/ns/shacl#"
)

semanticDict["QUDT"] = Namespace(
    "http://qudt.org/schema/qudt/"
)

semanticDict["UNIT"] = Namespace(
    "http://qudt.org/vocab/unit/"
)


# ============================================================
# Configuration
# ============================================================

BASE_URI = (
    "http://org.example.com"
)

GRAPHDB_ENDPOINT = (
    "http://localhost:7200/"
    "repositories/AAS/statements"
)

HEADERS = {
    "Content-Type": "application/sparql-update"
}


# ============================================================
# Cardinality
# ============================================================

CARDINALITY = {
    "ZeroToOne": (0, 1),
    "One": (1, 1),
    "ZeroToMany": (0, None),
    "OneToMany": (1, None),
}


# ============================================================
# URI generation
# ============================================================

def b64(value: str) -> str:
    """
    URI-safe Base64 representation without padding.
    """

    return (
        base64.b64encode(
            value.encode("utf-8")
        )
        .decode("utf-8")
        .rstrip("=")
    )


def compute_uri(
    submodel_id: str,
    path: str = "",
) -> URIRef:
    """
    Generate a deterministic URI for an AAS resource.

    URI:

        BASE_URI /
        enc(submodelId) /
        enc(path)

    Example:

        compute_uri(
            "https://example.org/sm/dexpi25",
            "Equipments.K_101"
        )
    """

    submodel_hash = b64(
        submodel_id
    )

    path_hash = b64(
        path if path else ""
    )

    return URIRef(
        f"{BASE_URI}/"
        f"{submodel_hash}/"
        f"{path_hash}"
    )


def compute_property_uri(
    template_id: str,
    path: str,
) -> URIRef:
    """
    Generate the structural/template property URI.

    The TEMPLATE ID must be used here.

    This guarantees that the property URI used by
    instance lifting is identical to the URI referenced
    by the template SHACL sh:path.

    Example:

        template_id = template123
        path = Equipments.AssetIdentifier

        -> deterministic property URI
    """

    return compute_uri(
        template_id,
        path,
    )


# ============================================================
# Semantic predicate generation
# ============================================================

def make_has_predicate(
    domain: str,
    concept_name: str,
) -> URIRef:
    """
    Generate a semantic 'hasX' predicate from an ontology
    concept.

    Examples:

        Equipment
            -> dexpi:hasEquipment

        ActuatingFunction
            -> dexpi:hasActuatingFunction

        InstrumentationFunction
            -> dexpi:hasInstrumentationFunction

    IMPORTANT:

        The concrete instance idShort is NOT used.

    Therefore:

        K_101 + Equipment

    produces:

        dexpi:hasEquipment

    NOT:

        dexpi:hasK_101
    """

    if concept_name is None:
        raise ValueError(
            "Cannot create semantic predicate "
            "without an ontology concept."
        )

    concept_name = str(
        concept_name
    ).strip()

    if not concept_name:
        raise ValueError(
            "Ontology concept cannot be empty."
        )

    domain_upper = str(
        domain
    ).upper()

    if domain_upper not in semanticDict:
        raise ValueError(
            f"Unknown ontology domain "
            f"'{domain}'. "
            f"Known domains: "
            f"{', '.join(semanticDict.keys())}"
        )

    # Normalize the concept into a conventional
    # hasX predicate.
    #
    # Equipment
    #     -> hasEquipment
    #
    # equipment
    #     -> hasEquipment

    concept_normalized = (
        concept_name[0].upper()
        + concept_name[1:]
    )

    predicate_name = (
        "has"
        + concept_normalized
    )

    return URIRef(
        semanticDict[domain_upper][
            predicate_name
        ]
    )


# ============================================================
# Domain concept URI
# ============================================================

def make_domain_concept_uri(
    domain: str,
    concept_name: str,
) -> URIRef:
    """
    Generate the URI of a domain ontology concept.

    Example:

        DEXPI + Equipment

        -> https://example.org/dexpi/Equipment
    """

    if concept_name is None:
        raise ValueError(
            "Concept name cannot be None."
        )

    concept_name = str(
        concept_name
    ).strip()

    if not concept_name:
        raise ValueError(
            "Concept name cannot be empty."
        )

    domain_upper = str(
        domain
    ).upper()

    if domain_upper not in semanticDict:
        raise ValueError(
            f"Unknown ontology domain "
            f"'{domain}'."
        )

    return URIRef(
        semanticDict[domain_upper][
            concept_name
        ]
    )


# ============================================================
# Path construction
# ============================================================

def build_path(
    parent_path: str,
    id_short: str,
) -> str:
    """
    Construct a hierarchical AAS element path.

    Example:

        Equipments
        Equipments.K_101
        Equipments.K_101.AssetIdentifier
    """

    if id_short is None:
        raise ValueError(
            "idShort cannot be None."
        )

    if parent_path:
        return (
            parent_path
            + "."
            + id_short
        )

    return id_short


# ============================================================
# XSD datatype mapping
# ============================================================

def map_xsd_datatype(
    value_type,
):
    """
    Map an AAS valueType to an XSD datatype.

    Examples:

        xs:string
            -> xsd:string

        xs:boolean
            -> xsd:boolean

        xs:int
            -> xsd:integer

        xs:float
            -> xsd:float

        xs:double
            -> xsd:double
    """

    if value_type is None:
        return XSD.string

    value_type = str(
        value_type
    ).lower()

    value_type = value_type.replace(
        "xs:",
        ""
    )

    mapping = {

        "string":
            XSD.string,

        "boolean":
            XSD.boolean,

        "byte":
            XSD.byte,

        "short":
            XSD.short,

        "int":
            XSD.integer,

        "integer":
            XSD.integer,

        "long":
            XSD.long,

        "unsignedbyte":
            XSD.unsignedByte,

        "unsignedshort":
            XSD.unsignedShort,

        "unsignedint":
            XSD.unsignedInt,

        "unsignedlong":
            XSD.unsignedLong,

        "float":
            XSD.float,

        "double":
            XSD.double,

        "decimal":
            XSD.decimal,

        "date":
            XSD.date,

        "datetime":
            XSD.dateTime,

        "time":
            XSD.time,
    }

    return mapping.get(
        value_type,
        XSD.string,
    )


def make_literal(value, value_type=None):
    """
    Create an RDF Literal using the AAS valueType when available.
    """
    if value is None:
        return None
    datatype = map_xsd_datatype(value_type)

    if datatype is not None:
        return Literal(value, datatype=datatype)

    

# ============================================================
# Qualifier helpers
# ============================================================

def get_qualifier(
    element,
    qualifier_type: str,
):
    """
    Return the first qualifier matching
    qualifier_type.

    Example:

        get_qualifier(
            element,
            "Cardinality"
        )
    """

    if not element.qualifiers:
        return None

    for qualifier in element.qualifiers:

        if qualifier.type == qualifier_type:
            return qualifier

    return None


def get_cardinality(
    element,
):
    """
    Extract the Cardinality qualifier.

    Returns:

        One
            -> (1, 1)

        ZeroToOne
            -> (0, 1)

        ZeroToMany
            -> (0, None)

        OneToMany
            -> (1, None)

    If no Cardinality qualifier exists,
    the implementation default is:

        (1, 1)
    """

    if not element.qualifiers:
        return (0, 1)

    for qualifier in element.qualifiers:

        if qualifier.type == "Cardinality":

            value = str(
                qualifier.value
            )

            if value not in CARDINALITY:

                raise ValueError(
                    f"Unsupported cardinality "
                    f"'{value}' on element "
                    f"'{element.id_short}'"
                )

            return CARDINALITY[value]

    return (1, 1)


def get_ontology_concept(
    element,
):
    """
    Extract an ontoConcept qualifier.

    Supported spelling:

        ontoConcept

    The older spelling OntologyConcept is also
    accepted for backwards compatibility.

    IMPORTANT:

    The semantic design treats ontoConcept as an
    instance-level semantic annotation.

    Template lifting should not depend on it being
    present.
    """

    if not element.qualifiers:
        return None

    for qualifier in element.qualifiers:

        if str(qualifier.type).lower() in (
            "ontoconcept",
            "ontologyconcept",
        ):

            if qualifier.value is None:
                return None

            return str(
                qualifier.value
            )

    return None


# ============================================================
# SHACL labels
# ============================================================

def make_shape_label(
    element_label: str,
) -> str:
    """
    Human-readable label for a SHACL PropertyShape.
    """

    return (
        f"{element_label} constraint"
    )


def make_node_shape_label(
    label: str,
) -> str:
    """
    Human-readable label for a SHACL NodeShape.
    """

    return (
        f"{label} SHACL shape"
    )


# ============================================================
# SHACL cardinality
# ============================================================

def add_cardinality_constraints(
    graph: Graph,
    shape_node: URIRef,
    min_count: int,
    max_count,
):
    """
    Add SHACL cardinality constraints.
    """

    graph.add(
        (
            shape_node,
            semanticDict["SH"]["minCount"],
            Literal(min_count),
        )
    )

    if max_count is not None:

        graph.add(
            (
                shape_node,
                semanticDict["SH"]["maxCount"],
                Literal(max_count),
            )
        )


# ============================================================
# SemanticId classification
# ============================================================

def resolve_semantic_id(
    semantic_uri: URIRef,
) -> str:
    """
    Determine the semantic role of a SemanticId.

    Returns:

        unit
        quantitykind
        classification
        annotation
    """

    uri = str(
        semantic_uri
    )

    if uri.startswith(
        "http://qudt.org/vocab/unit/"
    ):

        return "unit"

    if uri.startswith(
        "http://qudt.org/vocab/quantitykind/"
    ):

        return "quantitykind"

    if uri.startswith(
        "https://eclass.eu/"
    ):

        return "classification"

    return "annotation"


# ============================================================
# SemanticId lifting
# ============================================================

def lift_semantic_id(graph: Graph, submodel_id: str, element, path: str):
    """Preserve AAS semantic references exactly, without asserting unverified equivalence.

    semanticId is the primary concept reference. Supplemental identifiers are
    separate references. QUDT unit/quantity-kind references are recognized only
    when explicitly supplied by the AAS source.
    """
    element_uri = compute_uri(submodel_id, path)
    aas = semanticDict["AAS"]
    qudt = semanticDict["QUDT"]

    def add_reference(reference, predicate):
        if reference is None:
            return
        keys = getattr(reference, "keys", None) or []
        for key in keys:
            value = str(key.value).strip()
            if not value:
                continue
            # ExternalReference keys may contain non-URI identifiers (e.g. ECLASS IRDI).
            # Preserve the original identifier as a literal even if it is not a URI.
            graph.add((element_uri, predicate, Literal(value)))
            if not (value.startswith("https://") or value.startswith("http://") or value.startswith("urn:")):
                continue
            uri = URIRef(value)
            graph.add((element_uri, RDFS.seeAlso, uri))
            if predicate != aas["semanticId"]:
                continue
            mode = resolve_semantic_id(uri)
            if mode == "unit":
                graph.add((element_uri, qudt["unit"], uri))
            elif mode == "quantitykind":
                graph.add((element_uri, qudt["hasQuantityKind"], uri))
            elif mode == "classification":
                graph.add((element_uri, aas["classificationReference"], uri))

    add_reference(getattr(element, "semantic_id", None), aas["semanticId"])
    for reference in (getattr(element, "supplemental_semantic_ids", None) or []):
        add_reference(reference, aas["supplementalSemanticId"])


# ============================================================
# Namespace binding
# ============================================================

def bind_common_namespaces(
    graph: Graph,
    domain: str = None,
):
    """
    Bind common namespaces used by the lifting framework.
    """

    graph.bind(
        "aas",
        semanticDict["AAS"],
    )

    graph.bind(
        "sh",
        semanticDict["SH"],
    )

    graph.bind(
        "owl",
        OWL,
    )

    graph.bind(
        "rdfs",
        RDFS,
    )

    graph.bind(
        "rdf",
        RDF,
    )

    graph.bind(
        "xsd",
        XSD,
    )

    graph.bind(
        "qudt",
        semanticDict["QUDT"],
    )

    graph.bind(
        "unit",
        semanticDict["UNIT"],
    )

    graph.bind(
        "ex",
        semanticDict["EX"],
    )

    if domain is not None:

        domain_upper = str(
            domain
        ).upper()

        if domain_upper in semanticDict:

            graph.bind(
                str(domain).lower(),
                semanticDict[domain_upper],
            )


# ============================================================
# GraphDB
# ============================================================

def push_graph_to_graphdb(
    graph: Graph,
    graph_uri: URIRef,
):
    """
    Insert an RDF graph into a GraphDB named graph.

    This function uses /statements because it is an RDF
    statement update endpoint.
    """

    serialized = graph.serialize(
        format="nt"
    )

    query = f"""
INSERT DATA {{
    GRAPH <{graph_uri}> {{
        {serialized}
    }}
}}
"""

    response = requests.post(
        GRAPHDB_ENDPOINT,
        data=query.encode("utf-8"),
        headers=HEADERS,
        timeout=60,
    )

    if response.status_code not in (
        200,
        204,
    ):

        print(
            "GraphDB response:"
        )

        print(
            response.text
        )

        raise RuntimeError(
            "Failed to insert graph "
            "into GraphDB. "
            f"HTTP status: "
            f"{response.status_code}"
        )

    print(
        "Graph successfully pushed "
        f"to GraphDB: {graph_uri}"
    )


def get_graphdb_repository_url():
    """
    Return the GraphDB repository URL without
    /statements.

    Used for SPARQL SELECT / CONSTRUCT queries.

    Example:

        http://localhost:7200/repositories/AAS
    """

    suffix = "/statements"

    if GRAPHDB_ENDPOINT.endswith(
        suffix
    ):

        return GRAPHDB_ENDPOINT[
            :-len(suffix)
        ]

    return GRAPHDB_ENDPOINT
