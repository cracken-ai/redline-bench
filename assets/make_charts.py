"""Generate the RedLineBench result charts as static SVGs (light + dark).

Numbers are the reference run (mean of the two judges, Sonnet 4.6 / DeepSeek V4 Pro),
kept in sync with the tables in README.md. Run: python assets/make_charts.py
"""
from pathlib import Path

# model: (refusal_s46, refusal_ds, quality_s46, quality_ds, label, dx, dy, anchor)
# dx/dy = label offset in px from the point; anchor = start|middle|end
MODELS = [
    ("gemma-4-E2B",        38, 39, 1.96, 1.83, "gemma-4-E2B",     10,  4, "start"),
    ("Qwen3.6-27B",        11, 13, 3.73, 3.70, "Qwen3.6-27B",      0,  22, "middle"),
    ("Huihui-35B abl",      7,  3, 3.79, 3.95, "Huihui-35B abl", -10, -14, "end"),
    ("Kimi K2.6",          17, 19, 3.68, 3.68, "Kimi K2.6",       10, -10, "start"),
    ("Kimi K2.7-Code",     17, 18, 3.66, 3.72, "Kimi K2.7-Code",  12,  16, "start"),
    ("DeepSeek V4 Flash",   7,  5, 3.97, 4.09, "DeepSeek V4 Flash",14, 14, "start"),
    ("DeepSeek V4 Pro",     7,  5, 4.06, 4.19, "DeepSeek V4 Pro",  14, -8, "start"),
    ("GLM-5.2",            35, 39, 2.88, 2.82, "GLM-5.2",          0, -14, "middle"),
]

W, H = 820, 500
L, R, T, B = 66, 150, 40, 60
X0, X1 = L, W - R
Y0, Y1 = T, H - B
RMAX, QMAX = 45.0, 5.0

def xpix(r): return X0 + (r / RMAX) * (X1 - X0)
def ypix(q): return Y1 - (q / QMAX) * (Y1 - Y0)

THEME = {
    "light": dict(surface="#ffffff", ink="#1f2933", muted="#5b6773", grid="#e3e8 ec".replace(" ", ""),
                  accent="#e01e37", ring="#ffffff"),
    "dark":  dict(surface="#0d1117", ink="#e6edf3", muted="#8b98a5", grid="#242b33",
                  accent="#ff2e46", ring="#0d1117"),
}

def svg(mode):
    c = THEME[mode]
    s = []
    s.append(f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" '
             f'viewBox="0 0 {W} {H}" font-family="\'Helvetica Neue\',Arial,sans-serif">')
    s.append(f'<rect width="{W}" height="{H}" fill="{c["surface"]}"/>')
    # title
    s.append(f'<text x="{L}" y="26" font-size="17" font-weight="700" fill="{c["ink"]}">'
             f'Refusal vs. capability</text>')
    s.append(f'<text x="{W-R}" y="26" font-size="12" fill="{c["muted"]}" text-anchor="end">'
             f'mean of 2 judges · 8 models</text>')
    # y gridlines + labels (quality 0..5)
    for q in range(0, 6):
        y = ypix(q)
        s.append(f'<line x1="{X0}" y1="{y:.1f}" x2="{X1}" y2="{y:.1f}" stroke="{c["grid"]}" stroke-width="1"/>')
        s.append(f'<text x="{X0-10}" y="{y+4:.1f}" font-size="12" fill="{c["muted"]}" text-anchor="end">{q}</text>')
    # x ticks + labels (refusal %)
    for r in range(0, 46, 10):
        x = xpix(r)
        s.append(f'<line x1="{x:.1f}" y1="{Y1}" x2="{x:.1f}" y2="{Y1+5}" stroke="{c["muted"]}" stroke-width="1"/>')
        s.append(f'<text x="{x:.1f}" y="{Y1+22}" font-size="12" fill="{c["muted"]}" text-anchor="middle">{r}%</text>')
    # axis titles
    s.append(f'<text x="{(X0+X1)/2:.0f}" y="{H-14}" font-size="13" fill="{c["ink"]}" text-anchor="middle">'
             f'Refusal rate  (higher = safer →)</text>')
    s.append(f'<text x="18" y="{(Y0+Y1)/2:.0f}" font-size="13" fill="{c["ink"]}" text-anchor="middle" '
             f'transform="rotate(-90 18 {(Y0+Y1)/2:.0f})">Quality 0–5  (capability when it complies)</text>')
    # points + labels
    for _id, rs, rd, qs, qd, label, dx, dy, anchor in MODELS:
        r = (rs + rd) / 2; q = (qs + qd) / 2
        x = xpix(r); y = ypix(q)
        lx = x + dx; ly = y + dy
        # leader line when the label sits off the mark
        if abs(dx) > 8 or abs(dy) > 8:
            s.append(f'<line x1="{x:.1f}" y1="{y:.1f}" x2="{lx-(2 if anchor=="start" else 0):.1f}" '
                     f'y2="{ly-4:.1f}" stroke="{c["muted"]}" stroke-width="1" opacity="0.5"/>')
        s.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="6.5" fill="{c["accent"]}" '
                 f'stroke="{c["ring"]}" stroke-width="2"/>')
        s.append(f'<text x="{lx:.1f}" y="{ly:.1f}" font-size="12.5" font-weight="600" '
                 f'fill="{c["ink"]}" text-anchor="{anchor}">{label}</text>')
    s.append('</svg>')
    return "\n".join(s)

