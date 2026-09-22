import asyncio, math, random
import numpy as np
from fastapi import FastAPI, WebSocket
from scipy.optimize import least_squares

app = FastAPI()

ANCHORS = {
    "A1": (3.5, 1.5),
    "A2": (11.0, 1.5),
    "A3": (11.0, 6.6),
    "A4": (3.5, 6.6),
}

ZONES = {
    "Reacteur":              (1.35, 2.45, 3.08, 5.65, True),
    "Quartiers des equipes": (3.45, 1.28, 5.20, 3.30, False),
    "Cafeteria":             (3.45, 4.85, 5.20, 6.85, False),
    "Laboratoire":           (6.83, 1.28, 8.57, 3.30, False),
    "Infirmerie":            (6.83, 4.85, 8.57, 6.85, False),
    "Salle Serveur":         (10.20, 1.28, 11.52, 3.30, True),
}
RESTRICTED = {name for name, z in ZONES.items() if z[4]}

BADGES = {
    "ASTRA-001": {"name": "Cdt Vega", "role": "Commandant", "clearance": ["*"]},
    "ASTRA-002": {"name": "Ing. Lior", "role": "Ingenieur", "clearance": ["Reacteur", "Salle Serveur"]},
    "ASTRA-003": {"name": "Pass. Noor", "role": "Passager", "clearance": []},
}

TX_POWER, N = -59, 2.2

state, clients = {}, set()


def ingest(badge, anchor, rssi):
    s = state.setdefault(badge, {})
    s[anchor] = rssi if anchor not in s else 0.7 * s[anchor] + 0.3 * rssi


def rssi_to_dist(rssi):
    return 10 ** ((TX_POWER - rssi) / (10 * N))


def trilaterate(dists):
    ids = list(dists)
    pts = np.array([ANCHORS[i] for i in ids])
    d = np.array([dists[i] for i in ids])
    res = lambda p: np.linalg.norm(pts - p, axis=1) - d
    result = least_squares(res, pts.mean(axis=0), bounds=([-1, -1], [16, 9]))
    return result.x


smoothed_positions = {}


def zone_of(x, y):
    for name, (x1, y1, x2, y2, _restricted) in ZONES.items():
        if x1 <= x <= x2 and y1 <= y <= y2:
            return name
    return "Coursive"


def snapshot():
    out = []
    for badge, s in state.items():
        if len(s) >= 3:
            raw_x, raw_y = trilaterate({a: rssi_to_dist(r) for a, r in s.items()})
        elif len(s) >= 1:
            nearest_anchor = max(s, key=s.get)
            anchor_pos = np.array(ANCHORS[nearest_anchor])
            dist = rssi_to_dist(s[nearest_anchor])
            center = np.array([7.45, 4.0])
            direction = center - anchor_pos
            direction = direction / (np.linalg.norm(direction) or 1)
            raw_x, raw_y = anchor_pos + direction * min(dist, 5.5)
        else:
            continue

        prev = smoothed_positions.get(badge, np.array([raw_x, raw_y]))
        smoothed = 0.65 * prev + 0.35 * np.array([raw_x, raw_y])
        smoothed_positions[badge] = smoothed
        x, y = smoothed
        info = BADGES.get(badge)
        zone = zone_of(x, y)
        allowed = info and ("*" in info["clearance"] or zone in info["clearance"])
        out.append({
            "id": badge,
            "name": info["name"] if info else "INCONNU",
            "role": info["role"] if info else "?",
            "x": round(float(x), 2),
            "y": round(float(y), 2),
            "zone": zone,
            "alert": zone in RESTRICTED and not allowed,
        })
    return out


def make_path(pos, dest):
    corridor_y = 4.0
    via1 = np.array([pos[0], corridor_y])
    via2 = np.array([dest[0], corridor_y])
    path = [via1, via2, dest]
    return [wp for wp in path if np.linalg.norm(wp - pos) > 0.15]


def random_waypoint():
    if random.random() < 0.75:
        x1, y1, x2, y2, _ = random.choice(list(ZONES.values()))
        margin = 0.25
        return np.array([
            random.uniform(x1 + margin, x2 - margin),
            random.uniform(y1 + margin, y2 - margin),
        ])
    return np.array([random.uniform(3.3, 11.3), random.uniform(3.7, 4.3)])


def intruder_waypoint():
    if random.random() < 0.6:
        name = random.choice(list(RESTRICTED))
        x1, y1, x2, y2, _ = ZONES[name]
        margin = 0.25
        return np.array([random.uniform(x1 + margin, x2 - margin), random.uniform(y1 + margin, y2 - margin)])
    return random_waypoint()


async def sim_loop():
    people = {
        b: {"pos": random_waypoint(), "path": []}
        for b in [*BADGES, "UNKNOWN-42"]
    }
    while True:
        for badge, p in people.items():
            if not p["path"]:
                if random.random() < 0.25:
                    continue
                dest = intruder_waypoint() if badge == "UNKNOWN-42" else random_waypoint()
                p["path"] = make_path(p["pos"], dest)
                if not p["path"]:
                    continue

            step = p["path"][0] - p["pos"]
            dist = np.linalg.norm(step)
            if dist < 0.1:
                p["path"].pop(0)
            else:
                p["pos"] += step / dist * 0.035
            for a, apos in ANCHORS.items():
                d = max(np.linalg.norm(p["pos"] - apos), 0.1)
                ingest(badge, a, TX_POWER - 10 * N * math.log10(d) + random.gauss(0, 1.2))
        await asyncio.sleep(0.2)


async def broadcast_loop():
    while True:
        data = snapshot()
        for c in list(clients):
            try:
                await c.send_json(data)
            except Exception:
                clients.discard(c)
        await asyncio.sleep(0.2)


@app.on_event("startup")
async def start():
    asyncio.create_task(broadcast_loop())
    # asyncio.create_task(sim_loop())


@app.websocket("/ws")
async def ws(websocket: WebSocket):
    await websocket.accept()
    clients.add(websocket)
    try:
        while True:
            await websocket.receive_text()
    except Exception:
        clients.discard(websocket)


@app.post("/rssi")
def rssi(d: dict):
    ingest(d["badge"], d["anchor"], d["rssi"])


@app.post("/revoke/{badge}")
def revoke(badge: str):
    BADGES.pop(badge, None)
    return {"revoked": badge}

