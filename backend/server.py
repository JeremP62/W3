import asyncio, math, random, sqlite3, time
from collections import deque
import numpy as np
from fastapi import FastAPI, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from scipy.optimize import least_squares
from collections import deque

app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],   # dashboard local uniquement, ouverture large sans risque ici
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Base de données locale (SQLite) — équipage, zones, télémétrie vitale et
# journal d'accès. 100% local, aucun accès réseau/cloud (mode Edge). Le
# fichier astra.db est créé et peuplé automatiquement au premier lancement.
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

-- Habilitations : quelles salles chaque role a le droit d'utiliser, avant
-- meme de regarder le BPM. Un role non habilite est TOUJOURS refuse dans
-- cette zone, meme au repos. Un role habilite reste ensuite soumis au
-- seuil BPM de la zone (double controle : identite + etat physiologique).
CREATE TABLE IF NOT EXISTS Autorisations_Zone (
    id_role INTEGER NOT NULL,
    id_zone INTEGER NOT NULL,
    PRIMARY KEY (id_role, id_zone),
    FOREIGN KEY (id_role) REFERENCES Roles_Equipage(id_role),
    FOREIGN KEY (id_zone) REFERENCES Zones_Vaisseau(id_zone)
);
"""

# Données fictives de départ (Mission Aurora Star). Ces INSERT ne sont exécutés
# qu'au tout premier lancement, si les tables sont vides — pas de doublons
# aux redémarrages suivants.
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

# Seed separe pour les habilitations : verifie independamment si vide, pour
# rattraper automatiquement une base existante creee AVANT l'ajout de cette
# table (pas besoin de supprimer astra.db a la main a chaque evolution).
AUTH_SEED_SQL = """
-- Habilitations par role (id_zone : 1 Cafeteria, 2 Quartiers, 3 Infirmerie,
-- 4 Laboratoire, 5 Poste de Pilotage, 6 Salle Serveur, 7 Reacteur)
INSERT INTO Autorisations_Zone (id_role, id_zone) VALUES
-- Commandant de bord (1) : acces total au vaisseau
(1,1),(1,2),(1,3),(1,4),(1,5),(1,6),(1,7),
-- Pilote / Navigateur (2) : zones communes + poste de pilotage
(2,1),(2,2),(2,3),(2,5),
-- Medecin-Psychiatre (3) : zones communes + infirmerie (deja incluse)
(3,1),(3,2),(3,3),
-- Ingenieur Agronome (4) : zones communes + laboratoire
(4,1),(4,2),(4,3),(4,4),
-- Ingenieur Energie (5) : zones communes + reacteur
(5,1),(5,2),(5,3),(5,7),
-- Specialiste Cyber & IA (6) : zones communes + labo + salle serveur
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
    # Verification independante : rattrape une base existante ou la table
    # Autorisations_Zone a ete creee vide (schema ajoute apres coup).
    if conn.execute("SELECT COUNT(*) AS c FROM Autorisations_Zone").fetchone()["c"] == 0:
        conn.executescript(AUTH_SEED_SQL)
    # Relie 3 membres de l'équipage aux badges BLE physiques testables
    # (ASTRA-001/002/003). Idempotent : peut être relancé sans risque.
    conn.execute("UPDATE Equipage SET astra_badge_id='ASTRA-001' WHERE nom_complet='Elena Rostova'")
    conn.execute("UPDATE Equipage SET astra_badge_id='ASTRA-002' WHERE nom_complet='Chloe Dubois'")
    conn.execute("UPDATE Equipage SET astra_badge_id='ASTRA-003' WHERE nom_complet='Marcus Vance'")
    # Migration : renomme l'ancienne "Salle Serveur" si une base existante
    # a deja ete creee avant ce changement (idempotent, sans effet sinon).
    conn.execute("UPDATE Zones_Vaisseau SET nom_zone='Poste de Sécurité & Serveur' WHERE nom_zone='Salle Serveur'")
    conn.commit()
    conn.close()


def load_crew():
    """{badge_id: {id_astronaute, name, role, pilier, profil, clearance}} —
    uniquement les membres d'équipage reliés à un badge BLE physique.
    "clearance" est l'ensemble des noms de salles autorisées pour le role."""
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
    """{nom_zone: {id_zone, niveau_securite, bpm_max_autorise}}"""
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
# Géométrie du vaisseau — DOIT correspondre exactement aux constantes ROOMS /
# ANCHORS / HULL / PILOTAGE du composant frontend BLEPassengerTracker.tsx
# (même unité : mètres, même repère, origine en haut à gauche).
# ---------------------------------------------------------------------------
# Dimensions du vaisseau (memes valeurs que ROOM_WIDTH_M/ROOM_HEIGHT_M cote
# frontend) - utilisees pour borner le deplacement libre au clavier.
ROOM_WIDTH_M_SERVER = 15
ROOM_HEIGHT_M_SERVER = 8.3

