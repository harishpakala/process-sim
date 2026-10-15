# ProductCatalog engineering compatibility audit

Audit date: 2026-10-15. Target branch: `feature/tep-nexus-ui`.

## Method and limitations

Manufacturer specifications were transcribed conservatively into the ProductCatalog. Product specifications establish a product type, **not** suitability for the installed application. Values and units are retained as strings until a structured AAS unit/semantic scheme is agreed. Manufacturer URLs are embedded per product. No actual TEP process envelopes, wiring diagrams, PLC hardware specifications, load calculations, or chemical compatibility assessments were provided; **installation suitability is not certified**.

## Findings and required actions

| Product | ECAD / engineering use | Status | Evidence gap / next action |
|---|---|---|---|
| SMC PFMV505-1 | 10 process-flow measurements | **High-priority review** | 0–0.5 L/min dry-air/nitrogen minute-flow sensor; compare TEP flow range, medium, pressure and 1–5 V nonlinear output; confirm PLC analog input/scaling. |
| SMC PSH-L2-01-W | 5 process-temperature measurements | **High-priority review** | Condensation / humidity switch, not established as a process-temperature transmitter; confirm exact variant and replace or justify selection for process temperature. |
| IFM LW2720 | 3 vessel-level measurements | **Conditional** | Check vessel pressure (8 bar product rating), temperature derating, dielectric constant, medium compatibility, vessel geometry and radar installation. |
| Schneider A9MEM3555 | Compressor-work measurement | **Conditional** | Measures electrical energy/power using Rogowski coils and Modbus; demonstrate equivalence or conversion to the simulated compressor-work variable; check Modbus gateway and scaling. |
| Siemens S55264-V193 | 12 process valves | **High-priority review** | HVAC pressure-independent control valve body; confirm process media, temperature, pressure, Cv/Kvs, flow range, compatible actuator and fail-safe behavior. Valve body is not a complete actuated assembly. |
| Rittal 3244100 | 4 process motors | **High-priority review** | Enclosure cooling filter fan, not reactor agitator / process pump / compressor drive. Replace assignments with correctly sized process motor equipment or document exceptional design basis. |
| SMC PSE550 | Proposed 3 pressure instruments | **High-priority review** | 0–2 kPa differential-pressure range, gas-only compatibility; verify gauge/absolute/differential measurand, process pressure and signal variant. Current feature-branch CSV still assigns PSH-L2-01-W to these pressure points; resolve source revision first. |
| Phoenix Contact 2938581 | Proposed DC power supply TA1 | **Conditional** | Confirm TA1 is the ECAD DCPowerSupply, reconcile CSV shorthand PXC to Phoenix Contact, calculate 24 V/5 A load and inrush/derating, verify wiring. |
| PLCBox | Unidentified device | **Unresolved** | Manufacturer and part number absent; identify PLC, I/O modules, power and network interfaces. |

## Cross-domain inconsistencies

1. **Source revision conflict:** `docs/InstrumentationFunctions.csv` on `feature/tep-nexus-ui` assigns `PSH-L2-01-W` to pressure tags `PI-1101`, `PI-1301`, `PI-1501`, whereas another reviewed CSV version assigned `PSE550`. Do not silently overwrite ECAD assignments before selecting authoritative revision.
2. **PLC interface:** CSV addresses such as `I10.x` and `Q10.x` do not themselves establish the analog, IO-Link or Modbus hardware path. Provide PLC module types, terminal mapping, scaling and signal conversion.
3. **Catalog identity:** `PXC` is retained as an engineering source abbreviation; catalog product `2938581` is attributed to Phoenix Contact according to its manufacturer documentation. This does not confirm installation identity.
4. **Provenance:** The ProductCatalog records manufacturer product specifications only. No engineering suitability statuses in `product_catalog_ecad_coverage.json` have been upgraded by this audit.

## Sources

- SMC_PFMV505_1: https://static.smc.eu/pdf/PFMV5-PFGV301_EU.pdf
- SMC_PSH_L2_01_W: https://static.smc.eu/pdf/PSH_EU.pdf
- IFM_LW2720: https://www.ifm.com/gb/en/product/LW2720
- Schneider_A9MEM3555: https://www.se.com/de/de/product/A9MEM3555/
- Siemens_S55264_V193: https://de.rs-online.com/web/p/druckunabhangige-steuerventile-picv/0636071
- Rittal_3244100: https://www.rittal.com/com-en/products/PG20231215KLI101/PG20231215KLI102/PG20240718KLI001/PRO0299?variantId=3244100
- SMC_PSE550: https://static.smc.eu/binaries/content/assets/smc_global/product-documentation/operation-manuals/en/om_pse550_omg0009en-d.pdf
- PXC_2938581: https://www.phoenixcontact.com/ro-ro/produse/power-supply-quint-ps-100-240ac24dc-5-2938581

## Verification to finish

Obtain process minimum/normal/maximum conditions, medium compositions, valve sizing and actuator schedules, motor duty points, PLC and I/O module bill of materials, wiring diagrams, and 24 V load budget. Resolve source CSV version. Review all flagged mappings before marking any installed device suitable.
