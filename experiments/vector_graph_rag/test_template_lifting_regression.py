"""Read-only regression checks for AAS template lifting and DTWise metadata."""
import json
import unittest
from pathlib import Path

from rdflib import Literal, OWL, RDF, RDFS
from rdflib.namespace import SH
import aas_core3_1.jsonization as aas_jsonization

from semantic.template_lifting import build_template_graph, make_semantic_predicate
from semantic.ontoutils import compute_uri
from semantic.dtwise_index import build_dtwise_catalog, DT


ROOT = Path(__file__).resolve().parents[2]
TEMPLATE = ROOT / "semantic/templates/engineeringbom_v2_template.json"


def iter_elements(elements, parent=""):
    for element in elements or []:
        path = parent + "." + element.id_short if parent else element.id_short
        yield path, element
        if hasattr(element, "value") and isinstance(element.value, (list, tuple)):
            yield from iter_elements(element.value, path)


class TemplateLiftingRegression(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.model = aas_jsonization.submodel_from_jsonable(
            json.loads(TEMPLATE.read_text(encoding="utf-8"))
        )
        cls.graph = build_template_graph(cls.model, "engineeringbom")
        cls.concepts, cls.relationships = build_dtwise_catalog(
            [("engineeringbom", cls.graph)]
        )

    def test_root_description_on_shape_and_class(self):
        root = self.model.description[0]
        literal = Literal(root.text, lang=root.language)
        self.assertIn(
            (compute_uri(self.model.id, "shape"), SH.description, literal), self.graph
        )
        self.assertIn(
            (compute_uri(self.model.id, ""), RDFS.comment, literal), self.graph
        )

    def test_every_element_description_on_shape_and_catalog(self):
        elements = list(iter_elements(self.model.submodel_elements))
        self.assertEqual(36, len(elements))
        for path, element in elements:
            with self.subTest(path=path):
                self.assertTrue(element.description)
                shape = compute_uri(self.model.id, path + "/shape")
                self.assertIn((shape, RDF.type, SH.PropertyShape), self.graph)
                predicate = make_semantic_predicate("engineeringbom", element.id_short)
                self.assertIn((shape, SH.path, predicate), self.graph)
                self.assertIn((shape, None, None), self.graph)
                for entry in element.description:
                    literal = Literal(entry.text, lang=entry.language)
                    self.assertIn((shape, SH.description, literal), self.graph)
                    self.assertIn((predicate, RDFS.comment, literal), self.graph)
                    records = list(self.concepts.subjects(DT.refersTo, shape))
                    self.assertEqual(1, len(records))
                    self.assertIn((records[0], SH.description, literal), self.concepts)

    def test_relationships_are_schema_not_instance_assertions(self):
        for path, element in iter_elements(self.model.submodel_elements):
            if type(element).__name__ != "RelationshipElement":
                continue
            with self.subTest(path=path):
                shape = compute_uri(self.model.id, path + "/shape")
                predicate = make_semantic_predicate("engineeringbom", element.id_short)
                self.assertIn((predicate, RDF.type, OWL.ObjectProperty), self.graph)
                self.assertIn((shape, SH["class"], None), self.graph)
                self.assertNotIn(
                    (compute_uri(self.model.id, path), RDF.type, None), self.graph
                )

    def test_property_datatypes(self):
        for path, element in iter_elements(self.model.submodel_elements):
            if type(element).__name__ == "Property" and element.value_type is not None:
                shape = compute_uri(self.model.id, path + "/shape")
                self.assertTrue(list(self.graph.objects(shape, SH.datatype)))


if __name__ == "__main__":
    unittest.main()