ANCHORS = {
    "A1": (3.5, 1.5),
    "A2": (11.0, 1.5),
    "A3": (11.0, 6.6),
    "A4": (3.5, 6.6),
}

# Direction vers laquelle le point s'éloigne de chaque ancre, quand une seule
# ancre est active (pas de direction réelle calculable, seulement une
# distance). À CALIBRER le jour J selon la disposition réelle de la salle.
ANCHOR_DIRECTIONS = {
    "A1": (-1, -1),
    "A2": (-1, 0.3),
    "A3": (-1, -0.3),
    "A4": (1, -0.3),
}

# Géométrie pure (x1, y1, x2, y2) — la politique de sécurité (niveau, seuil
# BPM) vit dans la base et est chargée séparément via load_zone_security().
ZONES = {
    "Réacteur":              (1.35, 2.45, 3.08, 5.65),
    "Quartiers des équipes": (3.45, 1.28, 5.20, 3.30),
    "Cafétéria":             (3.45, 4.85, 5.20, 6.85),
    "Laboratoire":           (6.83, 1.28, 8.57, 3.30),
    "Infirmerie":            (6.83, 4.85, 8.57, 6.85),
    "Poste de Sécurité & Serveur": (10.20, 1.28, 11.52, 3.30),
    "Poste de Pilotage":     (11.52, 3.55, 13.9, 4.45),  # englobant du triangle
}

init_db()
CREW = load_crew()               # {badge_id: infos equipage} depuis la DB
SECURITY = load_zone_security()  # {nom_zone: seuils} depuis la DB

TX_POWER, N = -59, 2.2   # RSSI à 1 m et exposant de perte : À CALIBRER (voir étape 6)

state, clients = {}, set()
manual_overrides = {}  # {badge_id: (x, y)} - positions forcees pour tester sans BLE
current_bpm = {}   # {badge_id: bpm simule} - EN ATTENTE d'un vrai capteur biometrique
bpm_history = {}   # {badge_id: deque des dernieres valeurs, pour la courbe du profil}
prev_alert = {}    # {badge_id: bool} - detecte les transitions pour ne logger qu'une fois


rssi_history = {} # { (badge, anchor): deque(maxlen=5) }

def ingest(badge, anchor, rssi):
    key = (badge, anchor)
    if key not in rssi_history:
        rssi_history[key] = deque(maxlen=5)
    
    rssi_history[key].append(rssi)
    
    # Utilisation de la médiane pour éliminer les valeurs déviantes
    median_rssi = float(np.median(rssi_history[key]))
    state.setdefault(badge, {})[anchor] = median_rssi


def rssi_to_dist(rssi):
    # Clamper le RSSI pour éviter des explosions de distances théoriques
    rssi_clamped = min(max(rssi, -90), -35)
    dist = 10 ** ((TX_POWER - rssi_clamped) / (10 * N))
    return min(dist, 10.0) # Plafond max


def trilaterate(dists):
    ids = list(dists)
    pts = np.array([ANCHORS[i] for i in ids])
    d = np.array([dists[i] for i in ids])
    res = lambda p: np.linalg.norm(pts - p, axis=1) - d
    result = least_squares(
    res, 
    pts.mean(axis=0), 
    bounds=([0.5, 0.5], [ROOM_WIDTH_M_SERVER - 0.5, ROOM_HEIGHT_M_SERVER - 0.5])
)


smoothed_positions = {}
last_seen = {}   # {badge_id: (x, y, timestamp)} - pour detecter les sauts de position impossibles
forced_anomaly = {}  # {badge_id: timestamp d'expiration} - saut suspect force a titre de demo


def zone_of(x, y):
    for name, (x1, y1, x2, y2) in ZONES.items():
        if x1 <= x <= x2 and y1 <= y <= y2:
            return name
    return "Coursive"


baseline_bpm = {}  # {badge_id: valeur de repos personnelle, fixee une fois}


def update_bpm(badge):
    """Simule un BPM plausible : marche aleatoire QUI REVIENT vers une
    valeur de repos personnelle (mean-reverting), plutot qu'une derive
    libre qui finirait par atteindre des extremes au hasard.
    EN ATTENTE d'integration d'un vrai capteur (bracelet/montre connectee)."""
    baseline = baseline_bpm.setdefault(badge, random.uniform(68, 82))
    prev = current_bpm.get(badge, baseline)
    pull_to_baseline = (baseline - prev) * 0.08   # tire doucement vers le repos
    bpm = prev + pull_to_baseline + random.gauss(0, 1.8)
    bpm = max(55, min(bpm, 145))
    current_bpm[badge] = bpm
    bpm_history.setdefault(badge, deque(maxlen=150)).append(round(bpm))  # ~30s d'historique
    return bpm


