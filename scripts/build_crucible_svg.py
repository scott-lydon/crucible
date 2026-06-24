"""Hand-authored Crucible system overview SVG.

Layout: zones placed as a clockwise ring. Forward path runs around the
inner arc; long feedback edges route along the perimeter so they cross
nothing.

  9 o'clock  RED ZONE       (with Red Agent sub-loop + WB + HYB + Strategy Catalog)
  6 o'clock  PRODUCER ZONE  (3 adapters + Target Protocol)
 12 o'clock  SEALED ZONE    (Spec, 5 oracles, Aggregator)
  3 o'clock  MEASURE ZONE   (TRACE, DASH, CURVE, AUDIT, ART, HALT)
  5 o'clock  BLUE ZONE      (3 proposer feeds + Retrainer + Held-out validator)
"""
from __future__ import annotations
from textwrap import dedent
from base64 import b64encode
from pathlib import Path

W, H = 1700, 1280

# ---------- palette ----------
BG = "#0a0e1a"
TEXT = "#e2e8f0"
MUTED = "#94a3b8"
TITLE = "#cbd5e1"

# tier colors (non-foundational: muted)
TIER_COMPUTE   = ("#141d2f", "#475569")  # fill, stroke
TIER_STORAGE   = ("#1a1f29", "#64748b")
TIER_CONTROL   = ("#241818", "#7f3a3a")
TIER_KERNEL    = ("#152a26", "#1f6b5c")
TIER_OBS       = ("#1f2738", "#475569")
TIER_DATA      = ("#22192e", "#5b497a")

# foundational accent (only 8 nodes get this)
FND_STROKE = "#f59e0b"
FND_STROKE_W = 3
FND_GLOW = "#f59e0b"

# edge colors
EDGE_MAIN = "#e2e8f0"         # main forward path
EDGE_NORMAL = "#94a3b8"       # secondary data edges
EDGE_CTRL = "#e06a6a"         # halt control loop
EDGE_FB = "#6366f1"           # blue feedback (retrain)

# zone label colors
ZONE_RED = "#c0584f"
ZONE_PROD = "#94a3b8"
ZONE_SEAL = "#8b7fd4"
ZONE_MEAS = "#94a3b8"
ZONE_BLUE = "#6366f1"

# load logos
ICONS = {}
for name in ("anthropic", "scipy", "python", "yaml"):
    p = Path(f"/tmp/icons/{name}.svg")
    if p.exists():
        ICONS[name] = "data:image/svg+xml;base64," + b64encode(p.read_bytes()).decode()


def node(x, y, w, h, title, sub, tier, foundational=False, icon=None):
    """Render one node centered at (x, y) with given size."""
    fill, stroke = tier
    if foundational:
        stroke = FND_STROKE
        stroke_w = FND_STROKE_W
        filt = ' filter="url(#glow)"'
    else:
        stroke_w = 1
        filt = ""
    rx, ry = 8, 8
    nx, ny = x - w/2, y - h/2
    body = f'<rect x="{nx:.1f}" y="{ny:.1f}" width="{w}" height="{h}" rx="{rx}" ry="{ry}" fill="{fill}" stroke="{stroke}" stroke-width="{stroke_w}"{filt}/>'
    # title text
    title_y = y - h/2 + 18
    sub_y = title_y + 14
    icon_html = ""
    text_x = x
    if icon and icon in ICONS:
        icon_html = f'<image href="{ICONS[icon]}" x="{nx + 8:.1f}" y="{title_y - 11:.1f}" width="14" height="14"/>'
        text_x = x + 7  # shift label right to make space
    title_el = f'<text x="{text_x}" y="{title_y}" text-anchor="middle" font-family="Helvetica,Arial,sans-serif" font-size="12" font-weight="600" fill="{TEXT}">{title}</text>'
    sub_el = ""
    if sub:
        lines = sub.split("\n")
        for i, line in enumerate(lines):
            sub_el += f'<text x="{x}" y="{sub_y + i * 12}" text-anchor="middle" font-family="Helvetica,Arial,sans-serif" font-size="9" fill="{MUTED}">{line}</text>'
    return body + icon_html + title_el + sub_el


def zone(x, y, w, h, label, color):
    nx, ny = x - w/2, y - h/2
    return (
        f'<rect x="{nx}" y="{ny}" width="{w}" height="{h}" rx="14" ry="14" '
        f'fill="none" stroke="{color}" stroke-width="1.2" stroke-dasharray="6 4" opacity="0.55"/>'
        f'<text x="{nx + 14}" y="{ny + 20}" font-family="Helvetica,Arial,sans-serif" '
        f'font-size="13" font-weight="600" fill="{color}" opacity="0.85">{label}</text>'
    )


