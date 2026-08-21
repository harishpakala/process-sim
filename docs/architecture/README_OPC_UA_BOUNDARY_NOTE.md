# OPC UA external-control boundary

The operational control boundary is OPC UA. External SCADA/HMI systems, PID/MPC controllers, or simulated PLCs read XMEAS values and write XMV values through OPC UA. The TEP digital twin does not embed the experimental external controller.

The OPC UA operational launcher runs the TEP backend in manual-control mode and reports `Simulation/ControlMode = external_opcua`.

```text
External PID / MPC / simulated PLC
              │
              │ OPC UA write
              ▼
           XMV1..XMV12
              │
              ▼
        TEP digital twin
              │
              │ OPC UA read
              ▼
          XMEAS1..XMEAS41
```

The native TEP closed-loop controller remains available as a reference controller for non-OPC-UA benchmark paths. It is not the operational controller when external OPC UA control is active.
