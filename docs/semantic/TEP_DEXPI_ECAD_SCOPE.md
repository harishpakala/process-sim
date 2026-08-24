# TEP DEXPI / ECAD Integration Scope

## Purpose

The current semantic-digital-thread scope models the TEP physical engineering functions in DEXPI and binds those functions to operational variables through the ECAD layer.

The distinction is intentional:

```text
DEXPI physical engineering model
        |
        | AssetIdentifier
        v
ECAD / automation model
        |
        +--> XMEAS / XMV
        +--> PLC address
        +--> OPC UA NodeId
        +--> other operational endpoints
```

## Current TEP signal scope

The current simulator integration uses:

- **22 continuous process measurements:** `XMEAS1`–`XMEAS22`
- **12 manipulated variables:** `XMV1`–`XMV12`

The DEXPI instance represents the 22 physical measurement functions as `InstrumentationFunction` SMCs and the 12 manipulated functions as `ActuatingFunction` SMCs.

Current instance-assigned identifiers are deliberately separate from the canonical TEP names. For example, `FI_101` is an identifier assigned by this project; it is **not claimed to be an original Vogel PFD tag**. The same convention is used for `TI_*`, `LI_*`, `PI_*`, `JI_*`, `VC_*`, and `SC_*` identifiers.

## 22 instrumentation functions

The current inventory is:

- 10 Flow Indicators (`FI_101`–`FI_110`)
- 5 Temperature Indicators (`TI_101`–`TI_105`)
- 3 Level Indicators (`LI_101`–`LI_103`)
- 3 Pressure Indicators (`PI_101`–`PI_103`)
- 1 compressor power indicator (`JI_101`)

The corresponding TEP operational mappings are maintained separately:

```text
FI_101 -> XMEAS1
FI_102 -> XMEAS2
FI_103 -> XMEAS3
FI_104 -> XMEAS4
FI_105 -> XMEAS5
FI_106 -> XMEAS6
PI_101 -> XMEAS7
LI_101 -> XMEAS8
TI_101 -> XMEAS9
FI_107 -> XMEAS10
TI_102 -> XMEAS11
LI_102 -> XMEAS12
PI_102 -> XMEAS13
FI_108 -> XMEAS14
LI_103 -> XMEAS15
PI_103 -> XMEAS16
FI_109 -> XMEAS17
TI_103 -> XMEAS18
FI_110 -> XMEAS19
JI_101 -> XMEAS20
TI_104 -> XMEAS21
TI_105 -> XMEAS22
```

## 12 actuating functions

The current manipulated-variable inventory is:

```text
VC_101 -> XMV1
VC_102 -> XMV2
VC_103 -> XMV3
VC_104 -> XMV4
VC_105 -> XMV5
VC_106 -> XMV6
VC_107 -> XMV7
VC_108 -> XMV8
VC_109 -> XMV9
VC_110 -> XMV10
VC_111 -> XMV11
SC_101 -> XMV12
```

`VC_*` identifiers are project-assigned identifiers for valve/control functions. `SC_101` is used for the agitator-speed control function.

## XMEAS23-XMEAS41 are out of current DEXPI/ECAD scope

The canonical TEP reference still contains **41 XMEAS measurements**. `XMEAS23`–`XMEAS41` are composition measurements. They are not interpreted here as 19 additional physical sensors or 19 additional DEXPI `InstrumentationFunction` instances.

Their operational characteristics include slower sampled measurement behavior. The TEP reference documentation describes reactor-feed and purge-gas composition measurements with a sampling frequency/dead time of `0.1 h`, and product composition measurements with `0.25 h` sampling/dead time.

Therefore, for the current simulator integration, these variables are deliberately **out of scope** for the DEXPI-to-ECAD operational binding.

This does **not** mean that the variables are absent from TEP. They remain part of the canonical simulator interface and may be incorporated in a future analyzer/composition integration.

The scope decision is:

```text
Canonical TEP
├── XMEAS1-XMEAS22   -> current DEXPI/ECAD scope
├── XMEAS23-XMEAS41  -> canonical TEP, currently out of scope
└── XMV1-XMV12       -> current DEXPI/ECAD scope
```

## Sampling frequency and dead time

Sampling frequency and dead time are operational properties. They should not be added to the DEXPI physical `InstrumentationFunction` merely because a TEP measurement has a particular simulator sampling interval.

For example:

```text
OperationalVariable
    id = XMEAS23
    samplingFrequency = 0.1 h
    deadTime = 0.1 h
```

belongs to the operational representation. DEXPI instead describes the physical engineering function and its measured engineering concept.

## Semantic annotations

The DEXPI instance uses the `OntoConcept` qualifier on each function SMC:

```text
InstrumentationFunction SMC
    OntoConcept = InstrumentationFunction

ActuatingFunction SMC
    OntoConcept = ActuatingFunction

Equipment SMC
    OntoConcept = Equipment
```

`MeasuredVariable` and `ActuatedVariable` use AAS `valueType` for the datatype. Quantity semantics are expressed through `semanticId`; for measured engineering concepts, QUDT quantity-kind/unit references are used where established.

Instance-level physical identifiers such as `FI_101` and `VC_101` belong to the instance, not the reusable DEXPI template.

## Future extension

If composition/analyzer integration becomes necessary, `XMEAS23`–`XMEAS41` can be introduced on the operational side without changing the current DEXPI physical-function model. This keeps the DEXPI representation focused on physical engineering identity while allowing the operational model to carry sampling, dead time, PLC/OPC UA addressing, and other automation-specific properties.
