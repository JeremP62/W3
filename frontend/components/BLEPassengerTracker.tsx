"use client";

import { useEffect, useRef, useState, useCallback } from "react";

// ---------------------------------------------------------------------------
// Configuration — calée sur plan_vaisseau_v3_clean.png
// Toutes les coordonnées sont en mètres, converties en pixels via SCALE.
// ---------------------------------------------------------------------------
const WS_URL = "ws://localhost:8000/ws";
const HTTP_BASE = "http://localhost:8000";
const TEST_BADGES = ["ASTRA-001", "ASTRA-002", "ASTRA-003", "INTRUS-01"];
// Correspondance affichage <-> badge BLE (doit rester synchro avec le
// mapping fait côté serveur dans init_db(), section "astra_badge_id").
const TEST_BADGE_LABELS: Record<string, string> = {
  "ASTRA-001": "Elena Rostova — Commandant",
  "ASTRA-002": "Chloe Dubois — Cyber & IA",
  "ASTRA-003": "Marcus Vance — Pilote",
  "INTRUS-01": "Intrus (non enregistré)",
};
// Toutes les zones connues côté serveur — inclut le Poste de Pilotage, qui
// n'est pas dans ROOMS (dessiné à part en triangle, pas comme un rectangle).
const TEST_ROOMS = [
  "Réacteur",
  "Quartiers des équipes",
  "Cafétéria",
  "Laboratoire",
  "Infirmerie",
  "Poste de Sécurité & Serveur",
  "Poste de Pilotage",
];
const ROOM_WIDTH_M = 15;
const ROOM_HEIGHT_M = 8.3;
const SCALE = 55; // pixels par mètre
const CANVAS_W = ROOM_WIDTH_M * SCALE;
const CANVAS_H = ROOM_HEIGHT_M * SCALE;

interface Room {
  name: string;
  x1: number; y1: number; x2: number; y2: number;
  border: string;
  fill: string;
  restricted?: boolean;
  lines: string[];   // texte de l'étiquette, une entrée par ligne
  vertical?: boolean; // texte tourné à 90° (cas du Réacteur)
}

// Salles — mêmes noms que ceux renvoyés par server.py (champ "zone")
const ROOMS: Room[] = [
  { name: "Réacteur", x1: 1.35, y1: 2.45, x2: 3.08, y2: 5.65,
    border: "#ff4d5e", fill: "rgba(255,77,94,0.14)", restricted: true, lines: ["RÉACTEUR"], vertical: true },
  { name: "Quartiers des équipes", x1: 3.45, y1: 1.28, x2: 5.20, y2: 3.30,
    border: "#39ff88", fill: "rgba(57,255,136,0.10)", lines: ["QUARTIERS", "DES ÉQUIPES"] },
  { name: "Cafétéria", x1: 3.45, y1: 4.85, x2: 5.20, y2: 6.85,
    border: "#39ff88", fill: "rgba(57,255,136,0.10)", lines: ["CAFÉTÉRIA"] },
  { name: "Laboratoire", x1: 6.83, y1: 1.28, x2: 8.57, y2: 3.30,
    border: "#ffb84d", fill: "rgba(255,184,77,0.12)", lines: ["LABORATOIRE"] },
  { name: "Infirmerie", x1: 6.83, y1: 4.85, x2: 8.57, y2: 6.85,
    border: "#ffb84d", fill: "rgba(255,184,77,0.12)", lines: ["INFIRMERIE"] },
  { name: "Poste de Sécurité & Serveur", x1: 10.20, y1: 1.28, x2: 11.52, y2: 3.30,
    border: "#ff4d5e", fill: "rgba(255,77,94,0.14)", restricted: true, lines: ["SÉCURITÉ", "&", "SERVEUR"] },
];

// Segments de coursive verticale (purement décoratifs, sans logique de zone)
const VCORRIDORS = [
  { x1: 5.58, y1: 2.00, x2: 6.45, y2: 6.10 },
  { x1: 8.95, y1: 2.00, x2: 9.83, y2: 6.10 },
];

// Coursive principale horizontale
const MAIN_CORRIDOR = { x1: 3.08, y1: 3.55, x2: 11.52, y2: 4.45 };

// Poste de pilotage — triangle, base à x1, pointe à apexX
const PILOTAGE = { x1: 11.52, y1: 3.55, y2: 4.45, apexX: 13.9, apexY: 4.0 };

// Sas (portes) : petit rectangle gris avec point bleu, aux jonctions salle/coursive
const DOORS: { x1: number; y1: number; x2: number; y2: number }[] = [
  { x1: 3.08, y1: 3.83, x2: 3.45, y2: 4.17 },   // Réacteur
  { x1: 4.12, y1: 3.30, x2: 4.55, y2: 3.55 },   // Quartiers
  { x1: 4.12, y1: 4.45, x2: 4.55, y2: 4.85 },   // Cafétéria
  { x1: 7.485, y1: 3.30, x2: 7.915, y2: 3.55 }, // Laboratoire
  { x1: 7.485, y1: 4.45, x2: 7.915, y2: 4.85 }, // Infirmerie
  { x1: 10.65, y1: 3.30, x2: 11.08, y2: 3.55 }, // Poste de Sécurité & Serveur
  { x1: 11.15, y1: 3.83, x2: 11.52, y2: 4.17 }, // Poste de pilotage
];

// Coque : hexagone pointu aux deux extrémités
const HULL: [number, number][] = [
  [1.0, 4.0],    // pointe gauche
  [3.0, 0.9],    // coin haut-gauche
  [11.5, 0.9],   // coin haut-droit
  [13.9, 4.0],   // pointe droite (rejoint l'apex du poste de pilotage)
  [11.5, 7.15],  // coin bas-droit
  [3.0, 7.15],   // coin bas-gauche
];

