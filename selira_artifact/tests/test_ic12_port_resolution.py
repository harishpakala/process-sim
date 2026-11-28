import pytest
from selira.language.parser.frontend import parse_safsl
from selira.runtime.port_resolution import resolve_port_dependencies, affected_ports

ASSETS = "https://example.org/sm/asset-inventory-template"
PRODUCTS = "https://example.org/sm/product-catalog-template"

SOURCE = """
Specification Governance {
 StartTerminal=[LP_01];
 Ref Submodel AssetInventory = "https://example.org/sm/asset-inventory-template";
 Ref Submodel ProductCatalog = "https://example.org/sm/product-catalog-template";
 Process LP_01 {
  Interface {
   Terminal Input START;
   Terminal Output DONE;
   Port Input Assets = AssetInventory;
   Port Input Products = ProductCatalog;
   Port Input Context;
   Port Output Result;
  }
  Body { assign(Result, Context); }
 }
}
"""


def dependencies(source=SOURCE):
    return resolve_port_dependencies(parse_safsl(source).children[0])


def test_ic12_port_aliases():
    deps = dependencies()
    assert [(d.process, d.port, d.template_id) for d in deps] == [
        ("LP_01", "Assets", ASSETS), ("LP_01", "Products", PRODUCTS)]


@pytest.mark.parametrize("template,expected", [
    (ASSETS, ["Assets"]), (PRODUCTS, ["Products"]), ("urn:other", [])])
def test_ic12_port_activation_scope(template, expected):
    assert [d.port for d in affected_ports(dependencies(), template_id=template,
                                          candidate=object())] == expected


@pytest.mark.parametrize("source", [
    SOURCE.replace("Assets = AssetInventory", "Assets = Unknown"),
    SOURCE.replace("Assets = AssetInventory", "Assets = AssetInventory.Assets"),
    SOURCE.replace("Ref Submodel ProductCatalog", "Ref Submodel AssetInventory"),
    SOURCE.replace("Port Input Context;", "Port Input Assets;"),
])
def test_ic12_port_invalid_binding(source):
    with pytest.raises(ValueError):
        dependencies(source)


def test_ic12_port_requires_candidate():
    with pytest.raises(ValueError):
        affected_ports(dependencies(), template_id=ASSETS, candidate=None)