def arrow(x1, y1, x2, y2, *, color=EDGE_NORMAL, width=1.4, dashed=False, label=None, label_offset=(0,0), curve=None, marker="end"):
    """Draw an arrow. `curve` is an optional (cx, cy) midpoint for quadratic Bezier, or a list for cubic."""
    dash = ' stroke-dasharray="6 4"' if dashed else ""
    if curve is None:
        d = f"M {x1:.1f} {y1:.1f} L {x2:.1f} {y2:.1f}"
        mid_x, mid_y = (x1 + x2) / 2, (y1 + y2) / 2
    elif isinstance(curve, tuple):
        cx, cy = curve
        d = f"M {x1:.1f} {y1:.1f} Q {cx:.1f} {cy:.1f} {x2:.1f} {y2:.1f}"
        mid_x, mid_y = cx, cy
    else:
        # cubic [c1x, c1y, c2x, c2y]
        c1x, c1y, c2x, c2y = curve
        d = f"M {x1:.1f} {y1:.1f} C {c1x:.1f} {c1y:.1f}, {c2x:.1f} {c2y:.1f}, {x2:.1f} {y2:.1f}"
        mid_x, mid_y = (c1x + c2x) / 2, (c1y + c2y) / 2
    path = f'<path d="{d}" fill="none" stroke="{color}" stroke-width="{width}"{dash} marker-end="url(#arrowhead-{marker})"/>'
    lbl = ""
    if label:
        lx, ly = mid_x + label_offset[0], mid_y + label_offset[1]
        # background pill for legibility
        text_w = len(label) * 6 + 10
        lbl = (
            f'<rect x="{lx - text_w/2:.1f}" y="{ly - 9:.1f}" width="{text_w}" height="14" rx="4" '
            f'fill="{BG}" opacity="0.85"/>'
            f'<text x="{lx:.1f}" y="{ly + 2:.1f}" text-anchor="middle" font-family="Helvetica,Arial,sans-serif" '
            f'font-size="10" fill="{TEXT}">{label}</text>'
        )
    return path + lbl


# ============== NODE POSITIONS ==============
# (x, y, w, h, title, sub, tier, foundational, icon)
positions = {
    # RED ZONE (9 o'clock, left side)
    "WB":      (220, 410, 160, 50, "white-box mode", "scheme revealed", TIER_CONTROL, False, None),
    "HYB":     (430, 410, 160, 50, "hybrid fallback", "scipy.optimize", TIER_CONTROL, False, "scipy"),
    "REASON":  (220, 560, 150, 54, "Red Agent · reason", "why was I caught?", TIER_COMPUTE, True, "anthropic"),
    "PROPOSE": (385, 560, 150, 50, "propose change", "preserve intent", TIER_COMPUTE, False, None),
    "QUERY":   (540, 560, 150, 50, "query_target()", "score, iterate", TIER_COMPUTE, False, None),
    "CAT":     (220, 720, 160, 56, "Strategy Catalog", "persistent memory\nacross runs", TIER_DATA, True, None),
    # PRODUCER ZONE (6 o'clock, bottom-center)
    "AF":      (640, 1010, 145, 50, "fraud adapter", "LightGBM .lgb", TIER_STORAGE, False, "python"),
    "AC":      (800, 1010, 165, 50, "code-agent adapter", "Sonnet 4.6 endpoint", TIER_STORAGE, False, "anthropic"),
    "AR":      (960, 1010, 150, 50, "research adapter", "stub", TIER_STORAGE, False, None),
    "TGT":     (800, 880, 200, 60, "Target Protocol", "submit · query_target\nself_test", TIER_COMPUTE, True, None),
    # SEALED ZONE (12 o'clock, top)
    "SPEC":    (440, 220, 160, 54, "Sealed Spec", "YAML obligations", TIER_DATA, False, "yaml"),
    "O1":      (640, 120, 130, 50, "held-out tests", "1.0", TIER_KERNEL, False, None),
    "O2":      (775, 120, 140, 50, "metamorphic", "1.0", TIER_KERNEL, False, None),
    "O3":      (920, 120, 145, 50, "differential", "Haiku vs Sonnet · 1.0", TIER_KERNEL, False, "anthropic"),
    "O4":      (1070, 120, 145, 50, "property-fuzz", "1.0", TIER_KERNEL, False, None),
    "O5":      (1220, 120, 135, 50, "LLM judge", "Opus · 0.5", TIER_KERNEL, False, "anthropic"),
    "AGG":     (1370, 220, 165, 58, "Aggregator", "PASS-weight &#8805; 2.0\n&#8658; pass; else caught", TIER_CONTROL, True, None),
    # MEASURE ZONE (3 o'clock, right)
    "TRACE":   (1450, 410, 175, 50, "agent step traces", "+ every verdict", TIER_OBS, False, None),
    "DASH":    (1430, 560, 195, 60, "Dashboard", "undetected-hack rate\nval-vs-heldout gap", TIER_OBS, True, None),
    "CURVE":   (1450, 700, 175, 50, "Co-evolution curves", "ASR · detection", TIER_OBS, False, None),
    "AUDIT":   (1450, 800, 175, 50, "Audit trace", "1-click replay", TIER_OBS, False, None),
    "ART":     (1450, 900, 175, 52, "Artifacts", "corpus · leaderboard\nSR 11-7 report", TIER_DATA, False, None),
    "HALT":    (1430, 1020, 200, 58, "Halt-certification", "recall &lt; red line\n&#8658; refuse new runs", TIER_CONTROL, True, None),
    # BLUE ZONE (5-6 o'clock, bottom-right)
    "PF":      (1170, 1115, 140, 46, "new features", "", TIER_COMPUTE, False, None),
    "PS":      (1170, 1175, 175, 46, "adversarial samples", "", TIER_COMPUTE, False, None),
    "PE":      (1170, 1235, 165, 46, "specialist ensemble", "", TIER_COMPUTE, False, None),
    "RTR":     (1370, 1175, 175, 58, "Retrainer", "LightGBM.fit() OR\nagent_configs patch", TIER_COMPUTE, True, "python"),
    "HOV":     (1570, 1175, 180, 58, "Held-out validator", "fixed attack set\nnever seen by proposer", TIER_STORAGE, True, None),
}

