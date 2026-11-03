"""ProductCatalog-only ECLASS grounding and conservative answer checks.

Independent evaluation and web queries may import this module. Frozen paper
scripts remain unchanged. These checks do not prove semantic correctness.
"""
import re

ECLASS_FIELDS = ("eclass_class", "eclass_irdi", "eclass_preferred_name",
                 "eclass_verification", "qudt_product_specification",
                 "catalog_technical_specifications")
POLICY = """
ECLASS authority policy: ECLASS class codes, IRDIs, preferred names, verification
status, QUDT attributes and catalog specifications must come EXCLUSIVELY from
the supplied ProductCatalog-backed engineering_catalog records. Do not use
external knowledge or lookups, or infer ECLASS details from GraphDB, DEXPI,
ECAD, AAS identifiers or product names. A graph mapping's eclassCode is NOT
authorization to assert a ProductCatalog classification. When ProductCatalog
evidence is absent, state 'Not available in ProductCatalog' for requested
ECLASS attributes. Never invent IRDI or preferred name. Do not add unrelated
ECLASS details to identifier-relationship questions. Preserve null versus
NOT_INSTALLED_VERIFIED and PENDING_ECLASS_VERIFICATION precisely.
"""


def catalog_records(evidence):
    if not isinstance(evidence, dict):
        return []
    catalog = evidence.get("engineering_catalog")
    if catalog is None and any(isinstance(v, dict) and "product_key" in v
                               for v in evidence.values()):
        catalog = evidence
    return [v for v in catalog.values() if isinstance(v, dict) and
            v.get("product_key")] if isinstance(catalog, dict) else []


def flags(answer, limitations, evidence, question_id=None):
    if not isinstance(answer, str) or not isinstance(limitations, list) or not all(
            isinstance(v, str) for v in limitations):
        return ["INVALID_ANSWER_FORMAT"]
    records = catalog_records(evidence)
    warnings = []
    combined = answer + "\n" + "\n".join(limitations)
    # IRDIs are globally recognizable identifiers; permit only catalog-listed values.
    allowed_irdis = {r["eclass_irdi"] for r in records if r.get("eclass_irdi")}
    for irdi in set(re.findall(r"0173-1#\S+", combined)):
        if irdi.rstrip(".,;)]}") not in allowed_irdis:
            warnings.append("IRDI_NOT_IN_PRODUCTCATALOG:" + irdi)
    # Claims with explicit IRDI labels must match ProductCatalog, even when
    # the model uses a fabricated tag instead of an IRDI-shaped string.
    for match in re.finditer(r"\bIRDI\s*:\s*([^,;\s]+)", answer, re.I):
        value = match.group(1).rstrip(".,;)]}")
        if value not in allowed_irdis:
            warnings.append("IRDI_NOT_IN_PRODUCTCATALOG:" + value)
    if not records:
        if re.search(r"\bpreferred name\s*:\s*(?!not available|unknown|none)\S+", answer, re.I):
            warnings.append("PREFERRED_NAME_WITHOUT_PRODUCTCATALOG")
        if re.search(r"\bECLASS\s+(?:class|code)\s*[:=]\s*\d", answer, re.I):
            warnings.append("ECLASS_CLASS_WITHOUT_PRODUCTCATALOG")
    else:
        allowed_codes = {str(r["eclass_class"]) for r in records if r.get("eclass_class")}
        for code in set(re.findall(r"\b\d{2}-\d{2}-\d{2}(?:-\d{2})?\b", answer)):
            if code not in allowed_codes:
                warnings.append("ECLASS_CLASS_NOT_IN_PRODUCTCATALOG:" + code)
        for r in records:
            if r.get("installation_verification") is None and re.search(
                    r"(?:all|every)\s+(?:product candidates?|instruments?|assets?).{0,90}NOT_INSTALLED_VERIFIED",
                    combined, re.I | re.S):
                warnings.append("INSTALLATION_STATUS_OVERGENERALIZED")
                break
    measurements = evidence.get("measurements") if isinstance(evidence, dict) else None
    if isinstance(measurements, dict):
        for signal in measurements:
            if re.search(r"(?:no (?:information|data|evidence)|unavailable|missing)[^.\n]*\b" +
                         re.escape(signal) + r"\b", combined, re.I):
                warnings.append("CONTRADICTORY_MISSING_SIGNAL:" + signal)
    return sorted(set(warnings))
