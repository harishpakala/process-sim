import asyncio
from datetime import datetime, timezone
from asyncua import Client

ENDPOINT = "opc.tcp://127.0.0.1:4841/process-sim/"
NAMESPACE = "urn:process-sim:opcua"

async def main():
    async with Client(url=ENDPOINT) as client:
        ns = await client.get_namespace_index(NAMESPACE)

        time_node = await client.nodes.objects.get_child([
            f"{ns}:TEP",
            f"{ns}:Simulation",
            f"{ns}:TimeHours",
        ])

        signal_node = client.get_node(
            f"ns={ns};s=TEP.Measurements.XMEAS9"
        )

        for i in range(5):
            simulation_hours = await time_node.read_value()
            data_value = await signal_node.read_data_value()

            print({
                "read": i + 1,
                "simulation_seconds": float(simulation_hours) * 3600,
                "XMEAS9": data_value.Value.Value,
                "status": str(data_value.StatusCode),
                "source_timestamp": str(data_value.SourceTimestamp),
                "read_at_utc": datetime.now(timezone.utc).isoformat(),
            })

            await asyncio.sleep(3)

asyncio.run(main())