# ============== ZONE BOUNDARIES ==============
zones = [
    ("Red side", 320, 595, 580, 470, ZONE_RED),
    ("Producer Zone · sandboxed, no producer path to verifier", 800, 950, 600, 240, ZONE_PROD),
    ("Sealed Verification Zone · no producer path in", 880, 175, 1080, 240, ZONE_SEAL),
    ("Measure · scoreboard + flight recorder", 1455, 720, 290, 750, ZONE_MEAS),
    ("Blue Loop · automated hardening", 1360, 1175, 460, 230, ZONE_BLUE),
]


# ============== EDGES (deliberately routed) ==============
edges = []
# --- RED inner loop ---
edges.append(arrow(295, 560, 310, 560, label=None))  # REASON -> PROPOSE
edges.append(arrow(460, 560, 465, 560, label=None))  # PROPOSE -> QUERY
edges.append(arrow(540, 535, 220, 535, curve=(380, 460), label="iterate on score", dashed=True))  # QUERY -> REASON arc above
# WB -> REASON (down)
edges.append(arrow(220, 435, 220, 533, dashed=True, label="augments prompt"))
# HYB -> QUERY (down-left to query top)
edges.append(arrow(430, 435, 540, 535, dashed=True, label="executes proposals", label_offset=(0,-6)))
# CAT -> REASON (up)
edges.append(arrow(220, 692, 220, 587, dashed=True, label="reuse tactics"))

# --- PRODUCER internal ---
edges.append(arrow(640, 985, 740, 910, label=None))  # AF -> TGT
edges.append(arrow(800, 985, 800, 910, label=None))  # AC -> TGT
edges.append(arrow(960, 985, 860, 910, label=None))  # AR -> TGT

# --- SEALED internal ---
# SPEC -> O1..O5
edges.append(arrow(520, 220, 640, 120, label="derives", label_offset=(0,-10)))
edges.append(arrow(520, 220, 770, 120))
edges.append(arrow(520, 220, 905, 120))
edges.append(arrow(520, 220, 1050, 120))
edges.append(arrow(520, 220, 1200, 120))
# O1..O5 -> AGG
edges.append(arrow(700, 145, 1290, 220))
edges.append(arrow(820, 145, 1290, 220))
edges.append(arrow(940, 145, 1290, 220))
edges.append(arrow(1095, 145, 1290, 220))
edges.append(arrow(1240, 145, 1290, 200))

# --- MEASURE internal ---
edges.append(arrow(1450, 435, 1430, 530, label=None))  # TRACE -> DASH
edges.append(arrow(1450, 435, 1450, 675, label=None))  # TRACE -> CURVE (right edge)
edges.append(arrow(1450, 435, 1500, 775, curve=(1620, 600)))  # TRACE -> AUDIT
edges.append(arrow(1430, 590, 1430, 990, label=None))  # DASH -> HALT
edges.append(arrow(1500, 590, 1500, 875, curve=(1640, 750), label=None))  # DASH -> ART
edges.append(arrow(1450, 725, 1450, 875, label=None))  # CURVE -> ART
edges.append(arrow(1450, 825, 1450, 875, label=None))  # AUDIT -> ART

