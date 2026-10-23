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

## Benchmark-based signal review (Downs & Vogel, 1993, Table 4)

Source: https://users.abo.fi/khaggblo/RS/Downs.pdf (page 249). Values are **nominal process measurements, not sensor ranges**.

| Signal | Measured quantity | Base case | Unit | Evaluation |
|---|---|---:|---|---|
| XMEAS1 | A feed | 0.25052 | kscmh | Gas standard-volume flow; conversion/reference state required |
| XMEAS2 | D feed | 3664.0 | kg/h | Mass-flow candidate |
| XMEAS3 | E feed | 4509.3 | kg/h | Mass-flow candidate |
| XMEAS4 | A and C feed | 9.3477 | kscmh | Gas standard-volume flow; conversion/reference state required |
| XMEAS5 | Recycle | 26.902 | kscmh | High gas throughput; meter sizing required |
| XMEAS6 | Reactor feed | 42.339 | kscmh | High gas throughput; meter sizing required |
| XMEAS10 | Purge | 0.33712 | kscmh | Gas standard-volume flow; conversion/reference state required |
| XMEAS14 | Separator underflow | 25.160 | m³/h | Liquid volume flow; density needed for mass conversion |
| XMEAS17 | Stripper underflow | 22.949 | m³/h | Liquid volume flow; density needed for mass conversion |
| XMEAS19 | **Stripper steam flow** | 230.31 | kg/h | Steam service requires dedicated instrument verification |

**Correction:** XMEAS19 is steam flow, not an unspecified stripper process stream. A Promass F 300 family page lists steam among application categories but does not establish suitability of an unspecified configured meter for this duty.

**Decision:** Do not approve or map a common F 300 to all ten signals. Evaluate separately (1) standard-volume gas streams, (2) liquid mass/volume streams, and (3) steam. Verify medium, measurement unit, normal and fault range, line sizing, pressure, and selected order code. Keep ECLASS IRDIs pending.
