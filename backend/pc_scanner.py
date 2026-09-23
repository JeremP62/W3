import asyncio
import requests
from bleak import BleakScanner

# ---------------------------------------------------------
# CONFIGURATION
# ---------------------------------------------------------
# Nom de l'ancre sur ce PC (Changer en "A2" ou "A3" sur les autres PC)
ANCHOR_ID = "A1"  

# Nom exact du badge Bluetooth émis par votre téléphone
TARGET_BADGE = "ASTRA-001"  

# Adresse du serveur backend (localhost si sur la même machine)
SERVER_URL = "http://127.0.0.1:8000/rssi"  
# ---------------------------------------------------------


def detection_callback(device, advertisement_data):
    # Détection par nom d'appareil ou nom local dans l'annonce
    device_name = device.name or advertisement_data.local_name
    if device_name == TARGET_BADGE:
        rssi = advertisement_data.rssi
        payload = {"badge": TARGET_BADGE, "anchor": ANCHOR_ID, "rssi": rssi}
        try:
            res = requests.post(SERVER_URL, json=payload, timeout=0.5)
            print(f"[{ANCHOR_ID}] Envoyé: {TARGET_BADGE} rssi={rssi} -> {res.status_code}")
        except Exception as e:
            print(f"[{ANCHOR_ID}] Erreur envoi serveur: {e}")


async def main():
    print(f"Démarrage de l'ancre {ANCHOR_ID} pour le badge {TARGET_BADGE}...")
    scanner = BleakScanner(detection_callback, scanning_mode="active")
    await scanner.start()
    while True:
        await asyncio.sleep(1)


if __name__ == "__main__":
    asyncio.run(main())