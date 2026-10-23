# Optional physical pump extension

This is a **separate, disabled-by-default AAS concept**, not a change to the original Tennessee Eastman benchmark or to active ProductCatalog/AssetInventory. See `examples/aas/extensions/optional_pump_extension_instance.json`.

| Proposed asset | Stream association | Nominal stream flow | Status |
|---|---|---|---|
| TEP_P_1301_Proposed | XMEAS14 separator underflow | 25.160 m³/h | Concept only |
| TEP_P_1501_Proposed | XMEAS17 stripper underflow | 22.949 m³/h | Concept only |

**Interpretation correction:** Some published TEP flowsheet renderings show a pump symbol near the stripper/product outlet. Thus, absence of a separate pump state does **not** prove the physical flowsheet contains no pump. It means the available benchmark does not expose an independently sizeable pump hydraulic model. Neither the illustration nor the motor records establish a specific pump rating. See https://www.mic-journal.no/PDF/2000/MIC-2000-4-2.pdf and https://kitchingroup.cheme.cmu.edu/tep-rust/notebooks/01-getting-started.html .

The extension explicitly does not assert that M-1301 or M-1501 is an actual physical motor or that XMEAS14/XMEAS17 equals pump throughput under all conditions. M-1401 remains a gas compressor-drive concept.

## Required for engineering activation

1. Confirm P&ID topology, suction/discharge connections and whether each pump exists.
2. Define normal/min/max suction and discharge absolute pressures, static elevations, pipe losses and liquid thermophysical properties.
3. Calculate differential head, NPSHa and hydraulic power at min/normal/max flows.
4. Select pressure-rated process-pump family/configuration using OEM performance curves, NPSHr, casing pressure/temperature and materials.
5. Add motor/drive coupling, instrumentation, failure modes and separate PLC/OPC UA tags only if supported by the extended simulation.
6. Validate AAS JSON/schema and repository tests before integration.

No pump model, vendor order code, ECLASS IRDI, ProductReference or fabricated numerical head/power has been assigned.
