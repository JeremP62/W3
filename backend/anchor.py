import asyncio, httpx
from bleak import BleakScanner

ANCHOR_ID = "A1"                       # A1 pour ce premier test
SERVER = "http://172.20.10.13:8000"      # meme PC pour l instant

async def main():
    async with httpx.AsyncClient() as http:
        async def cb(device, adv):
            name = adv.local_name or ""
            if name.startswith("ASTRA-") or name.startswith("UNKNOWN"):
                try:
                    r = await http.post(f"{SERVER}/rssi", json={"anchor": ANCHOR_ID, "badge": name, "rssi": adv.rssi})
                    print(f"envoye: {name} rssi={adv.rssi} -> {r.status_code}")
                except Exception as e:
                    print("erreur envoi:", e)
        async with BleakScanner(cb):
            await asyncio.Event().wait()

asyncio.run(main())

