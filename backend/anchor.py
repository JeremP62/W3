import asyncio, math, random, sqlite3, time
from collections import deque
import numpy as np
from fastapi import FastAPI, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from scipy.optimize import least_squares

app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Base de données locale (SQLite)
# ---------------------------------------------------------------------------
DB_PATH = "astra.db"

SCHEMA_SQL = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS Zones_Vaisseau (
    id_zone INTEGER PRIMARY KEY AUTOINCREMENT,
    nom_zone TEXT NOT NULL,
    niveau_securite INTEGER NOT NULL,
    bpm_max_autorise INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS Roles_Equipage (
    id_role INTEGER PRIMARY KEY AUTOINCREMENT,
    titre_role TEXT NOT NULL,
    pilier_rattachement TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS Equipage (
    id_astronaute INTEGER PRIMARY KEY AUTOINCREMENT,
    nom_complet TEXT NOT NULL,
    id_role INTEGER NOT NULL,
    profil_psy_base TEXT NOT NULL,
    astra_badge_id TEXT,
    FOREIGN KEY (id_role) REFERENCES Roles_Equipage(id_role)
);

CREATE TABLE IF NOT EXISTS Telemetrie_Vitale (
    id_mesure INTEGER PRIMARY KEY AUTOINCREMENT,
    id_astronaute INTEGER NOT NULL,
    horodatage DATETIME DEFAULT CURRENT_TIMESTAMP,
    bpm_actuel INTEGER NOT NULL,
    niveau_stress_ia REAL NOT NULL,
    FOREIGN KEY (id_astronaute) REFERENCES Equipage(id_astronaute)
);

CREATE TABLE IF NOT EXISTS Logs_Acces_Securise (
    id_log INTEGER PRIMARY KEY AUTOINCREMENT,
    id_astronaute INTEGER NOT NULL,
    id_zone INTEGER NOT NULL,
    horodatage DATETIME DEFAULT CURRENT_TIMESTAMP,
    bpm_lors_demande INTEGER NOT NULL,
    acces_accorde BOOLEAN NOT NULL,
    motif_refus TEXT,
    FOREIGN KEY (id_astronaute) REFERENCES Equipage(id_astronaute),
    FOREIGN KEY (id_zone) REFERENCES Zones_Vaisseau(id_zone)
);

CREATE TABLE IF NOT EXISTS Autorisations_Zone (
    id_role INTEGER NOT NULL,
    id_zone INTEGER NOT NULL,
    PRIMARY KEY (id_role, id_zone),
    FOREIGN KEY (id_role) REFERENCES Roles_Equipage(id_role),
    FOREIGN KEY (id_zone) REFERENCES Zones_Vaisseau(id_zone)
);
"""

SEED_SQL = """
INSERT INTO Zones_Vaisseau (nom_zone, niveau_securite, bpm_max_autorise) VALUES
('Cafétéria', 1, 180),
('Quartiers des équipes', 2, 150),
('Infirmerie', 3, 200),
('Laboratoire', 4, 110),
('Poste de Pilotage', 5, 120),
('Poste de Sécurité & Serveur', 5, 110),
('Réacteur', 5, 115);

INSERT INTO Roles_Equipage (titre_role, pilier_rattachement) VALUES
('Commandant de bord', 'Essentiel'),
('Pilote / Navigateur', 'Essentiel'),
('Médecin-Psychiatre', 'Pilier 1 : HumanTech'),
('Ingénieur Agronome', 'Pilier 2 : FoodTech'),
('Ingénieur Énergie', 'Pilier 3 : EnergyTech'),
('Spécialiste Cyber & IA', 'Pilier 4 : DeepTech');

INSERT INTO Equipage (nom_complet, id_role, profil_psy_base) VALUES
('Elena Rostova', 1, 'Résiliente, leadership naturel, faible réactivité au stress.'),
('Marcus Vance', 2, 'Flegmatique, très concentré, tendance à l''isolement.'),
('Dr. Sarah Jenkins', 3, 'Empathique, haut quotient émotionnel, analyse rapide.'),
('Kenji Sato', 4, 'Méthodique, calme, attaché à la routine du cycle végétal.'),
('Amir Fayed', 5, 'Pragmatique, sang-froid technique, stressé par les imprévus.'),
('Chloe Dubois', 6, 'Hyper-vigilante, analytique, susceptible de surmenage mental.');

INSERT INTO Telemetrie_Vitale (id_astronaute, horodatage, bpm_actuel, niveau_stress_ia) VALUES
(1, '2026-09-22 08:00:00', 65, 1.2),
(6, '2026-09-22 08:30:00', 88, 4.5),
(5, '2026-09-22 09:15:00', 135, 8.7),
(3, '2026-09-22 09:16:00', 85, 3.0);

INSERT INTO Logs_Acces_Securise (id_astronaute, id_zone, horodatage, bpm_lors_demande, acces_accorde, motif_refus) VALUES
(1, 5, '2026-09-22 08:05:00', 68, 1, NULL);
INSERT INTO Logs_Acces_Securise (id_astronaute, id_zone, horodatage, bpm_lors_demande, acces_accorde, motif_refus) VALUES
(6, 6, '2026-09-22 08:35:00', 92, 1, NULL);
INSERT INTO Logs_Acces_Securise (id_astronaute, id_zone, horodatage, bpm_lors_demande, acces_accorde, motif_refus) VALUES
(5, 7, '2026-09-22 09:15:30', 135, 0, 'Accès refusé - BPM (135) supérieur à la limite autorisée (115) pour la zone Réacteur. Risque d''erreur humaine critique.');
INSERT INTO Logs_Acces_Securise (id_astronaute, id_zone, horodatage, bpm_lors_demande, acces_accorde, motif_refus) VALUES
(3, 1, '2026-09-22 09:18:00', 85, 1, NULL);
"""

AUTH_SEED_SQL = """
INSERT INTO Autorisations_Zone (id_role, id_zone) VALUES
(1,1),(1,2),(1,3),(1,4),(1,5),(1,6),(1,7),
(2,1),(2,2),(2,3),(2,5),
(3,1),(3,2),(3,3),
(4,1),(4,2),(4,3),(4,4),
(5,1),(5,2),(5,3),(5,7),
(6,1),(6,2),(6,3),(6,4),(6,6);
"""


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_db()
    conn.executescript(SCHEMA_SQL)
    if conn.execute("SELECT COUNT(*) AS c FROM Zones_Vaisseau").fetchone()["c"] == 0:
        conn.executescript(SEED_SQL)
    if conn.execute("SELECT COUNT(*) AS c FROM Autorisations_Zone").fetchone()["c"] == 0:
        conn.executescript(AUTH_SEED_SQL)
    conn.execute("UPDATE Equipage SET astra_badge_id='ASTRA-001' WHERE nom_complet='Elena Rostova'")
    conn.execute("UPDATE Equipage SET astra_badge_id='ASTRA-002' WHERE nom_complet='Chloe Dubois'")
    conn.execute("UPDATE Equipage SET astra_badge_id='ASTRA-003' WHERE nom_complet='Marcus Vance'")
    conn.execute("UPDATE Zones_Vaisseau SET nom_zone='Poste de Sécurité & Serveur' WHERE nom_zone='Salle Serveur'")
    conn.commit()
    conn.close()


def load_crew():
    conn = get_db()
    rows = conn.execute("""
        SELECT e.id_astronaute, e.nom_complet, e.astra_badge_id, e.profil_psy_base,
               r.id_role, r.titre_role, r.pilier_rattachement
        FROM Equipage e JOIN Roles_Equipage r ON e.id_role = r.id_role
        WHERE e.astra_badge_id IS NOT NULL
    """).fetchall()

    zone_by_role = {}
    for row in conn.execute("""
        SELECT a.id_role, z.nom_zone
        FROM Autorisations_Zone a JOIN Zones_Vaisseau z ON a.id_zone = z.id_zone
    """).fetchall():
        zone_by_role.setdefault(row["id_role"], set()).add(row["nom_zone"])

    conn.close()
    return {
        r["astra_badge_id"]: {
            "id_astronaute": r["id_astronaute"],
            "name": r["nom_complet"],
            "role": r["titre_role"],
            "pilier": r["pilier_rattachement"],
            "profil": r["profil_psy_base"],
            "clearance": zone_by_role.get(r["id_role"], set()),
        }
        for r in rows
    }


def load_zone_security():
    conn = get_db()
    rows = conn.execute("SELECT * FROM Zones_Vaisseau").fetchall()
    conn.close()
    return {
        r["nom_zone"]: {
            "id_zone": r["id_zone"],
            "niveau_securite": r["niveau_securite"],
            "bpm_max_autorise": r["bpm_max_autorise"],
        }
        for r in rows
    }


def log_access(id_astronaute, id_zone, bpm, accorde, motif):
    conn = get_db()
    conn.execute(
        "INSERT INTO Logs_Acces_Securise (id_astronaute, id_zone, bpm_lors_demande, acces_accorde, motif_refus) "
        "VALUES (?, ?, ?, ?, ?)",
        (id_astronaute, id_zone, bpm, 1 if accorde else 0, motif),
    )
    conn.commit()
    conn.close()


def log_telemetry(id_astronaute, bpm, stress):
    conn = get_db()
    conn.execute(
        "INSERT INTO Telemetrie_Vitale (id_astronaute, bpm_actuel, niveau_stress_ia) VALUES (?, ?, ?)",
        (id_astronaute, bpm, stress),
    )
    conn.commit()
    conn.close()


# ---------------------------------------------------------------------------
# Géométrie du vaisseau
# ---------------------------------------------------------------------------
ROOM_WIDTH_M_SERVER = 15
ROOM_HEIGHT_M_SERVER = 8.3

ANCHORS = {
    "A1": (3.5, 1.5),
    "A2": (11.0, 1.5),
    "A3": (11.0, 6.6),
    "A4": (3.5, 6.6),
}

ANCHOR_DIRECTIONS = {
    "A1": (-1, -1),
    "A2": (-1, 0.3),
    "A3": (-1, -0.3),
    "A4": (1, -0.3),
}

ZONES = {
    "Réacteur":                   (1.35, 2.45, 3.08, 5.65),
    "Quartiers des équipes":     (3.45, 1.28, 5.20, 3.30),
    "Cafétéria":                 (3.45, 4.85, 5.20, 6.85),
    "Laboratoire":               (6.83, 1.28, 8.57, 3.30),
    "Infirmerie":                (6.83, 4.85, 8.57, 6.85),
    "Poste de Sécurité & Serveur": (10.20, 1.28, 11.52, 3.30),
    "Poste de Pilotage":         (11.52, 3.55, 13.9, 4.45),
}

init_db()
CREW = load_crew()
SECURITY = load_zone_security()

TX_POWER, N = -59, 2.2

state, clients = {}, set()
manual_overrides = {}
current_bpm = {}
bpm_history = {}
prev_alert = {}
rssi_history = {}

smoothed_positions = {}
last_seen = {}
forced_anomaly = {}


def ingest(badge, anchor, rssi):
    key = (badge, anchor)
    if key not in rssi_history:
        # Tampon réduit à 3 valeurs pour supprimer la latence
        rssi_history[key] = deque(maxlen=3)
    
    rssi_history[key].append(rssi)
    median_rssi = float(np.median(rssi_history[key]))
    state.setdefault(badge, {})[anchor] = median_rssi


def rssi_to_dist(rssi):
    rssi_clamped = min(max(rssi, -90), -35)
    dist = 10 ** ((TX_POWER - rssi_clamped) / (10 * N))
    return min(dist, 10.0)


def trilaterate(dists):
    ids = list(dists)
    pts = np.array([ANCHORS[i] for i in ids])
    d = np.array([dists[i] for i in ids])
    res = lambda p: np.linalg.norm(pts - p, axis=1) - d
    result = least_squares(
        res, 
        pts.mean(axis=0), 
        bounds=([1.0, 1.0], [ROOM_WIDTH_M_SERVER - 1.0, ROOM_HEIGHT_M_SERVER - 1.0])
    )
    return result.x


def zone_of(x, y):
    for name, (x1, y1, x2, y2) in ZONES.items():
        if x1 <= x <= x2 and y1 <= y <= y2:
            return name
    return "Coursive"


baseline_bpm = {}


def update_bpm(badge):
    baseline = baseline_bpm.setdefault(badge, random.uniform(68, 82))
    prev = current_bpm.get(badge, baseline)
    pull_to_baseline = (baseline - prev) * 0.08
    bpm = prev + pull_to_baseline + random.gauss(0, 1.8)
    bpm = max(55, min(bpm, 145))
    current_bpm[badge] = bpm
    bpm_history.setdefault(badge, deque(maxlen=150)).append(round(bpm))
    return bpm


def snapshot():
    out = []
    all_badges = set(state.keys()) | set(manual_overrides.keys())
    for badge in all_badges:
        if badge in manual_overrides:
            x, y = manual_overrides[badge]
            smoothed_positions[badge] = np.array([x, y])
            signal = None
            mode = "test"
            anomaly = False
        else:
            s = state[badge]
            if len(s) >= 3:
                raw_x, raw_y = trilaterate({a: rssi_to_dist(r) for a, r in s.items()})
                mode = "trilateration"
            elif len(s) >= 1:
                nearest_anchor = max(s, key=s.get)
                anchor_pos = np.array(ANCHORS[nearest_anchor])
                dist = rssi_to_dist(s[nearest_anchor])
                direction = np.array(ANCHOR_DIRECTIONS[nearest_anchor], dtype=float)
                direction = direction / (np.linalg.norm(direction) or 1)
                raw_x, raw_y = anchor_pos + direction * min(dist, 2.0)
                mode = "1-ancre"
            else:
                continue

            # --- Confinement géométrique (Clamping) dans la coque ---
            MARGIN_X = 1.2
            MARGIN_Y = 1.2
            raw_x = float(np.clip(raw_x, MARGIN_X, ROOM_WIDTH_M_SERVER - MARGIN_X))
            raw_y = float(np.clip(raw_y, MARGIN_Y, ROOM_HEIGHT_M_SERVER - MARGIN_Y))

            now_t = time.time()
            prev_seen = last_seen.get(badge)

            if prev_seen is not None:
                px, py, pt = prev_seen
                dt = max(now_t - pt, 0.05)
                
                MAX_SPEED_M_S = 3.0 # Tolérance augmentée à 3.0 m/s pour réactivité
                max_dist = MAX_SPEED_M_S * dt

                dist_raw = math.hypot(raw_x - px, raw_y - py)
                if dist_raw > max_dist and dist_raw > 0:
                    ratio = max_dist / dist_raw
                    raw_x = px + (raw_x - px) * ratio
                    raw_y = py + (raw_y - py) * ratio

            # --- Lissage hyper-réactif (85% nouvelle mesure, 15% ancienne) ---
            prev_pos = smoothed_positions.get(badge, np.array([raw_x, raw_y]))
            smoothed = 0.15 * prev_pos + 0.85 * np.array([raw_x, raw_y])
            smoothed_positions[badge] = smoothed
            x, y = smoothed
            signal = {a: round(r) for a, r in s.items()}

            anomaly = False
            if prev_seen is not None:
                px, py, pt = prev_seen
                dt = now_t - pt
                if dt > 0.05:
                    speed = math.hypot(x - px, y - py) / dt
                    if speed > 4.0:
                        anomaly = True

            last_seen[badge] = (x, y, now_t)

        now_t = time.time()
        if forced_anomaly.get(badge, 0) > now_t:
            anomaly = True

        zone = zone_of(x, y)
        crew = CREW.get(badge)
        bpm = update_bpm(badge)
        zone_sec = SECURITY.get(zone)

        if zone_sec is None:
            allowed, motif = True, None
        elif crew is None:
            allowed = zone_sec["niveau_securite"] < 4
            motif = None if allowed else "Badge non enregistré dans l'équipage — accès zone critique refusé."
        elif zone not in crew["clearance"]:
            allowed = False
            motif = f"Rôle « {crew['role']} » non habilité pour la zone {zone}."
        else:
            allowed = bpm <= zone_sec["bpm_max_autorise"]
            motif = None if allowed else (
                f"BPM ({bpm:.0f}) supérieur au seuil autorisé ({zone_sec['bpm_max_autorise']}) "
                f"pour la zone {zone}."
            )

        alert = not allowed
        if alert and not prev_alert.get(badge, False) and crew is not None and zone_sec is not None:
            stress_est = round(min(10.0, max(0.0, (bpm - 70) / 8)), 1)
            log_access(crew["id_astronaute"], zone_sec["id_zone"], round(bpm), False, motif)
            log_telemetry(crew["id_astronaute"], round(bpm), stress_est)
        prev_alert[badge] = alert

        out.append({
            "id": badge,
            "name": crew["name"] if crew else "INCONNU",
            "role": crew["role"] if crew else "Non enregistré",
            "pilier": crew["pilier"] if crew else None,
            "x": round(float(x), 2),
            "y": round(float(y), 2),
            "zone": zone,
            "bpm": round(bpm),
            "alert": alert,
            "motif": motif,
            "signal": signal,
            "mode": mode,
            "anomaly": anomaly,
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
        x1, y1, x2, y2 = random.choice(list(ZONES.values()))
        margin = 0.25
        return np.array([
            random.uniform(x1 + margin, x2 - margin),
            random.uniform(y1 + margin, y2 - margin),
        ])
    return np.array([random.uniform(3.3, 11.3), random.uniform(3.7, 4.3)])


def intruder_waypoint():
    restricted_names = [n for n, s in SECURITY.items() if s["niveau_securite"] >= 4 and n in ZONES]
    if restricted_names and random.random() < 0.6:
        name = random.choice(restricted_names)
        x1, y1, x2, y2 = ZONES[name]
        margin = 0.25
        return np.array([random.uniform(x1 + margin, x2 - margin), random.uniform(y1 + margin, y2 - margin)])
    return random_waypoint()


async def sim_loop():
    people = {
        b: {"pos": random_waypoint(), "path": []}
        for b in [*CREW.keys(), "UNKNOWN-42"]
    }
    while True:
        now_t = time.time()
        for badge, p in people.items():
            # DESACTIVATION DE LA SIMULATION LORSQU'UN BADGE REEL EST CAPTÉ (dans les 4 dernières secondes)
            if badge in last_seen and (now_t - last_seen[badge][2]) < 4.0:
                continue

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
    asyncio.create_task(sim_loop())
    asyncio.create_task(broadcast_loop())


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


@app.get("/debug")
def debug():
    return {"state": state, "anchors_seen": {b: list(s.keys()) for b, s in state.items()}}


@app.get("/crew")
def get_crew():
    crew_json = {
        badge: {**info, "clearance": sorted(info["clearance"])}
        for badge, info in CREW.items()
    }
    return {"crew": crew_json, "zones_security": SECURITY}


@app.post("/roles/authorize")
def authorize_role(d: dict):
    role_name, room = d["role"], d["room"]
    if room not in ZONES:
        return {"error": f"Salle inconnue. Salles valides : {list(ZONES.keys())}"}
    conn = get_db()
    role_row = conn.execute("SELECT id_role FROM Roles_Equipage WHERE titre_role = ?", (role_name,)).fetchone()
    if not role_row:
        conn.close()
        return {"error": f"Rôle inconnu : {role_name}"}
    zone_row = conn.execute("SELECT id_zone FROM Zones_Vaisseau WHERE nom_zone = ?", (room,)).fetchone()
    conn.execute(
        "INSERT OR IGNORE INTO Autorisations_Zone (id_role, id_zone) VALUES (?, ?)",
        (role_row["id_role"], zone_row["id_zone"]),
    )
    conn.commit()
    conn.close()
    global CREW
    CREW = load_crew()
    return {"authorized": {"role": role_name, "room": room}}


@app.post("/roles/revoke")
def revoke_role_access(d: dict):
    role_name, room = d["role"], d["room"]
    conn = get_db()
    conn.execute("""
        DELETE FROM Autorisations_Zone
        WHERE id_role = (SELECT id_role FROM Roles_Equipage WHERE titre_role = ?)
          AND id_zone = (SELECT id_zone FROM Zones_Vaisseau WHERE nom_zone = ?)
    """, (role_name, room))
    conn.commit()
    conn.close()
    global CREW
    CREW = load_crew()
    return {"revoked": {"role": role_name, "room": room}}


@app.get("/roles")
def list_roles():
    conn = get_db()
    roles = conn.execute("SELECT id_role, titre_role, pilier_rattachement FROM Roles_Equipage").fetchall()
    result = []
    for r in roles:
        zones = conn.execute("""
            SELECT z.nom_zone FROM Autorisations_Zone a
            JOIN Zones_Vaisseau z ON a.id_zone = z.id_zone
            WHERE a.id_role = ?
        """, (r["id_role"],)).fetchall()
        result.append({
            "role": r["titre_role"],
            "pilier": r["pilier_rattachement"],
            "zones_autorisees": [z["nom_zone"] for z in zones],
        })
    conn.close()
    return {"roles": result}


@app.get("/profile/{badge}/history")
def get_bpm_history(badge: str):
    return {"badge": badge, "history": list(bpm_history.get(badge, []))}


@app.get("/logs")
def get_logs(limit: int = 20):
    conn = get_db()
    rows = conn.execute("""
        SELECT l.horodatage, e.nom_complet, z.nom_zone, l.bpm_lors_demande, l.acces_accorde, l.motif_refus
        FROM Logs_Acces_Securise l
        JOIN Equipage e ON l.id_astronaute = e.id_astronaute
        JOIN Zones_Vaisseau z ON l.id_zone = z.id_zone
        ORDER BY l.id_log DESC LIMIT ?
    """, (limit,)).fetchall()
    conn.close()
    return {"logs": [dict(r) for r in rows]}


@app.post("/rescue/{zone}")
def rescue(zone: str):
    if zone not in ZONES:
        return {"error": f"Salle inconnue. Salles valides : {list(ZONES.keys())}"}
    people = snapshot()
    trapped = [p["name"] for p in people if p["zone"] == zone]
    return {"zone": zone, "trapped": trapped, "can_seal": len(trapped) == 0}


@app.get("/test/rooms")
def test_rooms():
    return {"rooms": list(ZONES.keys())}


@app.post("/test/move")
def test_move(d: dict):
    badge = d["badge"]
    room = d["room"]
    if room not in ZONES:
        return {"error": f"Salle inconnue. Salles valides : {list(ZONES.keys())}"}
    x1, y1, x2, y2 = ZONES[room]
    center = (round((x1 + x2) / 2, 2), round((y1 + y2) / 2, 2))
    manual_overrides[badge] = center
    return {"badge": badge, "room": room, "position": center}


@app.post("/test/set-position")
def test_set_position(d: dict):
    badge = d["badge"]
    x = round(max(0.3, min(float(d["x"]), ROOM_WIDTH_M_SERVER - 0.3)), 2)
    y = round(max(0.3, min(float(d["y"]), ROOM_HEIGHT_M_SERVER - 0.3)), 2)
    manual_overrides[badge] = (x, y)
    return {"badge": badge, "position": (x, y)}


@app.post("/test/clear/{badge}")
def test_clear(badge: str):
    manual_overrides.pop(badge, None)
    return {"cleared": badge}


@app.post("/test/clear-all")
def test_clear_all():
    manual_overrides.clear()
    return {"cleared": "all"}


@app.post("/test/reset-bpm/{badge}")
def reset_bpm(badge: str):
    baseline_bpm.pop(badge, None)
    current_bpm.pop(badge, None)
    prev_alert.pop(badge, None)
    return {"reset": badge}


@app.post("/test/stress/{badge}")
def induce_stress(badge: str):
    bpm = random.uniform(125, 142)
    current_bpm[badge] = bpm
    return {"badge": badge, "bpm": round(bpm)}


@app.post("/test/simulate-jump/{badge}")
def simulate_jump(badge: str):
    forced_anomaly[badge] = time.time() + 2.5
    return {"badge": badge, "forced_anomaly_until": "2.5s"}