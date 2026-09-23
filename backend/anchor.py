"""
anchor.py  –  Scanner BLE pour le projet Aurora Star
Envoie les RSSI des badges ASTRA-* et UNKNOWN-* au serveur FastAPI.

Compatible bleak >= 3.0

Usage : python anchor.py
"""

import asyncio
import httpx
from bleak import BleakScanner
from bleak.backends.device import BLEDevice
from bleak.backends.scanner import AdvertisementData
from datetime import datetime

import os

# ── Configuration ──────────────────────────────────────────────────────────────
ANCHOR_ID   = os.getenv("ANCHOR_ID", "A3")               # Identifiant de cet anchor (A1-A4)
SERVER      = os.getenv("SERVER_URL", "http://127.0.0.1:8000") # Adresse du serveur FastAPI
RETRY_DELAY = 3                                          # Secondes avant de relancer le scanner si crash
# ───────────────────────────────────────────────────────────────────────────────


def log(msg: str):
    """Affiche un message avec horodatage."""
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}", flush=True)


async def main():
    log(f"Anchor {ANCHOR_ID} démarré  →  serveur : {SERVER}")

    async with httpx.AsyncClient(timeout=5.0) as http:

        # Vérification initiale que le serveur est joignable
        for attempt in range(1, 11):
            try:
                r = await http.get(f"{SERVER}/docs")
                if r.status_code < 500:
                    log("✅  Serveur joignable.")
                    break
            except Exception:
                pass
            log(f"⏳  Serveur injoignable (essai {attempt}/10) – nouvelle tentative dans {RETRY_DELAY}s…")
            await asyncio.sleep(RETRY_DELAY)
        else:
            log("⚠️   Serveur non joignable après 10 essais. Lancement quand même.")

        # Boucle principale de scan BLE (se relance automatiquement si crash)
        while True:
            try:
                log("📡  Démarrage du scan BLE…")

                async def cb(device: BLEDevice, adv: AdvertisementData):
                    name = adv.local_name or device.name or ""
                    if name.startswith("ASTRA-") or name.startswith("UNKNOWN"):
                        try:
                            r = await http.post(
                                f"{SERVER}/rssi",
                                json={"anchor": ANCHOR_ID, "badge": name, "rssi": adv.rssi},
                            )
                            log(f"📤 {name:20s}  rssi={adv.rssi:4d} dBm  →  HTTP {r.status_code}")
                        except httpx.ConnectError:
                            log(f"⚠️   Serveur injoignable – paquet {name} perdu.")
                        except Exception as e:
                            log(f"⚠️   Erreur envoi {name}: {e}")

                async with BleakScanner(detection_callback=cb):
                    log("🔍  Scanner actif – en attente de badges…  (Ctrl+C pour arrêter)")
                    await asyncio.Event().wait()   # bloque indéfiniment jusqu'à Ctrl+C

            except asyncio.CancelledError:
                log("🛑  Arrêt demandé.")
                break
            except Exception as e:
                log(f"💥  Erreur scanner BLE : {e}")
                log(f"🔄  Relance du scanner dans {RETRY_DELAY}s…")
                await asyncio.sleep(RETRY_DELAY)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n[Arrêt propre par l'utilisateur]")
