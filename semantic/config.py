"""Built-in semantic lifting targets; run scripts without command-line arguments."""
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TARGETS = (
    ("dexpi", ROOT / "semantic/templates/dexpi_template.json", ROOT / "examples/aas/tep_dexpi_instance.json"),
    ("ecad", ROOT / "semantic/templates/ecad_template.json", ROOT / "examples/aas/tep_ecad_instance.json"),
    ("productcatalog", ROOT / "semantic/templates/product_catalog_template.json", ROOT / "examples/aas/product_catalog_instance.json"),
    ("assetinventory", ROOT / "semantic/templates/asset_inventory_template.json", ROOT / "examples/aas/asset_inventory_instance.json"),
    ("opcuaconnectivity", ROOT / "semantic/templates/opcua_connectivity_template.json", ROOT / "examples/aas/tep_opcua_connectivity_instance.json"),
    ("engineeringbom", ROOT / "semantic/templates/engineering_bom_template.json", ROOT / "examples/aas/tep_engineering_bom_instance.json"),
)
OUTPUT = ROOT / "out" / "semantic"
