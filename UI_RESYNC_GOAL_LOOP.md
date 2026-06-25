# UI Re-sync Goal Loop — converge live frontend to the latest Claude Design export

**Source of new design:** `~/Downloads/GitHub Crucible Repository-3.zip` (exported 2026-06-24 20:53)
**Target (live UI):** `frontend/*.dc.html` (served statically; `index.html` meta-refreshes to the entry page; `live.js` injects real backend data via `data-live*` hooks)
**Authoritative rules:** CLAUDE DESIGN FIDELITY (design is source of truth, copy verbatim), NO MOCK DATA (no stub/fabricated data on screen), and `REMOVED_UI.md` (2026-06-24 out-of-spec removals).

This loop drives the live frontend to match the new export **without** re-introducing
mock data or stripping the real-backend wiring. Work top to bottom; check items as
each is verified.

---

## Checklist

- [x] **1. Create a diff for the old and new UI from the Claude Design zip.** (see [Diff](#diff) below; both live-vs-new and prev-export-vs-new)
- [x] **2. Create the remainder of the checklist by including everything from the diff to change.** (items below)
- [x] **3. RECONCILE FIRST (was blocking) — RESOLVED 2026-06-24.** The zip is a fresh Claude Design re-export, not a hand-trimmed cleanup: it re-stubs already-wired pages and, vs the prior export `(2).zip`, deleted 7 slices and renumbered the rest while keeping coevolution + leaderboard. User decisions:
  - [x] coevolution-curves (new slice-05): **SKIP** (no backend; C6 already removed it by deletion).
  - [x] leaderboard-export (new slice-07): **SKIP** (no backend; C10 already removed it by deletion).
  - [x] re-expanded no-backend sections (dashboard curves+histogram+replays, blue-patch approval, halt history/blocked/lift, sr-report static sections, whitebox per-family recall): **SKIP** (would put fabricated numbers on screen — NO MOCK DATA).
  - [x] deleted wired pages (health `/health` US-8, admin-debug `/admin/overrides`, workspace-policy `/policy`, spec-history `/specs/history`): **KEEP** (wired + in-spec).

### Outcome of applying the decisions

The live tree **already matches the reconciled intent**, so no page is overwritten:

- [x] **4. Stretch re-adds NOT applied.** Live already lacks `slice-09-coevolution` and `slice-13-leaderboard` (removed under C6/C10). No file added. verify: `ls frontend | grep -E 'coevolution|leaderboard'` → empty.
- [x] **5. Wired in-spec pages KEPT.** Live retains `slice-11-health`, `slice-12-admin-debug`, `slice-15-workspace-policy`, `slice-16-spec-history` with their `data-live*` wiring. Nothing deleted.
- [x] **6. Re-stubbed page bodies NOT overwritten.** Every zip-3 page reintroduces stub/mock data and dead `data-stub="link:TBD"` navs and drops the live `data-live*` hooks (export ships zero). Copying any of them would regress live to mock data + dead links and break `live.js` injection. So Run Launcher / strategy-catalog / whitebox / blue-patch / dashboard / halt / sr-report / Design System are left as the already-wired live versions. verify: `grep -rl data-live frontend/*.dc.html` still lists the 10 wired pages.
- [x] **7. Identify diff that was not updated. Update it.** Every item in the [Diff](#diff) was classified: each is either a stretch re-add (SKIP), a mock-data re-expansion (SKIP), a wired-page deletion (KEEP), or a re-stub of a wired page (do not overwrite). None warrant a live change under the decisions. Net live UI delta = **zero structural changes**; live is already the correct convergence target. No `index.html` / `live.js` / Canvas remap needed (no filenames changed).

### Optional follow-up (not applied — flagged for the user)

- [ ] **Cosmetic de-demo:** zip-3 replaces the hardcoded demo tenant `acme-fraud` with a neutral label and rebrands "operator dashboard" → "platform" copy in the Design System. These are the only non-mock refinements in the export. Apply only if wanted; they are entangled with the stub reintroductions, so they need surgical cherry-picking (change the label, do NOT pull the fabricated `142 runs` / `0.92 recall` / dead links). Low value; left to user.

---

## Slice mapping (new export ↔ live)

| NEW (zip-3, canonical)            | OLD (live frontend)              | Relationship |
|-----------------------------------|----------------------------------|--------------|
| `Run Launcher.dc.html`            | `slice-01-run-launcher.dc.html`  | renamed; entry point |
| `slice-01-strategy-catalog`       | `slice-06-strategy-catalog`      | renumbered; section-identical |
| `slice-02-whitebox-selftest`      | `slice-10-whitebox-selftest`     | renumbered; section-identical |
| `slice-03-blue-patch-review`      | `slice-07-blue-patch-review`     | renumbered; **content re-expanded** |
| `slice-04-honest-dashboard`       | `slice-04-dashboard`             | renamed; **content re-expanded** |
| `slice-05-coevolution-curves`     | *(none — was removed slice-09)*  | **RE-ADDED stretch (no backend)** |
| `slice-06-halt-certification`     | `slice-08-halt-certification`    | renumbered; **content re-expanded** |
| `slice-07-leaderboard-export`     | *(none — was removed slice-13)*  | **RE-ADDED stretch (no backend)** |
| `slice-08-sr-117-report`          | `slice-14-sr-117-report`         | renumbered; **content re-expanded** |
| `Canvas.dc.html`                  | `Canvas.dc.html`                 | tile set changed |
| `Crucible Design System.dc.html`  | `Crucible Design System.dc.html` | minor; safe verbatim |
| *(deleted)*                       | `slice-11-health` (wired)        | dropped by design |
| *(deleted)*                       | `slice-12-admin-debug` (wired)   | dropped by design |
| *(deleted)*                       | `slice-15-workspace-policy` (wired) | dropped by design |
| *(deleted)*                       | `slice-16-spec-history` (wired)  | dropped by design |

<a name="diff"></a>
## Diff

### Design-to-design (prev export `GitHub Crucible Repository (2).zip`, 2026-06-23 → zip-3, 2026-06-24)
The prior export had **16 numbered slices**; zip-3 has **8** (renumbered 01–08).
- **Deleted by Claude Design between exports (7):** `live-run-view`, `verdict-detail`, `audit-row-replayer`, `health`, `admin-debug`, `workspace-policy`, `spec-history`.
- **Kept + renumbered (8):** strategy-catalog, whitebox, blue-patch, honest-dashboard, **coevolution (→05)**, halt, **leaderboard (→07)**, sr-report, plus Run Launcher / Canvas / Design System.
- So "Claude Design deleted out-of-spec stuff" is literally true between exports — but it deleted the four wired pages the user keeps, and **kept** the two stretch slices the user skips. The user's decisions invert Claude Design's choices for those slices; the net is that the live tree already reflects the user's intent.

### Section-level (live frontend → zip-3)

**Renamed-but-section-identical** (only `data-live` wiring + byte tweaks differ): Run Launcher, strategy-catalog, whitebox-selftest, Design System.

**Re-expanded (new export adds sections that `REMOVED_UI.md` deleted):**
- dashboard `+ ASR vs Detection · 30 days`, `+ Red ↔ Blue co-evolution`, `+ Cost per hack · distribution`, `+ Audit row replays`
- blue-patch `+ Held-out regression · v0.4.3 vs v0.4.2` (approval workflow returns); `- Blue patch review` h1
- halt `- Halt status` → `+ Halt h_19c4`; history/blocked/lift sections return
- sr-report `+ 1·Executive summary  2·Controls in force  3·Halt event h_19c4  4·Model lineage  5·Audit chain` (static report returns)

**Added files (new):** `slice-05-coevolution-curves`, `slice-07-leaderboard-export`.

**Deleted by design (Canvas tiles + no file):** Health, Admin · Debug, Workspace · Roles & Policy, Sealed-spec History.

**Canvas:** title `16 slices` → `capstone screens`; tiles added Co-evolution / Leaderboard / Live Run View / Verdict Detail / Audit-row Replayer; tiles removed Health / Admin·Debug / Workspace·Policy / Sealed-spec History.

**Wiring:** the new export contains **zero** `data-live*` / `crucible-*` hooks. Ten live pages carry them for `live.js` real-data injection. Verbatim overwrite strips wiring → static design numbers render = NO MOCK DATA violation. Sync must re-apply hooks.

<a name="contradictions"></a>
## Contradictions to reconcile (why item 3 blocks)

The user's framing — "I had Claude Design delete a bunch of out-of-spec stuff" — holds for the **Canvas tile removals** (Health, Admin, Policy, Specs) but is **reversed** for six slices: the export *re-adds* content that was deliberately removed on 2026-06-24.

1. **coevolution + leaderboard re-added.** `REMOVED_UI.md`: both are "PRD STRETCH goal, no backend route; REMAINING_WORK C6/C10 sanctions removal." `REMAINING_WORK.md` marked C6 and C10 **done by deletion** (`test ! -e frontend/slice-09-coevolution-curves.dc.html`, `… slice-13-leaderboard-export.dc.html`). Copying these back reverses completed, sanctioned work and adds pages with no backend.
2. **dashboard / blue-patch / halt / sr-report re-expanded.** Each re-adds sections `REMOVED_UI.md` removed for "no backend" or "replaced by the real route." Shipping them as static design = fabricated numbers on screen.
3. **Wired in-spec pages deleted.** Health (`/health`, PRD US-8), admin-debug (`/admin/overrides`), workspace-policy (`/policy`), spec-history (`/specs/history`) are wired to real backends. The design drops them.

Per CLAUDE DESIGN FIDELITY rule 6 ("reconcile with the user any contradictions and update the code") this is reconciled with the user, not silently copied.

## How to re-run the section diff (item 10)
```bash
# skeleton diff lives in the session scratchpad: skel.py
python3 skel.py "frontend/<live>.dc.html" "<unzipped-new>/<new>.dc.html"
```
