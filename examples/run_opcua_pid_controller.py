"""Run a PLC-style PID controller against process-sim exclusively via OPC UA.

This example deliberately contains no process-sim Python API calls. The
controller reads XMEAS9 and XMV10 over OPC UA and writes XMV10 back over OPC UA.
It is intended as a small external-control reference that can later be
replaced by a simulated PLC runtime, MATLAB/Simulink, or an MPC implementation.
"""

from __future__ import annotations

import argparse
import asyncio

from asyncua import Client


class PIDController:
    """Minimal cyclic PID controller suitable for an OPC UA client example."""

    def __init__(
        self,
        setpoint: float,
        kp: float,
        ki: float,
        kd: float,
        output_min: float,
        output_max: float,
    ) -> None:
        if output_min >= output_max:
            raise ValueError("output_min must be smaller than output_max")
        self.setpoint = float(setpoint)
        self.kp = float(kp)
        self.ki = float(ki)
        self.kd = float(kd)
        self.output_min = float(output_min)
        self.output_max = float(output_max)
        self._integral = 0.0
        self._previous_error: float | None = None

    def reset(self) -> None:
        self._integral = 0.0
        self._previous_error = None

    def calculate(self, measurement: float, dt_seconds: float, current_output: float) -> float:
        if dt_seconds <= 0:
            raise ValueError("dt_seconds must be > 0")

        error = self.setpoint - float(measurement)
        integral_candidate = self._integral + error * dt_seconds
        derivative = (
            0.0
            if self._previous_error is None
            else (error - self._previous_error) / dt_seconds
        )

        raw_output = (
            current_output
            + self.kp * error
            + self.ki * integral_candidate
            + self.kd * derivative
        )
        output = min(self.output_max, max(self.output_min, raw_output))

        # Basic conditional integration prevents the integral term from
        # accumulating while the output is pinned at a limit in the same
        # direction as the control error.
        saturated_high = output >= self.output_max and error > 0
        saturated_low = output <= self.output_min and error < 0
        if not (saturated_high or saturated_low):
            self._integral = integral_candidate

        self._previous_error = error
        return output


async def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run an external PLC-style PID controller over OPC UA"
    )
    parser.add_argument(
        "--endpoint",
        default="opc.tcp://127.0.0.1:4841/process-sim/",
        help="OPC UA endpoint",
    )
    parser.add_argument(
        "--setpoint",
        type=float,
        default=120.40,
        help="XMEAS9 reactor-temperature setpoint in deg C",
    )
    parser.add_argument("--kp", type=float, default=1.0, help="PID proportional gain")
    parser.add_argument("--ki", type=float, default=0.01, help="PID integral gain")
    parser.add_argument("--kd", type=float, default=0.0, help="PID derivative gain")
    parser.add_argument("--output-min", type=float, default=0.0, help="Minimum XMV10 command")
    parser.add_argument("--output-max", type=float, default=100.0, help="Maximum XMV10 command")
    parser.add_argument(
        "--cycle-seconds",
        type=float,
        default=1.0,
        help="Controller cycle period in wall-clock seconds",
    )
    parser.add_argument(
        "--duration-hours",
        type=float,
        default=2.0,
        help="Controller runtime in simulated hours",
    )
    args = parser.parse_args()

    if args.cycle_seconds <= 0:
        raise ValueError("cycle-seconds must be > 0")
    if args.duration_hours <= 0:
        raise ValueError("duration-hours must be > 0")

    client = Client(url=args.endpoint)
    controller = PIDController(
        setpoint=args.setpoint,
        kp=args.kp,
        ki=args.ki,
        kd=args.kd,
        output_min=args.output_min,
        output_max=args.output_max,
    )

    async with client:
        namespace_index = await client.get_namespace_index("urn:process-sim:opcua")
        objects = client.nodes.objects
        tep = await objects.get_child([f"{namespace_index}:TEP"])
        simulation = await tep.get_child([f"{namespace_index}:Simulation"])
        measurements = await tep.get_child([f"{namespace_index}:Measurements"])
        manipulated_variables = await tep.get_child(
            [f"{namespace_index}:ManipulatedVariables"]
        )

        control_mode = await simulation.get_child(
            [f"{namespace_index}:ControlMode"]
        ).read_value()
        if control_mode != "external_opcua":
            raise RuntimeError(
                "process-sim is not in external_opcua control mode; "
                "start examples/run_opcua_server.py first"
            )

        time_node = await simulation.get_child([f"{namespace_index}:TimeHours"])
        running_node = await simulation.get_child([f"{namespace_index}:Running"])
        start_node = await simulation.get_child([f"{namespace_index}:Start"])
        stop_node = await simulation.get_child([f"{namespace_index}:Stop"])
        xmeas9 = await measurements.get_child([f"{namespace_index}:XMEAS9"])
        xmv10 = await manipulated_variables.get_child([f"{namespace_index}:XMV10"])

        running = await running_node.read_value()
        if not running:
            await start_node.call()

        start_time_hours = float(await time_node.read_value())
        print(f"Connected to {args.endpoint}")
        print("Controller: external PLC-style PID")
        print(f"Setpoint: XMEAS9 = {args.setpoint:.3f} deg C")
        print("Actuator: XMV10")

        try:
            while True:
                simulation_time = float(await time_node.read_value())
                if simulation_time - start_time_hours >= args.duration_hours:
                    break

                measurement = float(await xmeas9.read_value())
                current_output = float(await xmv10.read_value())
                command = controller.calculate(
                    measurement,
                    args.cycle_seconds,
                    current_output,
                )
                await xmv10.write_value(command)

                print(
                    f"t={simulation_time:8.4f} h  "
                    f"XMEAS9={measurement:9.4f}  "
                    f"XMV10={command:9.4f}",
                    flush=True,
                )
                await asyncio.sleep(args.cycle_seconds)
        finally:
            await stop_node.call()


if __name__ == "__main__":
    asyncio.run(main())
