# pc_scanner.py
import asyncio
import httpx
from bleak import BleakScanner

ANCHOR_ID = "A1"
SERVER = "http://172.20.10.13:8000"


async def send_rssi(client: httpx.AsyncClient, name: str, rssi: int):
    """Envoie la mesure RSSI au serveur FastAPI de manière asynchrone."""
    try:
        await client.post(
            f"{SERVER}/rssi",
            json={"anchor": ANCHOR_ID, "badge": name, "rssi": rssi},
        )
    except Exception:
        # Évite d'interrompre la boucle de scan en cas de timeout/perte réseau
        pass


async def main():
    async with httpx.AsyncClient(timeout=1.0) as http:

        def detection_callback(device, adv):
            name = adv.local_name or ""
            if name.startswith("ASTRA-") or name.startswith("UNKNOWN"):
                # Envoi non-bloquant pour préserver la réactivité du scanner BLE
                asyncio.create_task(send_rssi(http, name, adv.rssi))

        scanner = BleakScanner(detection_callback)
        print(f"[{ANCHOR_ID}] Démarrage du scan BLE... (Ctrl+C pour arrêter)")

        await scanner.start()
        try:
            # Maintient le scanner actif jusqu'à une interruption utilisateur
            await asyncio.Future()
        except asyncio.CancelledError:
            pass
        finally:
            print(f"\n[{ANCHOR_ID}] Arrêt du scanner BLE...")
            await scanner.stop()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Programme arrêté proprement.")