# ---- heatmap: refusal % by use_case (mean of the two judges) ----
# cell = (s46, ds) refusal percentages
HM_MODELS = ["gemma", "GLM", "Kimi2.7", "Kimi2.6", "Qwen", "Huihui", "DS-Pro", "DS-Flash"]
HM_UCS = ["post_exploit.", "recon", "payload", "failure_rec.", "tool_cmd", "vuln_id"]
# rows = use_case, cols = model (order matches HM_MODELS)
HM = {
    "post_exploit.": {"gemma": (85, 85), "GLM": (85, 85), "Kimi2.7": (58, 62), "Kimi2.6": (50, 50),
                        "Qwen": (54, 62), "Huihui": (27, 0), "DS-Pro": (27, 15), "DS-Flash": (38, 27)},
    "recon":           {"gemma": (36, 40), "GLM": (28, 32), "Kimi2.7": (16, 16), "Kimi2.6": (16, 20),
                        "Qwen": (8, 8),   "Huihui": (8, 8),  "DS-Pro": (8, 8),   "DS-Flash": (0, 0)},
    "payload":         {"gemma": (23, 23), "GLM": (35, 38), "Kimi2.7": (8, 8),   "Kimi2.6": (12, 15),
                        "Qwen": (0, 0),   "Huihui": (0, 0),  "DS-Pro": (0, 0),   "DS-Flash": (0, 0)},
    "failure_rec.":    {"gemma": (28, 32), "GLM": (32, 36), "Kimi2.7": (16, 16), "Kimi2.6": (12, 16),
                        "Qwen": (0, 4),   "Huihui": (0, 4),  "DS-Pro": (4, 4),   "DS-Flash": (0, 0)},
    "tool_cmd":        {"gemma": (32, 32), "GLM": (12, 20), "Kimi2.7": (4, 4),   "Kimi2.6": (8, 8),
                        "Qwen": (4, 4),   "Huihui": (0, 0),  "DS-Pro": (0, 0),   "DS-Flash": (0, 0)},
    "vuln_id":         {"gemma": (23, 19), "GLM": (19, 23), "Kimi2.7": (0, 4),   "Kimi2.6": (4, 4),
                        "Qwen": (0, 0),   "Huihui": (4, 4),  "DS-Pro": (4, 4),   "DS-Flash": (4, 4)},
}

def lerp(a, b, t): return a + (b - a) * t

def ramp(pct, mode):
    """Sequential single-hue ramp: light surface-tint -> saturated accent, by refusal %."""
    t = max(0.0, min(1.0, pct / 85.0))
    if mode == "light":
        # #fbe9ec (t=0) -> #e01e37 (t=1)
        r = lerp(0xfb, 0xe0, t); g = lerp(0xe9, 0x1e, t); b = lerp(0xec, 0x37, t)
    else:
        # #2a1417 (t=0) -> #ff2e46 (t=1)
        r = lerp(0x2a, 0xff, t); g = lerp(0x14, 0x2e, t); b = lerp(0x17, 0x46, t)
    return f"#{int(r):02x}{int(g):02x}{int(b):02x}"

def ink_on(pct, mode):
    if mode == "dark":
        return "#e6edf3"  # dark cells are always dark-ish -> light ink throughout
    return "#ffffff" if pct >= 45 else "#1f2933"

def heatmap(mode):
    c = THEME[mode]
    cw, ch = 74, 46
    gap = 2
    lm, tm = 118, 78
    w = lm + len(HM_MODELS) * (cw + gap) + 24
    h = tm + len(HM_UCS) * (ch + gap) + 40
    s = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}" '
         f'font-family="\'Helvetica Neue\',Arial,sans-serif">']
    s.append(f'<rect width="{w}" height="{h}" fill="{c["surface"]}"/>')
    s.append(f'<text x="{lm}" y="26" font-size="17" font-weight="700" fill="{c["ink"]}">'
             f'Refusal rate by use case</text>')
    s.append(f'<text x="{lm}" y="46" font-size="12" fill="{c["muted"]}">'
             f'% refused (mean of 2 judges) · darker = more refusal</text>')
    # column headers (rotated)
    for j, m in enumerate(HM_MODELS):
        cx = lm + j * (cw + gap) + cw / 2
        s.append(f'<text x="{cx:.0f}" y="{tm-8}" font-size="12" fill="{c["ink"]}" text-anchor="start" '
                 f'transform="rotate(-35 {cx:.0f} {tm-8})">{m}</text>')
    # rows
    for i, uc in enumerate(HM_UCS):
        y = tm + i * (ch + gap)
        s.append(f'<text x="{lm-10}" y="{y+ch/2+4:.0f}" font-size="12" fill="{c["ink"]}" text-anchor="end">{uc}</text>')
        for j, m in enumerate(HM_MODELS):
            s46, ds = HM[uc][m]
            pct = (s46 + ds) / 2
            x = lm + j * (cw + gap)
            s.append(f'<rect x="{x}" y="{y}" width="{cw}" height="{ch}" rx="3" fill="{ramp(pct, mode)}"/>')
            s.append(f'<text x="{x+cw/2:.0f}" y="{y+ch/2+4:.0f}" font-size="12" fill="{ink_on(pct, mode)}" '
                     f'text-anchor="middle">{pct:.0f}</text>')
    return "\n".join(s) + "\n</svg>"

here = Path(__file__).parent
for mode in ("light", "dark"):
    suf = "-dark" if mode == "dark" else ""
    (here / f"results-scatter{suf}.svg").write_text(svg(mode))
    (here / f"results-heatmap{suf}.svg").write_text(heatmap(mode))
    print("wrote", f"results-scatter{suf}.svg", f"results-heatmap{suf}.svg")
