# OPC UA integration

The OPC UA layer is an adapter around the simulator. It does not contain TEP
process physics and it does not own the simulation clock.

## Initial namespace

```text
Objects
└── TEP
    ├── Simulation
    │   ├── TimeHours
    │   └── Running
    ├── Measurements
    │   └── XMEAS1 ... XMEAS41
    └── ManipulatedVariables
        └── XMV1 ... XMV12
```

The application namespace URI is:

```text
urn:process-sim:opcua
```

The default endpoint is:

```text
opc.tcp://0.0.0.0:4840/process-sim/
```

## Install

```bash
pip install -r requirements-opcua.txt
```

The `asyncua` package is used for the OPC UA transport.

## Minimal server

```python
import asyncio

from process_sim.backends.tep import TEPAdapter
from process_sim.protocols.opcua import OPCUAServer


async def main():
    simulator = TEPAdapter(random_seed=123)
    simulator.reset()

    server = OPCUAServer(simulator)
    await server.start()

    try:
        while True:
            await server.sync_manipulated_variables()
            simulator.step()
            await server.update(running=True)
            await asyncio.sleep(1.0)
    finally:
        await server.stop()


asyncio.run(main())
```

The example deliberately keeps stepping outside the OPC UA server. This
preserves the architectural rule that OPC UA clients do not synchronously own
the deterministic simulation loop.

## Current scope

Implemented first:

- stable application namespace
- TEP object
- simulation time and running state
- 41 raw XMEAS variables
- 12 raw XMV variables
- OPC UA writes for XMV, applied explicitly by `sync_manipulated_variables()`
- clean server start/stop lifecycle

Next additions should be made deliberately rather than hard-coding the whole
plant model at once:

1. semantic engineering names and units
2. quality/status/timestamps
3. simulation controls
4. fault/scenario controls
5. subscriptions and integration tests with an OPC UA client
6. equipment/process hierarchy
