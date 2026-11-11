"""Built-in semantic lifting targets; run scripts without command-line arguments."""

# Created: 2026-10-15 
# Author: Harish
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TARGETS = (
    ("dexpi", ROOT / "semantic/templates/dexpi_template.json", ROOT / "semantic/instances/tep/tep_dexpi_instance.json"),
    ("ecad", ROOT / "semantic/templates/ecad_template.json", ROOT / "semantic/instances/tep/tep_ecad_instance.json"),
    ("productcatalog", ROOT / "semantic/templates/product_catalog_template.json", ROOT / "semantic/instances/tep/tep_product_catalog_instance.json"),
    ("assetinventory", ROOT / "semantic/templates/asset_inventory_template.json", ROOT / "semantic/instances/tep/tep_asset_inventory_instance.json"),
    ("opcuaconnectivity", ROOT / "semantic/templates/opcua_connectivity_template.json", ROOT / "semantic/instances/tep/tep_opcua_connectivity_instance.json"),
    ("engineeringbom", ROOT / "semantic/templates/engineering_bom_template.json", ROOT / "semantic/instances/tep/tep_engineering_bom_instance.json"),
)
OUTPUT = ROOT / "semantic" / "ontology"