const ANCHORS: { id: string; x: number; y: number }[] = [
  { id: "A1", x: 3.5, y: 1.5 },
  { id: "A2", x: 11.0, y: 1.5 },
  { id: "A3", x: 11.0, y: 6.6 },
  { id: "A4", x: 3.5, y: 6.6 },
];

// ---------------------------------------------------------------------------
// Types — doivent correspondre au JSON envoyé par server.py (snapshot())
// ---------------------------------------------------------------------------
interface Passenger {
  id: string;      // identifiant BLE (nom annoncé, ex: "ASTRA-002")
  name: string;
  role: string;
  x: number;        // position en mètres
  y: number;
  zone: string;      // doit correspondre à un des noms de ROOMS, ou "Coursive"
  bpm: number;       // fréquence cardiaque simulée (en attente d'un vrai capteur)
  alert: boolean;   // true si présence non autorisée en zone restreinte
  motif?: string | null;  // raison du refus, si alert=true
}

type ConnState = "connecting" | "connected" | "disconnected";

interface LogEntry {
  horodatage: string;
  nom_complet: string;
  nom_zone: string;
  bpm_lors_demande: number;
  acces_accorde: number; // 0 ou 1
  motif_refus: string | null;
}

// ---------------------------------------------------------------------------
// Composant principal
// ---------------------------------------------------------------------------
export default function BLEPassengerTracker() {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const roomCanvasRef = useRef<HTMLCanvasElement>(null);
  const [people, setPeople] = useState<Passenger[]>([]);
  const [selected, setSelected] = useState<Passenger | null>(null);
  const [conn, setConn] = useState<ConnState>("connecting");
  const [selectedRoom, setSelectedRoom] = useState<Room | null>(null);
  const [intrusion, setIntrusion] = useState<Passenger | null>(null);
  const [logsOpen, setLogsOpen] = useState(false);
  const [logs, setLogs] = useState<LogEntry[]>([]);
  const [testBadge, setTestBadge] = useState(TEST_BADGES[0]);
  const [testStatus, setTestStatus] = useState<{ ok: boolean; msg: string } | null>(null);
  const wsRef = useRef<WebSocket | null>(null);
  const prevAlertRef = useRef<Record<string, boolean>>({});

  // --- Connexion WebSocket, avec reconnexion automatique --------------------
  useEffect(() => {
    let retryTimer: ReturnType<typeof setTimeout>;

    function connect() {
      const ws = new WebSocket(WS_URL);
      wsRef.current = ws;
      setConn("connecting");

      ws.onopen = () => setConn("connected");
      ws.onclose = () => {
        setConn("disconnected");
        retryTimer = setTimeout(connect, 2000); // tentative de reconnexion
      };
      ws.onerror = () => ws.close();
      ws.onmessage = (event) => {
        try {
          const data: Passenger[] = JSON.parse(event.data);
          // détecte une transition non-alerte -> alerte, pour déclencher le pop-up
          // une seule fois par intrusion (pas à chaque frame tant qu'elle dure)
          for (const p of data) {
            const wasAlert = prevAlertRef.current[p.id] ?? false;
            if (p.alert && !wasAlert) {
              setIntrusion(p);
            }
            prevAlertRef.current[p.id] = p.alert;
          }
          setPeople(data);
        } catch {
          // trame invalide ignorée
        }
      };
    }

    connect();
    return () => {
      clearTimeout(retryTimer);
      wsRef.current?.close();
    };
  }, []);

  // --- Dessin de la carte -------------------------------------------------
  const buildHullPath = useCallback((ctx: CanvasRenderingContext2D) => {
    ctx.beginPath();
    HULL.forEach(([mx, my], i) => {
      const x = mx * SCALE, y = my * SCALE;
      if (i === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y);
    });
    ctx.closePath();
  }, []);

  const drawRoom = (ctx: CanvasRenderingContext2D, r: Room) => {
    const x = r.x1 * SCALE, y = r.y1 * SCALE;
    const w = (r.x2 - r.x1) * SCALE, h = (r.y2 - r.y1) * SCALE;

    ctx.save();
    ctx.shadowColor = r.border;
    ctx.shadowBlur = 10;
    ctx.fillStyle = r.fill;
    ctx.fillRect(x, y, w, h);
    ctx.restore();

    ctx.strokeStyle = r.border;
    ctx.lineWidth = 2;
    ctx.strokeRect(x, y, w, h);

    ctx.fillStyle = "#d7ffe8";
    ctx.font = "bold 12px 'JetBrains Mono', ui-monospace, monospace";
    ctx.textAlign = "center";
    ctx.textBaseline = "middle";
    const cx = x + w / 2, cy = y + h / 2;

    if (r.vertical) {
      ctx.save();
      ctx.translate(cx, cy);
      ctx.rotate(-Math.PI / 2);
      r.lines.forEach((line, i) => ctx.fillText(line, 0, (i - (r.lines.length - 1) / 2) * 14));
      ctx.restore();
    } else {
      r.lines.forEach((line, i) => ctx.fillText(line, cx, cy + (i - (r.lines.length - 1) / 2) * 14));
    }
    ctx.textAlign = "left";
    ctx.textBaseline = "alphabetic";
  };

  const drawDoor = (ctx: CanvasRenderingContext2D, d: { x1: number; y1: number; x2: number; y2: number }) => {
    const x = d.x1 * SCALE, y = d.y1 * SCALE;
    const w = (d.x2 - d.x1) * SCALE, h = (d.y2 - d.y1) * SCALE;
    ctx.fillStyle = "#0f2019";
    ctx.strokeStyle = "#39ff88";
    ctx.lineWidth = 1;
    ctx.fillRect(x, y, w, h);
    ctx.strokeRect(x, y, w, h);
    ctx.fillStyle = "#39ff88";
    ctx.beginPath();
    ctx.arc(x + w / 2, y + h / 2, Math.min(w, h) * 0.22, 0, Math.PI * 2);
    ctx.fill();
  };

  const draw = useCallback(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    ctx.clearRect(0, 0, CANVAS_W, CANVAS_H);

    // Fond spatial + grille (esthétique HUD : quadrillage phosphore très bas)
    ctx.fillStyle = "#020705";
    ctx.fillRect(0, 0, CANVAS_W, CANVAS_H);
    ctx.strokeStyle = "rgba(57,255,136,0.05)";
    ctx.lineWidth = 1;
    for (let x = 0; x <= CANVAS_W; x += SCALE / 2) {
      ctx.beginPath(); ctx.moveTo(x, 0); ctx.lineTo(x, CANVAS_H); ctx.stroke();
    }
    for (let y = 0; y <= CANVAS_H; y += SCALE / 2) {
      ctx.beginPath(); ctx.moveTo(0, y); ctx.lineTo(CANVAS_W, y); ctx.stroke();
    }

    // Contour de la coque
    buildHullPath(ctx);
    ctx.strokeStyle = "rgba(57,255,136,0.4)";
    ctx.lineWidth = 1.5;
    ctx.stroke();

    // Coursives (horizontale + segments verticaux) — teinte cyan-vert
    // distincte du vert des salles, pour lire "circulation" au premier coup d'œil
    const drawCorridorRect = (c: { x1: number; y1: number; x2: number; y2: number }) => {
      const x = c.x1 * SCALE, y = c.y1 * SCALE;
      const w = (c.x2 - c.x1) * SCALE, h = (c.y2 - c.y1) * SCALE;
      ctx.fillStyle = "#03120e";
      ctx.fillRect(x, y, w, h);
      ctx.strokeStyle = "#2de0c0";
      ctx.lineWidth = 2;
      ctx.strokeRect(x, y, w, h);
    };
    drawCorridorRect(MAIN_CORRIDOR);
    VCORRIDORS.forEach(drawCorridorRect);

    // Salles
    ROOMS.forEach((r) => drawRoom(ctx, r));

    // Poste de pilotage (triangle)
    ctx.beginPath();
    ctx.moveTo(PILOTAGE.x1 * SCALE, PILOTAGE.y1 * SCALE);
    ctx.lineTo(PILOTAGE.apexX * SCALE, PILOTAGE.apexY * SCALE);
    ctx.lineTo(PILOTAGE.x1 * SCALE, PILOTAGE.y2 * SCALE);
    ctx.closePath();
    ctx.save();
    ctx.shadowColor = "#ff4d5e";
    ctx.shadowBlur = 10;
    ctx.fillStyle = "rgba(255,77,94,0.16)";
    ctx.fill();
    ctx.restore();
    ctx.strokeStyle = "#ff4d5e";
    ctx.lineWidth = 2;
    ctx.stroke();
    ctx.fillStyle = "#d7ffe8";
    ctx.font = "bold 11px 'JetBrains Mono', ui-monospace, monospace";
    ctx.textAlign = "left";
    ctx.fillText("POSTE DE", PILOTAGE.x1 * SCALE + 10, (PILOTAGE.y1 + PILOTAGE.y2) / 2 * SCALE - 4);
    ctx.fillText("PILOTAGE", PILOTAGE.x1 * SCALE + 10, (PILOTAGE.y1 + PILOTAGE.y2) / 2 * SCALE + 10);

    // Sas
    DOORS.forEach((d) => drawDoor(ctx, d));

    // Ancres BLE
    for (const a of ANCHORS) {
      ctx.fillStyle = "#4a9179";
      ctx.beginPath();
      ctx.arc(a.x * SCALE, a.y * SCALE, 4, 0, Math.PI * 2);
      ctx.fill();
      ctx.font = "10px 'JetBrains Mono', ui-monospace, monospace";
      ctx.fillStyle = "#4a9179";
      ctx.fillText(a.id, a.x * SCALE + 6, a.y * SCALE - 6);
    }

    // Passagers — on répartit d'abord les étiquettes pour éviter qu'elles
    // se chevauchent quand plusieurs points sont proches les uns des autres.
    const placedLabels: { x: number; y: number; w: number; h: number }[] = [];
    ctx.font = "11px 'JetBrains Mono', ui-monospace, monospace";

    const findLabelSpot = (px: number, py: number, text: string) => {
      const w = ctx.measureText(text).width + 6;
      const h = 14;
      // candidats, du plus proche du point au plus éloigné
      const candidates = [
        { x: px + 12, y: py - 8 },
        { x: px + 12, y: py + 16 },
        { x: px - w - 4, y: py - 8 },
        { x: px - w - 4, y: py + 16 },
        { x: px + 12, y: py - 22 },
        { x: px + 12, y: py + 30 },
      ];
      for (const c of candidates) {
        const box = { x: c.x, y: c.y - h + 3, w, h };
        const overlaps = placedLabels.some(
          (o) => box.x < o.x + o.w && box.x + box.w > o.x && box.y < o.y + o.h && box.y + box.h > o.y
        );
        if (!overlaps) {
          placedLabels.push(box);
          return c;
        }
      }
      placedLabels.push({ x: candidates[0].x, y: candidates[0].y - h + 3, w, h });
      return candidates[0];
    };

    for (const p of people) {
      const px = p.x * SCALE;
      const py = p.y * SCALE;

      if (p.alert) {
        ctx.beginPath();
        ctx.arc(px, py, 14, 0, Math.PI * 2);
        ctx.fillStyle = "rgba(255,50,50,0.25)";
        ctx.fill();
      }

      ctx.beginPath();
      ctx.arc(px, py, 8, 0, Math.PI * 2);
      ctx.fillStyle = p.alert ? "#ff3b3b" : "#39e07a";
      ctx.fill();
      ctx.strokeStyle = "#fff";
      ctx.lineWidth = 1.5;
      ctx.stroke();

      const spot = findLabelSpot(px, py, p.name);
      const textW = ctx.measureText(p.name).width;
      ctx.fillStyle = "rgba(2,7,5,0.78)";
      ctx.fillRect(spot.x - 3, spot.y - 11, textW + 6, 15);
      ctx.fillStyle = "#d7ffe8";
      ctx.fillText(p.name, spot.x, spot.y);
    }
  }, [people, buildHullPath]);

  useEffect(() => {
    draw();
  }, [draw]);

  // --- Clic sur la carte : sélectionne un passager proche, sinon une salle
  // --- Mode test : appelle l'API et affiche vraiment le résultat -----------
  async function callTest(path: string, body: unknown) {
    try {
      const res = await fetch(`${HTTP_BASE}${path}`, {
        method: "POST",
        ...(body ? { headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) } : {}),
      });
      const data = await res.json().catch(() => null);
      if (!res.ok) {
        setTestStatus({ ok: false, msg: `Erreur ${res.status} : ${data?.detail ?? "requête refusée"}` });
        return;
      }
      if (data?.error) {
        setTestStatus({ ok: false, msg: data.error });
        return;
      }
      setTestStatus({ ok: true, msg: JSON.stringify(data) });
    } catch (err) {
      setTestStatus({
        ok: false,
        msg: `Connexion au serveur impossible (${HTTP_BASE}). Vérifie que uvicorn tourne et a été relancé après l'ajout du CORS.`,
      });
    }
  }

  // --- Déplacement libre au clavier (ZQSD) pour le badge en mode test ----
  const walkPosRef = useRef<Record<string, { x: number; y: number }>>({});

  // --- Journal d'accès : récupération + rafraîchissement pendant l'ouverture
  async function fetchLogs() {
    try {
      const res = await fetch(`${HTTP_BASE}/logs?limit=25`);
      const data = await res.json();
      setLogs(data.logs ?? []);
    } catch {
      // silencieux : le bouton restera juste vide si le serveur est injoignable
    }
  }

  useEffect(() => {
    if (!logsOpen) return;
    fetchLogs();
    const interval = setInterval(fetchLogs, 3000);
    return () => clearInterval(interval);
  }, [logsOpen]);

  useEffect(() => {
    const STEP = 0.3;
    const MARGIN = 0.4;

    function moveTestBadge(dx: number, dy: number) {
      const known = people.find((p) => p.id === testBadge);
      const cur =
        walkPosRef.current[testBadge] ??
        (known ? { x: known.x, y: known.y } : { x: ROOM_WIDTH_M / 2, y: ROOM_HEIGHT_M / 2 });

      // arrondi à 2 décimales pour éviter l'accumulation d'imprécisions
      // flottantes (0.1 + 0.2 = 0.30000000000000004) au fil des appuis
      const round2 = (n: number) => Math.round(n * 100) / 100;
      const next = {
        x: round2(Math.min(Math.max(cur.x + dx, MARGIN), ROOM_WIDTH_M - MARGIN)),
        y: round2(Math.min(Math.max(cur.y + dy, MARGIN), ROOM_HEIGHT_M - MARGIN)),
      };
      walkPosRef.current[testBadge] = next;
      callTest("/test/set-position", { badge: testBadge, x: next.x, y: next.y });
    }

    function onKeyDown(e: KeyboardEvent) {
      const tag = (document.activeElement?.tagName || "").toLowerCase();
      if (tag === "input" || tag === "select" || tag === "textarea") return; // ne gêne pas la saisie

      switch (e.key.toLowerCase()) {
        case "z": case "arrowup": moveTestBadge(0, -STEP); break;
        case "s": case "arrowdown": moveTestBadge(0, STEP); break;
        case "q": case "arrowleft": moveTestBadge(-STEP, 0); break;
        case "d": case "arrowright": moveTestBadge(STEP, 0); break;
        default: return;
      }
      e.preventDefault();
    }

    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [testBadge, people]);

  function handleCanvasClick(e: React.MouseEvent<HTMLCanvasElement>) {
    const rect = e.currentTarget.getBoundingClientRect();
    const clickX = e.clientX - rect.left;
    const clickY = e.clientY - rect.top;

    let closest: Passenger | null = null;
    let minDist = Infinity;
    for (const p of people) {
      const dx = p.x * SCALE - clickX;
      const dy = p.y * SCALE - clickY;
      const dist = Math.hypot(dx, dy);
      if (dist < minDist) {
        minDist = dist;
        closest = p;
      }
    }
    if (minDist < 20) {
      setSelected(closest);
      return;
    }

    // pas de passager proche : regarde si le clic tombe dans une salle
    const mx = clickX / SCALE, my = clickY / SCALE;
    const room = ROOMS.find((r) => mx >= r.x1 && mx <= r.x2 && my >= r.y1 && my <= r.y2);
    if (room) {
      setSelectedRoom(room);
      setSelected(null);
    }
  }

  // --- Dessin de la vue "salle agrandie" ----------------------------------
  useEffect(() => {
    if (!selectedRoom) return;
    const canvas = roomCanvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    const SIZE = 520;
    canvas.width = SIZE;
    canvas.height = SIZE;

    ctx.clearRect(0, 0, SIZE, SIZE);
    ctx.fillStyle = "#020705";
    ctx.fillRect(0, 0, SIZE, SIZE);

    const pad = 30;
    const inner = SIZE - pad * 2;
    ctx.save();
    ctx.shadowColor = selectedRoom.border;
    ctx.shadowBlur = 16;
    ctx.fillStyle = selectedRoom.fill;
    ctx.fillRect(pad, pad, inner, inner);
    ctx.restore();
    ctx.strokeStyle = selectedRoom.border;
    ctx.lineWidth = 3;
    ctx.strokeRect(pad, pad, inner, inner);

    // grille interieure
    ctx.strokeStyle = "rgba(57,255,136,0.08)";
    ctx.lineWidth = 1;
    for (let i = 1; i < 6; i++) {
      const gx = pad + (inner / 6) * i;
      ctx.beginPath(); ctx.moveTo(gx, pad); ctx.lineTo(gx, pad + inner); ctx.stroke();
      const gy = pad + (inner / 6) * i;
      ctx.beginPath(); ctx.moveTo(pad, gy); ctx.lineTo(pad + inner, gy); ctx.stroke();
    }

    // titre de la salle
    ctx.fillStyle = "#d7ffe8";
    ctx.font = "bold 16px 'JetBrains Mono', ui-monospace, monospace";
    ctx.textAlign = "left";
    ctx.fillText(selectedRoom.lines.join(" "), pad, pad - 10);

    // dimensions reelles affichees
    const roomWm = (selectedRoom.x2 - selectedRoom.x1).toFixed(2);
    const roomHm = (selectedRoom.y2 - selectedRoom.y1).toFixed(2);
    ctx.fillStyle = "rgba(215,255,232,0.5)";
    ctx.font = "11px 'JetBrains Mono', ui-monospace, monospace";
    ctx.fillText(`${roomWm} m x ${roomHm} m`, pad, SIZE - 8);

    // seuls les passagers dont la zone reelle correspond a cette salle
    // sont affiches ici (evite qu'une personne dans une autre salle reste
    // "collee" a un bord, comme quand le filtre etait desactive)
    const inRoom = people.filter((p) => p.zone === selectedRoom.name);
    for (const p of inRoom) {
      // position relative dans la salle (0..1), projetee dans le carre agrandi
      const relX = (p.x - selectedRoom.x1) / (selectedRoom.x2 - selectedRoom.x1);
      const relY = (p.y - selectedRoom.y1) / (selectedRoom.y2 - selectedRoom.y1);
      const px = pad + Math.min(Math.max(relX, 0), 1) * inner;
      const py = pad + Math.min(Math.max(relY, 0), 1) * inner;

      if (p.alert) {
        ctx.beginPath();
        ctx.arc(px, py, 22, 0, Math.PI * 2);
        ctx.fillStyle = "rgba(255,77,94,0.25)";
        ctx.fill();
      }
      ctx.beginPath();
      ctx.arc(px, py, 12, 0, Math.PI * 2);
      ctx.fillStyle = p.alert ? "#ff4d5e" : "#39ff88";
      ctx.fill();
      ctx.strokeStyle = "#d7ffe8";
      ctx.lineWidth = 2;
      ctx.stroke();

      ctx.fillStyle = "#d7ffe8";
      ctx.font = "13px 'JetBrains Mono', ui-monospace, monospace";
      ctx.textAlign = "center";
      ctx.fillText(p.name, px, py - 20);
      ctx.font = "11px 'JetBrains Mono', ui-monospace, monospace";
      ctx.fillStyle = "rgba(215,255,232,0.6)";
      ctx.fillText(`${p.bpm} bpm`, px, py + 32);
      ctx.textAlign = "left";
    }

    if (inRoom.length === 0) {
      ctx.fillStyle = "rgba(215,255,232,0.35)";
      ctx.font = "13px 'JetBrains Mono', ui-monospace, monospace";
      ctx.textAlign = "center";
      ctx.fillText("Aucune détection dans cette salle", SIZE / 2, SIZE / 2);
      ctx.textAlign = "left";
    }
  }, [selectedRoom, people]);

  const alertCount = people.filter((p) => p.alert).length;

  return (
    <div style={styles.container}>
      <style>{`
        @keyframes astra-pulse {
          0%, 100% { opacity: 1; box-shadow: 0 0 6px currentColor; }
          50% { opacity: 0.5; box-shadow: 0 0 2px currentColor; }
        }
      `}</style>
      <div style={styles.header}>
        <h3 style={styles.title}>Suivi des passagers — module BLE</h3>
        <div style={styles.statusRow}>
          <span style={{ ...styles.dot, background: connColor(conn), color: connColor(conn) }} />
          <span style={styles.statusText}>{connLabel(conn)}</span>
          {alertCount > 0 && (
            <span style={styles.alertBadge}>{alertCount} alerte{alertCount > 1 ? "s" : ""}</span>
          )}
          <button style={styles.logsBtn} onClick={() => setLogsOpen(true)}>
            📜 Journal d'accès
          </button>
        </div>
      </div>

      <div style={styles.body}>
        <canvas
          ref={canvasRef}
          width={CANVAS_W}
          height={CANVAS_H}
          onClick={handleCanvasClick}
          style={styles.canvas}
        />

        <div style={styles.sidebar}>
          <div style={styles.testPanel}>
            <div style={styles.sidebarTitle}>Mode test (sans BLE)</div>
            <div style={styles.keyHint}>⌨ Z Q S D (ou flèches) : déplacer le profil sélectionné en direct</div>
            <select
              value={testBadge}
              onChange={(e) => setTestBadge(e.target.value)}
              style={styles.testSelect}
            >
              {TEST_BADGES.map((b) => (
                <option key={b} value={b}>{TEST_BADGE_LABELS[b] ?? b}</option>
              ))}
            </select>
            <div style={styles.testRoomGrid}>
              {TEST_ROOMS.map((room) => (
                <button
                  key={room}
                  style={styles.testRoomBtn}
                  onClick={() => callTest("/test/move", { badge: testBadge, room })}
                >
                  {room}
                </button>
              ))}
            </div>
            <button
              style={styles.testClearBtn}
              onClick={() => callTest(`/test/clear/${testBadge}`, null)}
            >
              Retirer {TEST_BADGE_LABELS[testBadge] ?? testBadge}
            </button>
            <button
              style={styles.testResetBtn}
              onClick={() => callTest(`/test/reset-bpm/${testBadge}`, null)}
            >
              Réinitialiser le BPM de {TEST_BADGE_LABELS[testBadge] ?? testBadge}
            </button>
            <button
              style={styles.testStressBtn}
              onClick={() => callTest(`/test/stress/${testBadge}`, null)}
            >
              ⚡ Simuler un pic de stress
            </button>
            {testStatus && (
              <div style={testStatus.ok ? styles.testStatusOk : styles.testStatusErr}>
                {testStatus.msg}
              </div>
            )}
          </div>

          <div style={styles.sidebarTitle}>Personnes détectées ({people.length})</div>
          <div style={styles.list}>
            {people.map((p) => (
              <button
                key={p.id}
                onClick={() => setSelected(p)}
                style={{
                  ...styles.listItem,
                  borderColor: p.alert ? "#ff3b3b" : "rgba(255,255,255,0.08)",
                  background: selected?.id === p.id ? "rgba(255,255,255,0.06)" : "transparent",
                }}
              >
                <span style={{ ...styles.miniDot, background: p.alert ? "#ff3b3b" : "#39e07a" }} />
                <span style={styles.listName}>{p.name}</span>
                <span style={styles.listZone}>{p.zone}</span>
              </button>
            ))}
            {people.length === 0 && <div style={styles.empty}>Aucune détection pour le moment</div>}
          </div>

          {selected && (
            <div style={styles.panel}>
              <div style={styles.panelHeader}>
                {selected.alert && <span style={styles.panelAlert}>⚠ INTRUSION</span>}
                <div style={styles.panelName}>{selected.name}</div>
              </div>
              <PanelRow label="Rôle" value={selected.role} />
              <PanelRow label="ID BLE" value={selected.id} />
              <PanelRow label="Secteur" value={selected.zone} />
              <PanelRow label="BPM" value={`${selected.bpm} bpm`} />
              <PanelRow label="Position" value={`x: ${selected.x.toFixed(1)}m · y: ${selected.y.toFixed(1)}m`} />
              {selected.alert && selected.motif && (
                <div style={styles.motifText}>{selected.motif}</div>
              )}
            </div>
          )}
        </div>
      </div>

      {selectedRoom && (
        <div style={styles.overlay} onClick={() => setSelectedRoom(null)}>
          <div style={styles.overlayCard} onClick={(e) => e.stopPropagation()}>
            <div style={styles.overlayHeader}>
              <h3 style={styles.overlayTitle}>{selectedRoom.lines.join(" ")}</h3>
              <button style={styles.closeBtn} onClick={() => setSelectedRoom(null)}>
                Retour au vaisseau
              </button>
            </div>
            <canvas ref={roomCanvasRef} style={styles.roomCanvas} />
          </div>
        </div>
      )}

      {intrusion && (
        <div style={styles.overlay} onClick={() => setIntrusion(null)}>
          <div style={styles.intrusionCard} onClick={(e) => e.stopPropagation()}>
            <div style={styles.intrusionIcon}>⚠</div>
            <div style={styles.intrusionTitle}>INTRUSION DÉTECTÉE</div>
            <div style={styles.intrusionBody}>
              <PanelRow label="Identité" value={intrusion.name} />
              <PanelRow label="ID BLE" value={intrusion.id} />
              <PanelRow label="Secteur" value={intrusion.zone} />
              <PanelRow label="BPM" value={`${intrusion.bpm} bpm`} />
              <PanelRow label="Heure" value={new Date().toLocaleTimeString()} />
              {intrusion.motif && <div style={styles.motifText}>{intrusion.motif}</div>}
            </div>
            <button style={styles.intrusionBtn} onClick={() => setIntrusion(null)}>
              Accusé de réception
            </button>
          </div>
        </div>
      )}

      {logsOpen && (
        <div style={styles.overlay} onClick={() => setLogsOpen(false)}>
          <div style={styles.logsCard} onClick={(e) => e.stopPropagation()}>
            <div style={styles.overlayHeader}>
              <h3 style={styles.overlayTitle}>Journal d'accès</h3>
              <div style={{ display: "flex", gap: 8 }}>
                <button style={styles.closeBtn} onClick={fetchLogs}>↻ Actualiser</button>
                <button style={styles.closeBtn} onClick={() => setLogsOpen(false)}>Fermer</button>
              </div>
            </div>
            <div style={styles.logsList}>
              {logs.length === 0 && (
                <div style={styles.empty}>Aucun événement enregistré pour le moment.</div>
              )}
              {logs.map((log, i) => (
                <div
                  key={i}
                  style={{
                    ...styles.logRow,
                    borderLeftColor: log.acces_accorde ? "#39e07a" : "#ff3b3b",
                  }}
                >
                  <div style={styles.logRowTop}>
                    <span style={styles.logName}>{log.nom_complet}</span>
                    <span style={styles.logTime}>{log.horodatage}</span>
                  </div>
                  <div style={styles.logRowBottom}>
                    <span>{log.nom_zone}</span>
                    <span>·</span>
                    <span>{log.bpm_lors_demande} bpm</span>
                    <span>·</span>
                    <span style={{ color: log.acces_accorde ? "#39e07a" : "#ff8080" }}>
                      {log.acces_accorde ? "Accès accordé" : "Accès refusé"}
                    </span>
                  </div>
                  {log.motif_refus && <div style={styles.logMotif}>{log.motif_refus}</div>}
                </div>
              ))}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

function PanelRow({ label, value }: { label: string; value: string }) {
  return (
    <div style={styles.panelRow}>
      <span style={styles.panelLabel}>{label}</span>
      <span style={styles.panelValue}>{value}</span>
    </div>
  );
}

function connColor(c: ConnState) {
  if (c === "connected") return "#39e07a";
  if (c === "connecting") return "#e0b339";
  return "#ff3b3b";
}
function connLabel(c: ConnState) {
  if (c === "connected") return "Connecté";
  if (c === "connecting") return "Connexion...";
  return "Déconnecté — reconnexion en cours";
}

// ---------------------------------------------------------------------------
// Styles inline (aucune dépendance externe — remplace par ton système
// de design/Tailwind si le reste du projet en utilise un)
// ---------------------------------------------------------------------------
// ---------------------------------------------------------------------------
// Styles inline — thème HUD terminal de vaisseau (noir/vert phosphore).
// Langage colorimétrique sémantique, pas décoratif : vert = nominal/sécurisé,
// ambre = zone de travail/vigilance, rouge = critique/intrusion — aligné sur
// les niveaux de sécurité réels de la base (Zones_Vaisseau.niveau_securite).
// ---------------------------------------------------------------------------
const FONT_MONO = "'JetBrains Mono', 'Fira Code', ui-monospace, SFMono-Regular, Menlo, Consolas, monospace";

const styles: Record<string, React.CSSProperties> = {
  container: {
    position: "relative",
    background: "#020705",
    border: "1px solid rgba(57,255,136,0.25)",
    borderRadius: 6,
    padding: 18,
    color: "#d7ffe8",
    fontFamily: FONT_MONO,
    boxShadow: "0 0 0 1px rgba(0,0,0,0.4), 0 0 32px rgba(57,255,136,0.06)",
  },
  header: {
    display: "flex",
    justifyContent: "space-between",
    alignItems: "center",
    marginBottom: 14,
    paddingBottom: 10,
    borderBottom: "1px solid rgba(57,255,136,0.18)",
  },
  title: {
    margin: 0,
    fontSize: 14,
    fontWeight: 700,
    letterSpacing: 1.5,
    color: "#39ff88",
    textTransform: "uppercase",
  },
  statusRow: { display: "flex", alignItems: "center", gap: 8 },
  dot: { width: 7, height: 7, borderRadius: "50%", animation: "astra-pulse 2s ease-in-out infinite" },
  statusText: { fontSize: 11, color: "#5f9a7c" },
  alertBadge: {
    background: "rgba(255,77,94,0.14)",
    border: "1px solid rgba(255,77,94,0.4)",
    color: "#ff8c96",
    fontSize: 10,
    fontWeight: 700,
    padding: "2px 8px",
    borderRadius: 3,
    letterSpacing: 0.5,
  },
  body: { display: "flex", gap: 16, flexWrap: "wrap", alignItems: "flex-start" },
  canvas: {
    borderRadius: 4,
    border: "1px solid rgba(57,255,136,0.25)",
    cursor: "pointer",
    width: CANVAS_W,
    height: CANVAS_H,
    maxWidth: "100%",
    flexShrink: 0,
    alignSelf: "flex-start",
    boxShadow: "0 0 24px rgba(57,255,136,0.05) inset",
  },
  sidebar: { flex: 1, minWidth: 220, display: "flex", flexDirection: "column", gap: 10 },
  sidebarTitle: { fontSize: 11, color: "#5f9a7c", textTransform: "uppercase", letterSpacing: 1 },
  testPanel: {
    display: "flex",
    flexDirection: "column",
    gap: 8,
    padding: 10,
    borderRadius: 4,
    background: "rgba(57,255,136,0.03)",
    border: "1px solid rgba(57,255,136,0.15)",
  },
  testSelect: {
    background: "#050f0a",
    color: "#d7ffe8",
    border: "1px solid rgba(57,255,136,0.25)",
    borderRadius: 3,
    padding: "6px 8px",
    fontSize: 12,
    fontFamily: FONT_MONO,
  },
  keyHint: {
    fontSize: 10,
    color: "#5f9a7c",
    lineHeight: 1.4,
  },
  testRoomGrid: { display: "grid", gridTemplateColumns: "1fr 1fr", gap: 6 },
  testRoomBtn: {
    background: "rgba(57,255,136,0.06)",
    border: "1px solid rgba(57,255,136,0.2)",
    borderRadius: 3,
    color: "#d7ffe8",
    padding: "6px 4px",
    fontSize: 10,
    cursor: "pointer",
    textAlign: "center",
    fontFamily: FONT_MONO,
  },
  testClearBtn: {
    background: "rgba(255,77,94,0.10)",
    border: "1px solid rgba(255,77,94,0.35)",
    borderRadius: 3,
    color: "#ff8c96",
    padding: "6px 8px",
    fontSize: 11,
    cursor: "pointer",
    fontFamily: FONT_MONO,
  },
  testResetBtn: {
    background: "rgba(45,224,192,0.10)",
    border: "1px solid rgba(45,224,192,0.35)",
    borderRadius: 3,
    color: "#7ff0dc",
    padding: "6px 8px",
    fontSize: 11,
    cursor: "pointer",
    fontFamily: FONT_MONO,
  },
  testStressBtn: {
    background: "rgba(255,184,77,0.12)",
    border: "1px solid rgba(255,184,77,0.4)",
    borderRadius: 3,
    color: "#ffcf85",
    padding: "6px 8px",
    fontSize: 11,
    fontWeight: 700,
    cursor: "pointer",
    fontFamily: FONT_MONO,
  },
  testStatusOk: {
    fontSize: 10,
    color: "#39ff88",
    wordBreak: "break-word",
    marginTop: 2,
  },
  testStatusErr: {
    fontSize: 10,
    color: "#ff8c96",
    wordBreak: "break-word",
    marginTop: 2,
  },
  list: { display: "flex", flexDirection: "column", gap: 6, maxHeight: 200, overflowY: "auto" },
  listItem: {
    display: "flex",
    alignItems: "center",
    gap: 8,
    padding: "6px 8px",
    borderRadius: 3,
    border: "1px solid",
    background: "transparent",
    color: "#d7ffe8",
    cursor: "pointer",
    fontSize: 12,
    textAlign: "left",
    fontFamily: FONT_MONO,
  },
  miniDot: { width: 6, height: 6, borderRadius: "50%", flexShrink: 0 },
  listName: { flex: 1 },
  listZone: { color: "#5f9a7c", fontSize: 11 },
  empty: { fontSize: 12, color: "#5f9a7c", fontStyle: "italic" },
  panel: {
    marginTop: 4,
    padding: 12,
    borderRadius: 4,
    background: "rgba(57,255,136,0.03)",
    border: "1px solid rgba(57,255,136,0.15)",
  },
  panelHeader: { marginBottom: 8 },
  panelAlert: { display: "block", color: "#ff8c96", fontSize: 11, fontWeight: 700, marginBottom: 2, letterSpacing: 0.5 },
  panelName: { fontSize: 14, fontWeight: 700, color: "#d7ffe8" },
  panelRow: { display: "flex", justifyContent: "space-between", fontSize: 12, padding: "3px 0" },
  panelLabel: { color: "#5f9a7c" },
  panelValue: { color: "#d7ffe8" },
  motifText: {
    marginTop: 8,
    fontSize: 11,
    color: "#ff8c96",
    lineHeight: 1.4,
    borderTop: "1px solid rgba(57,255,136,0.15)",
    paddingTop: 8,
  },
  overlay: {
    position: "fixed",
    inset: 0,
    background: "rgba(0,3,1,0.82)",
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    zIndex: 1000,
    padding: 16,
  },
  overlayCard: {
    background: "#050f0a",
    border: "1px solid rgba(57,255,136,0.3)",
    borderRadius: 6,
    padding: 20,
    maxWidth: 600,
    width: "100%",
    boxShadow: "0 0 40px rgba(57,255,136,0.08)",
    fontFamily: FONT_MONO,
  },
  overlayHeader: { display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 14 },
  overlayTitle: {
    margin: 0,
    fontSize: 15,
    fontWeight: 700,
    color: "#39ff88",
    textTransform: "uppercase",
    letterSpacing: 1,
  },
  closeBtn: {
    background: "rgba(57,255,136,0.08)",
    border: "1px solid rgba(57,255,136,0.3)",
    borderRadius: 3,
    color: "#d7ffe8",
    padding: "6px 12px",
    fontSize: 11,
    cursor: "pointer",
    fontFamily: FONT_MONO,
  },
  roomCanvas: { width: "100%", height: "auto", borderRadius: 4, display: "block" },
  logsBtn: {
    background: "rgba(57,255,136,0.06)",
    border: "1px solid rgba(57,255,136,0.25)",
    borderRadius: 3,
    color: "#d7ffe8",
    padding: "4px 10px",
    fontSize: 11,
    cursor: "pointer",
    marginLeft: 4,
    fontFamily: FONT_MONO,
  },
  logsCard: {
    background: "#050f0a",
    border: "1px solid rgba(57,255,136,0.3)",
    borderRadius: 6,
    padding: 20,
    maxWidth: 520,
    width: "100%",
    maxHeight: "80vh",
    display: "flex",
    flexDirection: "column",
    fontFamily: FONT_MONO,
    boxShadow: "0 0 40px rgba(57,255,136,0.08)",
  },
  logsList: {
    display: "flex",
    flexDirection: "column",
    gap: 8,
    overflowY: "auto",
    paddingRight: 4,
  },
  logRow: {
    borderLeft: "3px solid",
    background: "rgba(57,255,136,0.03)",
    borderRadius: 3,
    padding: "8px 10px",
  },
  logRowTop: { display: "flex", justifyContent: "space-between", fontSize: 12, fontWeight: 700, color: "#d7ffe8" },
  logTime: { fontSize: 10, color: "#5f9a7c", fontWeight: 400 },
  logRowBottom: { display: "flex", gap: 6, fontSize: 11, color: "#5f9a7c", marginTop: 3 },
  logName: {},
  logMotif: { fontSize: 10, color: "#ff8c96", marginTop: 4, lineHeight: 1.3 },
  intrusionCard: {
    background: "#0f0508",
    border: "2px solid #ff4d5e",
    borderRadius: 6,
    padding: "28px 24px",
    maxWidth: 340,
    width: "100%",
    textAlign: "center",
    boxShadow: "0 0 48px rgba(255,77,94,0.3)",
    fontFamily: FONT_MONO,
  },
  intrusionIcon: { fontSize: 38, color: "#ff4d5e", marginBottom: 8 },
  intrusionTitle: {
    fontSize: 15,
    fontWeight: 800,
    color: "#ff8c96",
    letterSpacing: 1.5,
    marginBottom: 16,
  },
  intrusionBody: { textAlign: "left", marginBottom: 20 },
  intrusionBtn: {
    background: "#ff4d5e",
    border: "none",
    borderRadius: 3,
    color: "#0f0508",
    padding: "10px 20px",
    fontSize: 12,
    fontWeight: 700,
    cursor: "pointer",
    width: "100%",
    letterSpacing: 0.5,
    fontFamily: FONT_MONO,
  },
};