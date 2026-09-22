"use client";

import { useEffect, useRef, useState, useCallback } from "react";

// ---------------------------------------------------------------------------
// Configuration — calée sur plan_vaisseau_v3_clean.png
// Toutes les coordonnées sont en mètres, converties en pixels via SCALE.
// ---------------------------------------------------------------------------
const WS_URL = "ws://localhost:8000/ws";
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
    border: "#e0524a", fill: "rgba(150,40,40,0.30)", restricted: true, lines: ["RÉACTEUR"], vertical: true },
  { name: "Quartiers des équipes", x1: 3.45, y1: 1.28, x2: 5.20, y2: 3.30,
    border: "#2bb37a", fill: "rgba(10,90,65,0.30)", lines: ["QUARTIERS", "DES ÉQUIPES"] },
  { name: "Cafétéria", x1: 3.45, y1: 4.85, x2: 5.20, y2: 6.85,
    border: "#2bb37a", fill: "rgba(10,90,65,0.30)", lines: ["CAFÉTÉRIA"] },
  { name: "Laboratoire", x1: 6.83, y1: 1.28, x2: 8.57, y2: 3.30,
    border: "#e08a3c", fill: "rgba(120,60,20,0.30)", lines: ["LABORATOIRE"] },
  { name: "Infirmerie", x1: 6.83, y1: 4.85, x2: 8.57, y2: 6.85,
    border: "#e08a3c", fill: "rgba(120,60,20,0.30)", lines: ["INFIRMERIE"] },
  { name: "Salle Serveur", x1: 10.20, y1: 1.28, x2: 11.52, y2: 3.30,
    border: "#e08a3c", fill: "rgba(120,60,20,0.30)", restricted: true, lines: ["SALLE", "SERVEUR"] },
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
  { x1: 10.65, y1: 3.30, x2: 11.08, y2: 3.55 }, // Salle Serveur
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
  { id: "A1", x: 2, y: 1.4 },
  { id: "A2", x: 13, y: 1.4 },
  { id: "A3", x: 13, y: 6.9 },
  { id: "A4", x: 2, y: 6.9 },
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
  alert: boolean;   // true si présence non autorisée en zone restreinte
}

type ConnState = "connecting" | "connected" | "disconnected";