def snapshot():
    out = []
    all_badges = set(state.keys()) | set(manual_overrides.keys())
    for badge in all_badges:
        if badge in manual_overrides:
            # position forcee manuellement (mode test sans BLE) : on saute
            # entierement le calcul RSSI/trilateration
            x, y = manual_overrides[badge]
            smoothed_positions[badge] = np.array([x, y])
            signal = None          # pas de vrai signal BLE en mode test
            mode = "test"
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
                raw_x, raw_y = anchor_pos + direction * min(dist, 5.5)
                mode = "1-ancre"
            else:
                continue

            prev = smoothed_positions.get(badge, np.array([raw_x, raw_y]))
            smoothed = 0.65 * prev + 0.35 * np.array([raw_x, raw_y])
            smoothed_positions[badge] = smoothed
            x, y = smoothed
            # RSSI brut par ancre (arrondi), pour affichage cote dashboard
            signal = {a: round(r) for a, r in s.items()}
        zone = zone_of(x, y)

        # --- 1. Restriction de vitesse (Clamp) sur les coordonnées brutes ---
        now_t = time.time()
        prev_seen = last_seen.get(badge)

        if mode != "test" and prev_seen is not None:
            px, py, pt = prev_seen
            dt = max(now_t - pt, 0.05)  # Sécurité contre division par zéro
            
            MAX_SPEED_M_S = 1.8  # Vitesse max réaliste (1.8 m/s)
            max_dist = MAX_SPEED_M_S * dt

            dist_raw = math.hypot(raw_x - px, raw_y - py)
            if dist_raw > max_dist and dist_raw > 0:
                # On ramène le point brut sur le cercle de rayon max_dist
                ratio = max_dist / dist_raw
                raw_x = px + (raw_x - px) * ratio
                raw_y = py + (raw_y - py) * ratio

        # --- 2. Lissage exponentiel classique ---
        prev_pos = smoothed_positions.get(badge, np.array([raw_x, raw_y]))
        smoothed = 0.65 * prev_pos + 0.35 * np.array([raw_x, raw_y])
        smoothed_positions[badge] = smoothed
        x, y = smoothed
        signal = {a: round(r) for a, r in s.items()}

        # --- 3. Détection d'anomalie (saut suspect / usurpation) ---
        anomaly = False
        if mode != "test" and prev_seen is not None:
            px, py, pt = prev_seen
            dt = now_t - pt
            if dt > 0.05:
                # Vitesse calculée après filtrage pour repérer les sauts bruts
                speed = math.hypot(x - px, y - py) / dt
                if speed > 2.5:  # Seuil de téléportation suspecte
                    anomaly = True

        last_seen[badge] = (x, y, now_t)

        if forced_anomaly.get(badge, 0) > now_t:
            # Déclenchement forcé à titre de démo
            anomaly = True

        crew = CREW.get(badge)
        bpm = update_bpm(badge)
        zone_sec = SECURITY.get(zone)  # None si "Coursive" (pas une salle)

        if zone_sec is None:
            allowed, motif = True, None
        elif crew is None:
            # badge sans profil equipage (ex : intrus) - seules les zones
            # publiques (niveau < 4) restent accessibles
            allowed = zone_sec["niveau_securite"] < 4
            motif = None if allowed else "Badge non enregistré dans l'équipage — accès zone critique refusé."
        elif zone not in crew["clearance"]:
            # double controle 1/2 : le role n'a meme pas le droit d'entrer
            # dans cette salle, peu importe l'etat physiologique
            allowed = False
            motif = f"Rôle « {crew['role']} » non habilité pour la zone {zone}."
        else:
            # double controle 2/2 : role habilite, mais BPM au-dessus du
            # seuil de la zone au moment present
            allowed = bpm <= zone_sec["bpm_max_autorise"]
            motif = None if allowed else (
                f"BPM ({bpm:.0f}) supérieur au seuil autorisé ({zone_sec['bpm_max_autorise']}) "
                f"pour la zone {zone}."
            )

        alert = not allowed
        # ne journalise qu'au moment de la transition (pas a chaque frame)
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
            "signal": signal,   # {"A1": -62, "A2": -70, ...} ou null en mode test
            "mode": mode,       # "trilateration" | "1-ancre" | "test"
            "anomaly": anomaly, # true si saut de position suspect (indice d'usurpation)
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
    # asyncio.create_task(sim_loop())  # simulateur desactive pour le test reel


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
        badge: {**info, "clearance": sorted(info["clearance"])}  # set -> liste triee (JSON)
        for badge, info in CREW.items()
    }
    return {"crew": crew_json, "zones_security": SECURITY}


