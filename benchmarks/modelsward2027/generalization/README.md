# Multi-domain generalization challenge — design stage

Schema audit derived from the frozen index at 639c59fe9b7fcdbf8b17ec3896ea1a31c22954b1. Seven candidate owner-discrimination scenarios in DEXPI and Engineering BOM are recorded with exact SHACL evidence. These are root-to-entity property paths, not deeper nesting. Product Catalog has a Product → TechnicalProperty node edge and is a candidate for deeper evaluation; Asset Inventory and OPC UA Connectivity have only root-to-entity node edges in this index. ECAD is development-exposed.

Next: construct disjoint synthetic values, independently review questions and reference queries, validate fixtures and freeze the test manifest before LLM execution. No claims of independent authorship, SHACL conformance or measured generalization yet. No production changes.
