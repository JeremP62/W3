import asyncio, httpx
from bleak import BleakScanner

ANCHOR_ID = "A1"   # ou A2, A3 selon le PC
SERVER = "http://172.20.10.13:8000"

async def main():
    async with httpx.AsyncClient() as http:
        async def cb(device, adv):
            name = adv.local_name or ""
            if name.startswith("ASTRA-") or name.startswith("UNKNOWN"):
                r = await http.post(f"{SERVER}/rssi", json={"anchor": ANCHOR_ID, "badge": name, "rssi": adv.rssi})
        async with BleakScanner(cb):
            await asyncio.Event().wait()

asyncio.run(main())