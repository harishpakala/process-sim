# TEP pressure transmitter replacement review (engineering candidate)

Status: **candidate selection, not approved installed equipment**.

## Scope

The AssetInventory currently associates SMC_PSE550 with:
- TEP_XMEAS7 — reactor pressure (TEP nominal 2705.0 kPa gauge)
- TEP_XMEAS13 — separator pressure (TEP nominal 2633.7 kPa gauge)
- TEP_XMEAS16 — stripper pressure (TEP nominal 3102.2 kPa gauge)

These are benchmark base-case values, **not** transmitter operating limits, design pressures or safety setpoints.

The ProductCatalog's SMC_PSE550 lists a rated differential-pressure range of 0–2 kPa, operating pressure −50 to 50 kPa and proof pressure 65 kPa. This is a high-priority application mismatch requiring review. Do not assume the sensor sees unconditioned process pressure.

## Manufacturer candidate shortlist

1. **Endress+Hauser Cerabar PMP51B** (preferred family for engineering evaluation). Manufacturer states gauge and absolute measuring principles, range up to 400 bar, process temperature −40 to +125 °C standard, up to +400 °C with diaphragm seal (configuration dependent), 4–20 mA HART options. https://www.endress.com/en/field-instruments-overview/pressure/pressure-transmitter-cerabar-pmp51b
2. **Emerson Rosemount 3051** pressure transmitter family. Inline configurations and 4–20 mA HART options; specific pressure range depends on selected model code. https://www.emerson.com/en/measurement-instrumentation/products/rosemount-3051-pressure-transmitter-family
3. **Yokogawa EJA530E** inline gauge pressure transmitter. Confirm configured sensor range, wetted materials and installation conditions. https://www.yokogawaelectric.org/solutions/products-and-services/measurement/field-instruments-products/pressure-transmitters/gauge-pressure/eja530e/index.html

## Mandatory checks before approving any replacement

- Pressure basis: gauge vs absolute vs differential (benchmark indicates gauge for these signals).
- Calibrated span, upper range limit and overpressure limits for the exact ordering code, allowing for the actual maximum credible pressure, not merely base-case values.
- Process temperature at tapping point, impulse-line / remote-seal design and thermal isolation.
- Process fluid compatibility, wetted materials, corrosion and pressure-boundary rating.
- Connection, mounting, hazardous-area requirements, safety and communication interface.
- Verification of actual installed instrument identity vs illustrative benchmark association.
- Manufacturer documentation for the exact selected variant and engineering approval.

## Semantic alignment policy

- Preserve the original SMC_PSE550 catalog entry for provenance; do not overwrite its manufacturer's specifications.
- Mark SMC_PSE550-to-XMEAS7/13/16 as **replacement_review_required** rather than a validated physical installation.
- Record replacement families as **candidates**, not installed asset references.
- Do not invent property-level ECLASS IRDIs or derive limits from ECLASS product classification.
- The process pressure is a measured quantity; transmitter range is a manufacturer capability; benchmark shutdown constraints are separate process constraints.
- No numerical compliance check is authorized until quantity, unit, reference pressure basis, applicability, signal binding and configuration are verified.

## Next action

Select a specific configured PMP51B (or alternate) ordering code after confirming the three measurement-point conditions. Then update ProductCatalog with the exact part number and its source-backed technical properties, and update AssetInventory references in a separate reviewed change.