@app.post("/roles/authorize")
def authorize_role(d: dict):
    """Ajoute une habilitation role -> salle.
    Payload : {"role": "Ingénieur Agronome", "room": "Réacteur"}"""
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
    CREW = load_crew()  # recharge pour appliquer immediatement le changement
    return {"authorized": {"role": role_name, "room": room}}


@app.post("/roles/revoke")
def revoke_role_access(d: dict):
    """Retire une habilitation role -> salle.
    Payload : {"role": "Ingénieur Agronome", "room": "Réacteur"}"""
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
    """Liste tous les roles avec leurs habilitations actuelles."""
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
    """Historique recent du BPM d'un badge, pour tracer la courbe dans la
    fiche de profil du dashboard."""
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


# --- Mode sauvetage : verifie qu'une salle est vide avant de sceller un sas -

@app.post("/rescue/{zone}")
def rescue(zone: str):
    """En cas d'incident (incendie, depressurisation...), verifie qui se
    trouve encore dans la salle avant d'autoriser le scellement du sas.
    Utilise le dernier etat connu (positions du dernier snapshot)."""
    if zone not in ZONES:
        return {"error": f"Salle inconnue. Salles valides : {list(ZONES.keys())}"}
    people = snapshot()
    trapped = [p["name"] for p in people if p["zone"] == zone]
    return {"zone": zone, "trapped": trapped, "can_seal": len(trapped) == 0}


# --- Mode test sans BLE : placer un badge dans une salle a la main ---------

@app.get("/test/rooms")
def test_rooms():
    """Liste des salles utilisables pour le test manuel."""
    return {"rooms": list(ZONES.keys())}


@app.post("/test/move")
def test_move(d: dict):
    """Place un badge directement dans une salle, sans RSSI/BLE.
    Payload : {"badge": "ASTRA-001", "room": "Laboratoire"}
    "badge" peut etre n'importe quel id (ASTRA-001/002/003 pour un profil
    connu, ou autre chose type "INTRUS-01" pour tester un badge inconnu)."""
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
    """Place un badge a des coordonnees precises (en metres), pour le
    deplacement libre au clavier (ZQSD) cote frontend.
    Payload : {"badge": "ASTRA-001", "x": 7.2, "y": 3.9}"""
    badge = d["badge"]
    x = round(max(0.3, min(float(d["x"]), ROOM_WIDTH_M_SERVER - 0.3)), 2)
    y = round(max(0.3, min(float(d["y"]), ROOM_HEIGHT_M_SERVER - 0.3)), 2)
    manual_overrides[badge] = (x, y)
    return {"badge": badge, "position": (x, y)}


@app.post("/test/clear/{badge}")
def test_clear(badge: str):
    """Retire le placement manuel (reprend le suivi BLE reel s'il y en a un)."""
    manual_overrides.pop(badge, None)
    return {"cleared": badge}


@app.post("/test/clear-all")
def test_clear_all():
    manual_overrides.clear()
    return {"cleared": "all"}


@app.post("/test/reset-bpm/{badge}")
def reset_bpm(badge: str):
    """Remet le BPM simule d'un badge a sa valeur de repos - utile si la
    marche aleatoire a derive vers un extreme pendant un test prolonge."""
    baseline_bpm.pop(badge, None)
    current_bpm.pop(badge, None)
    prev_alert.pop(badge, None)
    return {"reset": badge}


@app.post("/test/stress/{badge}")
def induce_stress(badge: str):
    """Provoque un pic de stress simule (BPM eleve) pour demontrer le
    declenchement d'alerte a la demande. Redescend naturellement vers la
    valeur de repos au fil des ticks suivants (retour au calme progressif)."""
    bpm = random.uniform(125, 142)
    current_bpm[badge] = bpm
    return {"badge": badge, "bpm": round(bpm)}


@app.post("/test/simulate-jump/{badge}")
def simulate_jump(badge: str):
    """Force un 'saut de position suspect' a des fins de demonstration,
    visible pendant 2,5 secondes sur le dashboard. Le badge doit deja etre
    suivi (place via /test/move ou du vrai BLE)."""
    forced_anomaly[badge] = time.time() + 2.5
    return {"badge": badge, "forced_anomaly_until": "2.5s"}