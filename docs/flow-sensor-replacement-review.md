# TEP flow sensor replacement review

Status: **review only — no flow instrument replacement approved**.

## Current assignments

AssetInventory maps XMEAS1, XMEAS2, XMEAS3, XMEAS4, XMEAS5, XMEAS6, XMEAS10, XMEAS14, XMEAS17 and XMEAS19 to `https://example.org/product-types/SMC_PFMV505_1`.

The SMC PFMV505-1 is a miniature dry-air/N2 sensor with rated flow 0–0.5 L/min, operating pressure −100 to 400 kPa, and nonlinear 1–5 V output. It is not a justified common instrument for the TEP benchmark's industrial process streams.

Manufacturer source: https://static.smc.eu/pdf/PFMV5-PFGV301_EU.pdf

## Replacement candidate

**Endress+Hauser Proline Promass F 300 (8F3B)** is a preferred *family for evaluation*, not an approved assignment. Coriolis measurement supports liquid and gas mass flow. Manufacturer specifications list family measuring range 0–2,200,000 kg/h and process pressure class up to PN 100 (configuration dependent). Manufacturer source: https://www.endress.com/en/field-instruments-overview/flow-measurement-product-overview/coriolis-flowmeter-promass-f300-8f3b

## Required validation before mapping

1. Obtain benchmark nominal values and **units** for each XMEAS flow; distinguish gas and liquid streams, mass and volumetric flow, and any standard-state volume units.
2. Verify the flowmeter's ordered diameter/range, pressure rating and phase applicability for each signal. Family-wide maximum is not the configured sensor's range.
3. Avoid treating SMC PFMV505-1's range as a TEP process limit.
4. Keep existing ProductReferences for provenance until replacements are approved.
5. Resolve ECLASS classification and property IRDIs from authoritative ECLASS data; do not reuse the SMC classification IRDI for a Coriolis meter.
6. Keep OPC UA mappings provisional until verified.

No ProductCatalog or AssetInventory flow assignments are changed by this review.