# --- BLUE internal ---
edges.append(arrow(1240, 1115, 1283, 1165))  # PF -> RTR
edges.append(arrow(1258, 1175, 1283, 1175))  # PS -> RTR
edges.append(arrow(1252, 1235, 1290, 1195))  # PE -> RTR
edges.append(arrow(1458, 1175, 1480, 1175))  # RTR -> HOV

# --- CROSS-ZONE: MAIN FORWARD PATH ---
# QUERY (red) -> TGT (producer): down-right
edges.append(arrow(615, 585, 750, 850, color=EDGE_MAIN, width=2.2, label="submit / query"))
# TGT (producer) -> O1 (sealed, leftmost oracle) via center-up
edges.append(arrow(740, 850, 640, 145, color=EDGE_MAIN, width=2.2, curve=(580, 500), label="output (sealed from spec)", label_offset=(0,-10)))
# AGG (sealed) -> REASON (red): TOP perimeter arc
edges.append(arrow(1290, 200, 220, 533,
                   color=EDGE_MAIN, width=2.2,
                   curve=[1100, 40, 400, 40],
                   label="verdict + audit trace", label_offset=(0,-14)))

# --- CROSS-ZONE: MEMORY ---
# AGG -> CAT: TOP arc, slightly lower than verdict arc
edges.append(arrow(1290, 240, 300, 720,
                   curve=[1100, 0, 0, 200],
                   label="log undetected hacks", label_offset=(0,-12)))

# CAT -> PF/PS/PE: arc DOWN-RIGHT along bottom
edges.append(arrow(300, 740, 1100, 1115,
                   curve=[200, 1200, 600, 1280],
                   label="discovered tactics", label_offset=(0,12)))

# --- CROSS-ZONE: BLUE FEEDBACK ---
# HOV -> TGT: up-left arc (around BLUE zone top edge)
edges.append(arrow(1570, 1146, 800, 850,
                   color=EDGE_FB, width=1.8, dashed=True,
                   curve=[1450, 1060, 1000, 800],
                   label="retrain / patch", label_offset=(0,-6)))

# --- CROSS-ZONE: MEASURE FEEDS ---
# AGG -> TRACE: simple short down
edges.append(arrow(1370, 250, 1450, 385))

# --- CROSS-ZONE: HALT CONTROL ---
# HALT -> REASON: BOTTOM perimeter arc, below all other clusters
edges.append(arrow(1330, 1049, 200, 590,
                   color=EDGE_CTRL, width=1.7, dashed=True,
                   curve=[1100, 1260, 100, 1260],
                   label="blocks new POST /runs", label_offset=(0,18)))


# ============== ASSEMBLE SVG ==============
svg_parts = []
svg_parts.append(f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" role="img" aria-label="Crucible system overview">')
svg_parts.append('  <title>Crucible · combined system overview</title>')
svg_parts.append('  <defs>')
svg_parts.append(f'    <filter id="glow" x="-20%" y="-20%" width="140%" height="140%">')
svg_parts.append(f'      <feGaussianBlur stdDeviation="2.5" result="b"/>')
svg_parts.append(f'      <feFlood flood-color="{FND_GLOW}" flood-opacity="0.55"/>')
svg_parts.append(f'      <feComposite in2="b" operator="in" result="g"/>')
svg_parts.append(f'      <feMerge><feMergeNode in="g"/><feMergeNode in="SourceGraphic"/></feMerge>')
svg_parts.append(f'    </filter>')
svg_parts.append(f'    <marker id="arrowhead-end" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">')
svg_parts.append(f'      <path d="M 0 0 L 10 5 L 0 10 z" fill="{MUTED}"/>')
svg_parts.append(f'    </marker>')
svg_parts.append('  </defs>')
svg_parts.append(f'  <rect width="{W}" height="{H}" fill="{BG}"/>')
# title
svg_parts.append(f'  <text x="{W/2}" y="34" text-anchor="middle" font-family="Helvetica,Arial,sans-serif" font-size="18" font-weight="600" fill="{TITLE}">Crucible · combined system overview</text>')
svg_parts.append(f'  <text x="{W/2}" y="55" text-anchor="middle" font-family="Helvetica,Arial,sans-serif" font-size="12" fill="{MUTED}">26 components, clockwise loop topology, foundational nodes carry amber accent</text>')
# zones (draw first so nodes overlay them)
for label, x, y, w, h, color in zones:
    svg_parts.append("  " + zone(x, y, w, h, label, color))
# edges (drawn behind nodes)
for e in edges:
    svg_parts.append("  " + e)
# nodes
for key, (x, y, w, h, title, sub, tier, fnd, icon) in positions.items():
    svg_parts.append("  " + node(x, y, w, h, title, sub, tier, foundational=fnd, icon=icon))
svg_parts.append('</svg>')

out = "\n".join(svg_parts)
Path("/tmp/crucible-overview-handauthored.svg").write_text(out)
print(f"wrote {len(out)} bytes")