// ---------------------------------------------------------------------------
// Composant principal
// ---------------------------------------------------------------------------
export default function BLEPassengerTracker() {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const [people, setPeople] = useState<Passenger[]>([]);
  const [selected, setSelected] = useState<Passenger | null>(null);
  const [conn, setConn] = useState<ConnState>("connecting");
  const wsRef = useRef<WebSocket | null>(null);

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

    ctx.fillStyle = "#f4f6fa";
    ctx.font = "bold 12px sans-serif";
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
    ctx.fillStyle = "#c7cdd9";
    ctx.strokeStyle = "#6b7280";
    ctx.lineWidth = 1;
    ctx.fillRect(x, y, w, h);
    ctx.strokeRect(x, y, w, h);
    ctx.fillStyle = "#3aa0ff";
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

    // Fond spatial + grille
    ctx.fillStyle = "#05070d";
    ctx.fillRect(0, 0, CANVAS_W, CANVAS_H);
    ctx.strokeStyle = "rgba(255,255,255,0.035)";
    ctx.lineWidth = 1;
    for (let x = 0; x <= CANVAS_W; x += SCALE / 2) {
      ctx.beginPath(); ctx.moveTo(x, 0); ctx.lineTo(x, CANVAS_H); ctx.stroke();
    }
    for (let y = 0; y <= CANVAS_H; y += SCALE / 2) {
      ctx.beginPath(); ctx.moveTo(0, y); ctx.lineTo(CANVAS_W, y); ctx.stroke();
    }

    // Contour de la coque
    buildHullPath(ctx);
    ctx.strokeStyle = "rgba(140,160,200,0.45)";
    ctx.lineWidth = 1.5;
    ctx.stroke();

    // Coursives (horizontale + segments verticaux)
    const drawCorridorRect = (c: { x1: number; y1: number; x2: number; y2: number }) => {
      const x = c.x1 * SCALE, y = c.y1 * SCALE;
      const w = (c.x2 - c.x1) * SCALE, h = (c.y2 - c.y1) * SCALE;
      ctx.fillStyle = "#0b1730";
      ctx.fillRect(x, y, w, h);
      ctx.strokeStyle = "#2f8fe0";
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
    ctx.shadowColor = "#e0524a";
    ctx.shadowBlur = 10;
    ctx.fillStyle = "rgba(150,40,40,0.35)";
    ctx.fill();
    ctx.restore();
    ctx.strokeStyle = "#e0524a";
    ctx.lineWidth = 2;
    ctx.stroke();
    ctx.fillStyle = "#f4f6fa";
    ctx.font = "bold 11px sans-serif";
    ctx.textAlign = "left";
    ctx.fillText("POSTE DE", PILOTAGE.x1 * SCALE + 10, (PILOTAGE.y1 + PILOTAGE.y2) / 2 * SCALE - 4);
    ctx.fillText("PILOTAGE", PILOTAGE.x1 * SCALE + 10, (PILOTAGE.y1 + PILOTAGE.y2) / 2 * SCALE + 10);

    // Sas
    DOORS.forEach((d) => drawDoor(ctx, d));

    // Ancres BLE
    for (const a of ANCHORS) {
      ctx.fillStyle = "#8892a6";
      ctx.beginPath();
      ctx.arc(a.x * SCALE, a.y * SCALE, 4, 0, Math.PI * 2);
      ctx.fill();
      ctx.font = "10px sans-serif";
      ctx.fillText(a.id, a.x * SCALE + 6, a.y * SCALE - 6);
    }

    // Passagers
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

      ctx.fillStyle = "#e6e9f0";
      ctx.font = "11px sans-serif";
      ctx.fillText(p.name, px + 12, py - 8);
    }
  }, [people, buildHullPath]);

  useEffect(() => {
    draw();
  }, [draw]);

  // --- Clic sur la carte : sélectionne le passager le plus proche -------
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
    setSelected(minDist < 20 ? closest : null);
  }

  const alertCount = people.filter((p) => p.alert).length;

  return (
    <div style={styles.container}>
      <div style={styles.header}>
        <h3 style={styles.title}>BLE Passenger Tracker</h3>
        <div style={styles.statusRow}>
          <span style={{ ...styles.dot, background: connColor(conn) }} />
          <span style={styles.statusText}>{connLabel(conn)}</span>
          {alertCount > 0 && (
            <span style={styles.alertBadge}>{alertCount} alerte{alertCount > 1 ? "s" : ""}</span>
          )}
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
              <PanelRow label="Position" value={`x: ${selected.x.toFixed(1)}m · y: ${selected.y.toFixed(1)}m`} />
            </div>
          )}
        </div>
      </div>
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
const styles: Record<string, React.CSSProperties> = {
  container: {
    background: "#0d1420",
    border: "1px solid rgba(255,255,255,0.08)",
    borderRadius: 12,
    padding: 16,
    color: "#e6e9f0",
    fontFamily: "sans-serif",
  },
  header: { display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 12 },
  title: { margin: 0, fontSize: 16, fontWeight: 600 },
  statusRow: { display: "flex", alignItems: "center", gap: 8 },
  dot: { width: 8, height: 8, borderRadius: "50%" },
  statusText: { fontSize: 12, color: "#9aa3b5" },
  alertBadge: {
    background: "rgba(255,59,59,0.15)",
    color: "#ff6b6b",
    fontSize: 11,
    fontWeight: 600,
    padding: "2px 8px",
    borderRadius: 999,
  },
  body: { display: "flex", gap: 16, flexWrap: "wrap" },
  canvas: { borderRadius: 8, border: "1px solid rgba(255,255,255,0.08)", cursor: "pointer" },
  sidebar: { flex: 1, minWidth: 220, display: "flex", flexDirection: "column", gap: 10 },
  sidebarTitle: { fontSize: 12, color: "#9aa3b5", textTransform: "uppercase", letterSpacing: 0.5 },
  list: { display: "flex", flexDirection: "column", gap: 6, maxHeight: 200, overflowY: "auto" },
  listItem: {
    display: "flex",
    alignItems: "center",
    gap: 8,
    padding: "6px 8px",
    borderRadius: 6,
    border: "1px solid",
    background: "transparent",
    color: "#e6e9f0",
    cursor: "pointer",
    fontSize: 12,
    textAlign: "left",
  },
  miniDot: { width: 6, height: 6, borderRadius: "50%", flexShrink: 0 },
  listName: { flex: 1 },
  listZone: { color: "#9aa3b5", fontSize: 11 },
  empty: { fontSize: 12, color: "#9aa3b5", fontStyle: "italic" },
  panel: {
    marginTop: 4,
    padding: 12,
    borderRadius: 8,
    background: "rgba(255,255,255,0.03)",
    border: "1px solid rgba(255,255,255,0.08)",
  },
  panelHeader: { marginBottom: 8 },
  panelAlert: { display: "block", color: "#ff6b6b", fontSize: 11, fontWeight: 700, marginBottom: 2 },
  panelName: { fontSize: 14, fontWeight: 600 },
  panelRow: { display: "flex", justifyContent: "space-between", fontSize: 12, padding: "3px 0" },
  panelLabel: { color: "#9aa3b5" },
  panelValue: { color: "#e6e9f0" },
};
