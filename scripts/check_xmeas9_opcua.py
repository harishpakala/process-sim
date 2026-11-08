"""Created: 2026-11-01
Author: Harish"""


import asyncio
from datetime import datetime, timezone
from asyncua import Client

async def main():
    endpoint = "opc.tcp://127.0.0.1:4841"

    async with Client(url=endpoint) as client:
        namespace = await client.get_namespace_index(
            "urn:process-sim:opcua"
        )

        node = client.get_node(
            f"ns={namespace};s=TEP.Measurements.XMEAS9"
        )

        for i in range(5):
            data = await node.read_data_value()

            print({
                "read": i + 1,
                "value": data.Value.Value,
                "status": str(data.StatusCode),
                "source_timestamp": str(data.SourceTimestamp),
                "read_at_utc": datetime.now(
                    timezone.utc
                ).isoformat()
            })

            if i < 4:
                await asyncio.sleep(3)

asyncio.run(main())
