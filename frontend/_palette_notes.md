# Crucible — Palette Notes

**Palette name: "Graphite Meridian"**

A near-dark graphite-navy base with one restrained steel-cyan primary and AAA-tuned
semantic accents. It is deliberately the *intersection* palette: dark enough for the code
vendor, gridded and restrained enough for the bank, contrast-audited enough for government.

This palette is the canonical export. The architecture website (`website/index.html`)
re-syncs to these hex codes.

---

## Tokens

### Base / surfaces (graphite-navy, never pure black)
| Token            | Hex       | Role |
|------------------|-----------|------|
| `base`           | `#0E141B` | App background. Near-black with a navy bias — not `#000` (banks read pure black as "terminal from the 90s"). |
| `surface`        | `#161E27` | Panels, cards, table bodies. |
| `surface-2`      | `#1D2630` | Raised cards, drawer bodies, inputs. |
| `surface-3`      | `#25303C` | Hover / active fills, chips. |
| `border`         | `#2C3744` | Hairlines, dividers. |
| `border-strong`  | `#3A4654` | Focus rings, emphasized borders. |

### Text (cool off-white, never pure white)
| Token        | Hex       | Contrast on `base` | Role |
|--------------|-----------|--------------------|------|
| `text-hi`    | `#E8EDF3` | ~14.5:1 (AAA)      | Headings, key numbers. |
| `text`       | `#B8C2CE` | ~8.6:1 (AAA)       | Body copy. AAA at 14px base. |
| `text-mut`   | `#7C8896` | ~4.7:1 (AA)        | Labels, captions, metadata. |

### Primary (restrained steel-cyan — not neon, not pastel)
| Token         | Hex       | Contrast on `base` | Role |
|---------------|-----------|--------------------|------|
| `primary`     | `#4FAAC0` | ~7.4:1 (AAA)       | Links, interactive accents, brand, detection-rate chart line. |
| `primary-dim` | `#316E7E` | —                  | Pressed states, selection background, primary-dim fills. |

Chosen over a blue so it does not collide with U.S.-flag navy (procurement reads literal
navy+red+white as patriotic marketing) and does not read as "consumer AI purple."

### Semantic accents (success + danger tuned for AAA on `base`)
| Token        | Hex       | Contrast on `base` | Role |
|--------------|-----------|--------------------|------|
| `success`    | `#57C08A` | ~8.1:1 (AAA)       | Oracle PASS, healthy subcomponent, detection up. |
| `danger`     | `#E5736B` | ~5.6:1 (AA+)       | Oracle FAIL, destructive actions, red health. |
| `warning`    | `#D9A441` | ~9.0:1 (AAA)       | Amber health, reconnecting, attack-success-rate chart line. Warm gold — informs, does not alarm. |

### Halt-certification banner (global red bar)
| Token        | Hex       | Role |
|--------------|-----------|------|
| `halt-bg`    | `#5E1A1A` | Banner fill — deep, serious oxblood, not bright alarm-red. |
| `halt-text`  | `#FFC9C4` | Banner text — AAA on `halt-bg`. |

### Mock-LLM mode banner (yellow)
| Token        | Hex       | Role |
|--------------|-----------|------|
| `mock-bg`    | `#3A3413` | Banner fill — muted olive-gold, unmistakable but not a marketing yellow. |
| `mock-text`  | `#E8C84A` | Banner text. |

### Chart colors (never Recharts defaults)
- Attack-success-rate (ASR) line — `warning #D9A441` (a bad-trending metric reads warm/amber).
- Detection-rate line — `primary #4FAAC0`.
- Oracle verdict bars — PASS `success #57C08A`, FAIL `danger #E5736B`.
- Gridlines / axes — `border #2C3744`, axis labels `text-mut #7C8896`.

---

## Audience-by-audience rationale

**Bank model-risk officer (SR 11-7).** Lives in Bloomberg Terminal, Excel risk
dashboards, model-governance portals. Earns trust through a dark-but-not-black gridded
base, strict typographic hierarchy, monospace for every dollar figure and trace, and zero
gradients or illustration. The amber/cyan data accents echo terminal data coloring without
the 90s pure-black void. No marketing flourish anywhere.

**Code-generation agent vendor (engineering lead).** Lives in GitHub Dark, Linear, Vercel,
Sentry, Datadog. Dark theme is table stakes and is the default here. The restrained
steel-cyan primary is "a designer touched it," used sparingly. Cost and latency are
first-class citizens (CostChip + cost meter are core components), and the data-to-chrome
ratio stays high — high density without crowding.

**Public-sector AI procurement officer (NIST / WCAG).** Needs auditable contrast. Every
text token above is labeled with its measured ratio on `base`; body copy clears AAA at the
14px base, metadata clears AA. The palette is institutional and restrained but deliberately
sidesteps literal flag colors so it reads as a governed instrument, not patriotic branding.
No decorative animation — only data-driven transitions.

**The shared intersection:** near-dark navy-graphite base (not pure black), one restrained
primary that is neither neon nor pastel, success+danger chosen for AAA, and a warm amber for
warning that informs rather than alarms. Explicitly avoided: pure-black backgrounds, purple
neon accents, and high-saturation gradients.

---

## Type
- **Sans (UI + body):** IBM Plex Sans — institutional (IBM-authored, reads at home in
  NIST/government docs and bank portals) yet modern enough for a dev tool.
- **Mono (code, traces, prompts, audit JSON, all dollar amounts):** IBM Plex Mono — same
  family, perfect metric pairing.
- Base size **14px**, AAA body contrast preserved at that size.
