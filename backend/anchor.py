# pc_scanner.py optimisé
import asyncio, httpx
from bleak import BleakScanner

ANCHOR_ID = "A1"
SERVER = "http://172.20.10.13:8000"

async def main():
    async with httpx.AsyncClient(timeout=1.0) as http:
        async def cb(device, adv):
            name = adv.local_name or ""
            if name.startswith("ASTRA-") or name.startswith("UNKNOWN"):
                # Fire and forget pour éviter de bloquer la boucle BLE
                asyncio.create_task(send_rssi(http, name, adv.rssi))

        async def send_rssi(client, name, rssi):
            try:
                await client.post(f"{SERVER}/rssi", json={"anchor": ANCHOR_ID, "badge": name, "rssi": rssi})
            except Exception:
                pass

        scanner = BleakScanner(cb)
        await scanner.start()
        await asyncio.Event().wait()

asyncio.run(main())