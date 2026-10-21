# TEP NEXUS — equipment requirements and candidate fit-gap assessment

**Status:** Preliminary engineering screening, **not equipment sizing or purchase approval**. Date: 2026-10-21.

## Evidence hierarchy and units

- **Project evidence:** `README.md` identifies the ProfBraatz TEP reference model and the project's selected ECLASS mapping. The project model has not been executed for this review; no claim is made that values below are a current `process-sim` run.
- **TEP measurement definitions:** [ProfBraatz API measurement reference](https://github.com/jkitchin/tennessee-eastman-profbraatz/blob/master/docs/api.md) identifies XMEAS indices and units. Measurements are simulated **operating outputs**, not certified mechanical design limits.
- **Published example steady state:** [DYCOPS 2010 operability analysis, Table 1](https://skoge.folk.ntnu.no/prost/proceedings/dycops-2010/Papers_DYCOPS2010/TuMT3-01.pdf) reports reactor 393 K and 2769 kPa(g), separator 353 K and 2679 kPa(g), stripper 337 K, reactor liquid volume 14.2 m³, separator liquid volume 5.81 m³, stripper liquid volume 4.09 m³, reactor heat duty -6618 kW, separator heat duty -3074 kW, stripper heat duty 169 kW. These values are **published study operating conditions**; they are **not the project's verified simulation baseline**, vessel total volume, mechanical design ratings, or a universally applicable TE operating point. Heat duty sign conventions require checking before vendor comparison.
- **Do not conflate sources:** Siemens documentation quotes a different reactor operating pressure of 2705 kPa in a particular operating case. Different papers and operating modes need not share one steady state. [Siemens source](https://support.industry.siemens.com/cs/attachments/101978659/101978659_pcs7_mpc10x10_en_V11.pdf).

## Equipment-to-model traceability

| Equipment | Available TEP signals / external illustrative evidence | Preliminary candidate | Fit-gap verdict | Minimum additional sizing / selection inputs |
|---|---|---|---|---|
| Reactor | XMEAS(7) reactor pressure kPa(g); (8) level %; (9) temperature °C; (21) reactor cooling-water outlet °C. Published example 393 K, 2769 kPa(g), 14.2 m³ **liquid holdup**, -6618 kW reactor duty. | De Dietrich BE glass-lined reactor | **HOLD:** published operating pressure is ~27.69 bar(g); independently verify candidate's pressure rating. Previous shortlist indicated standard +6 bar, which would be **incompatible** if confirmed for the proposed configuration. Do not accept BE without pressure-rated evidence. | Vessel total volume and geometry, maximum pressure/temperature excursions, mechanical design pressure, heat-transfer area, materials/corrosion, agitation and seals, applicable code |
| Condenser | XMV(11) condenser cooling-water flow control; XMEAS(22) condenser/sep cooling-water outlet temperature; published -3074 kW **separator-side** heat duty, not a validated standalone condenser duty | Alfa Laval Olmi shell-and-tube | **OPEN:** offering exists, but no equipment-specific duty or thermal design point established | Vapor/liquid stream inlet and outlet states, actual condenser duty, cooling-water inlet/outlet, UA, fouling, allowable pressure drop, mechanical pressure |
| Gas–liquid separator | XMEAS(11) temperature °C; (12) level %; (13) pressure kPa(g); (14) underflow m³/h. Published 353 K, 2679 kPa(g), 5.81 m³ liquid holdup | Didion DSL | **OPEN:** compare manufacturer pressure-rated configuration against ~26.79 bar(g) *illustrative operating pressure* and gas/liquid service; no fit demonstrated | Design pressure, vapor and liquid volumetric rates at conditions, entrainment spec, liquid residence time, internals, vessel dimensions/materials |
| Recycle compressor | XMEAS(5) recycle flow kscmh; (20) compressor work kW; XMV(5) compressor recycle valve; XMEAS(13)/(16) separator/stripper pressure signals **not sufficient** to reconstruct a rated compressor map | Atlas Copco GT-Series | **OPEN:** GT family exists, but neither centrifugal technology nor duty point is established by TEP | Suction/discharge P,T, gas composition/MW, actual flow at suction, polytropic head, efficiency, shaft power, turndown, seal system and drive |
| Stripper | XMEAS(15) level %; (16) pressure kPa(g); (17) underflow m³/h; (18) temperature °C; (19) steam flow kg/h; XMV(9) steam valve. Published 337 K, 4.09 m³ liquid holdup, +169 kW duty | Sulzer engineered stripping unit | **OPEN:** complete offering identified, but mass-transfer design missing | Separation target, feed composition and flow, steam rate, stages/packing/trays, diameter/height, temperature/pressure envelope, materials |
| Reactor agitator | XMV(12) agitator speed manipulation; no verified shaft power/torque or mixing geometry extracted | EKATO HWL-N | **OPEN:** mechanical selection impossible from speed manipulation alone | Vessel geometry, fluid viscosity/density, impeller type, mixing duty, rpm, shaft power, torque, seal pressure and temperature |
| Separate motors | XMEAS(20) compressor work **is not verified electric motor nameplate power**; XMV(12) agitator speed does not define motor rating; no per-pump duty here | ABB AMZ synchronous family | **OPEN / assumption check:** synchronous motor is an explicit TEP NEXUS modeling assumption, not proven for every drive. ABB family may be oversized for small pumps/agitators | Confirm separately represented drives, shaft loads, speed, duty cycle, voltage/frequency, VFD/start, enclosure and hazardous-area classification |

## Screening conclusions

1. **Reactor is the highest-priority incompatibility risk.** The published example reactor pressure (~27.69 bar gauge) cannot be compared safely with a candidate family's nominal pressure without checking exact model, code, temperature, and maximum allowable working pressure. The previously cited +6 bar BE rating, if verified, rules out that configuration for this example.
2. **Condenser duty is not established** by simply reusing the separator's published -3074 kW heat duty; equipment boundaries and the source model's heat accounting must be reconciled.
3. **Holdup is not vessel total capacity.** The published liquid volumes are operating holdups, not vessel size requirements.
4. **Compressor work is not motor nameplate power.** Electrical efficiency, margins and drive arrangements require separate engineering.
5. **No seven-candidate ProductCatalog promotion yet.** The manufacturer selection register remains a research shortlist until each candidate passes process, mechanical, source and ECLASS checks.

## Reproducible project validation workflow (to execute)

1. Run a controlled, documented **fault-free steady-state** simulation in the actual `process-sim` / ProfBraatz adapter. Capture scenario, model version, initial conditions, run duration, stability criterion and engineering-unit mapping.
2. Export time-averaged and min/max values for XMEAS(5), (7)–(9), (11)–(13), (15)–(20), (21)–(22), plus XMV(5), (9), (11), (12). Preserve measurement units and timestamps.
3. Separate **steady-state operating point**, **normal operating envelope**, **upset envelope**, and **mechanical design requirements**. Do not infer latter three from one run.
4. For each vendor family, obtain official model-specific datasheets and check pressure/temperature, capacity, medium/material, sizing, code and interface.
5. Record each result as **Pass / Fail / Unknown** with evidence URL and configuration; only approve ProductCatalog integration when sufficient checks pass.
6. Validate ECLASS IRDI release and assignability before copying any of the working class references into new AAS instances.

## Manufacturer candidates

See [equipment manufacturer selection register](equipment_manufacturer_selection_register.md) for the seven candidate families, official source links and existing ECLASS IRDIs.
