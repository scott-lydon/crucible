# STUB DATA PROTOCOL

**Audience:** the coding agent that will replace fixtures with real data wiring.
**Promise:** every piece of fake/mock/stubbed data in this project carries the literal
ASCII token `STUB:` somewhere in source. A single `grep -rn "STUB:"` finds 100% of it.

> If you add new design with fake data, **you must tag it.** Untagged fixtures violate the
> protocol — the coding agent will not find them and they will ship.

---

## 1 · The sentinel

The string **`STUB:`** (uppercase, colon, no space) appears literally next to every
fixture. It is never used for anything else in this codebase. To strip all fixtures:

```
grep -rn "STUB:" .            # locate every stub
grep -rn "STUB:link" .        # locate every dead nav target
grep -rn "STUB:series" .      # locate every fake dataset block
```

---

## 2 · The three carriers

The sentinel rides on one of three carriers depending on where the fake data lives.

### 2a. HTML attribute — for a single fake value on one element

Use a `data-stub` attribute. The attribute value is `<kind>:<source>` (see §3, §4).

```html
<!-- a run id that should be a row from the runs API -->
<a href="#" data-stub="link:route.runs.detail(r_8f3a)"
   data-stub-id="STUB:id:db.runs.list[0].id">r_8f3a</a>

<!-- a KPI number -->
<div data-stub="metric:api.dashboard.kpi.undetected_hack_rate">14.2%</div>
```

Notes:
- The bare `data-stub` attribute carries `<kind>:<source>`.
- Adjacent `data-stub-*` attributes (with explicit `STUB:` token) tag *additional*
  values on the same element (e.g. the link target *and* the displayed id).
- Attributes render zero pixels, so designs look unchanged. Inspect to see them.

### 2b. HTML comment — for a region (table body, chart dataset, list)

Wrap a block of fake rows in opening + closing comments. The opener carries the full
declaration; the closer just marks the end. The coding agent deletes everything between.

```html
<!-- STUB:series source=api.runs.list?window=30d note="latest 8 rows for dashboard table" -->
<div role="row">…</div>
<div role="row">…</div>
<!-- /STUB:series -->
```

### 2c. JS comment — for fake values inside `Component` logic

```js
class Component extends DCLogic {
  state = {
    // STUB:series source=api.coevolution.series note="red↔blue ASR over 12 rounds"
    asrSeries: [0.32, 0.41, 0.55, 0.48, 0.51, 0.46, 0.43, 0.38, 0.34, 0.30, 0.27, 0.24],
    // STUB:id source=route.spec.current
    specId: '9f2a4c7b',
  };
}
```

---

## 3 · `<kind>` taxonomy (fixed)

Greppable by category. Use exactly these tokens — do not invent new ones without
adding them here first.

| kind      | what it tags                                                                       |
|-----------|------------------------------------------------------------------------------------|
| `id`      | fake entity identifier (run id, halt id, patch id, spec hash, strategy slug, audit id, content hash). |
| `metric`  | a single numeric KPI or chart value displayed standalone (e.g. "14.2%").            |
| `series`  | a multi-value dataset: table body, chart series, list of rows, sparkline points.    |
| `text`    | copy block that should come from real content (description, finding, oracle name).  |
| `link`    | dead navigation: `href="#"`, fake download targets, modal openers that go nowhere.  |
| `time`    | hardcoded timestamp / window / "last refreshed" / cron literal.                     |
| `user`    | handle, email, display name, avatar.                                                |
| `cost`    | dollar amount, token count, budget, latency in $.                                   |
| `count`   | quantity displayed standalone ("142 runs", "11 halted", "48/48").                   |
| `status`  | enum-ish badge value (PASS / FAIL / matched / sealed / connected).                  |
| `code`    | fake code/JSON/diff/prompt body.                                                    |

---

## 4 · `<source>` format

A dotted path naming where the *real* value should come from. Free-form but should
parse as one of:

- **API call:** `api.<service>.<endpoint>[.<field>]` — e.g. `api.runs.list[].id`,
  `api.dashboard.kpi.undetected_hack_rate`.
- **DB / store:** `db.<table>.<lookup>[.<field>]` — e.g. `db.halts.byId.spec_hash`.
- **Route param:** `route.<page>.<param>` — e.g. `route.runs.detail(:id)`.
- **Session / auth:** `auth.session.<field>` — e.g. `auth.session.user.handle`.
- **Computed:** `compute.<expression>` — e.g. `compute.now()`, `compute.derived.gap`.
- **Config / sealed spec:** `spec.<field>`, `config.<key>`.

If the real source is genuinely undecided, write `source=TBD` and add a `note=`
explaining the open question. Do not omit `source=`.

---

## 5 · Optional fields

After `kind:source` you can append space-separated `key=value` pairs (no quotes
needed unless the value has spaces, in which case use `"..."`).

| key      | meaning                                                                  |
|----------|--------------------------------------------------------------------------|
| `note`   | one-line explanation for the coding agent.                               |
| `count`  | for `series`: how many rows the real call should return (`count=8`).     |
| `unit`   | for `metric` / `cost`: `unit=pct`, `unit=usd`, `unit=ms`, `unit=tokens`. |
| `shape`  | for `code`/`series`: shape hint (`shape=number[]`, `shape={id,ts,asr}`). |
| `format` | display formatter to keep (`format=iso8601`, `format=$%,.0f`).           |

Example with everything:

```html
<!-- STUB:series source=api.runs.list?window=30d count=8 shape={id,ts,asr,patch} note="latest sealed-spec runs" -->
```

---

## 6 · What to tag vs. leave alone

**Tag:**
- Every value the user could mistake for real (numbers, ids, names, copy, links).
- Every chart/table/list that will eventually be hydrated from a backend.
- Every download/export anchor that doesn't actually produce a file.

**Don't tag:**
- Static UI chrome (button labels like "Export", section headings like "Strategies").
- The product name "Crucible", page titles, nav labels — these are real.
- Token/palette values from `_palette_notes.md`.
- Decorative SVG geometry.

When in doubt, **tag it.** Over-tagging costs the coding agent one extra glance;
under-tagging ships fake data.

---

## 7 · Removal recipe (for the coding agent)

```
# 1. Inventory
grep -rn "STUB:" . | sort -u

# 2. By kind
grep -rn "STUB:link" .       # wire routes / downloads first (cheap)
grep -rn "STUB:id" .         # then identifiers from real fixtures
grep -rn "STUB:series" .     # then the big datasets (most work)
grep -rn "STUB:metric" .     # KPIs
grep -rn 'STUB:' . | grep -v 'STUB:link\|STUB:id\|STUB:series\|STUB:metric'   # everything else

# 3. After each removal
#    - delete the data-stub attribute / wrapping STUB comments
#    - replace the literal with the real binding
#    - keep the same display format (see format= hint)
```

When zero results remain, the design is fully wired.

---

## 8 · Anti-patterns

- **Don't** spell it `Stub:` / `stub:` / `// STUB ` (space, no colon) — breaks grep.
- **Don't** invent new `<kind>` tokens; extend §3 first.
- **Don't** leave a `data-stub` without a `source=` value.
- **Don't** tag tokens (palette hex, spacing) — those are design decisions, not stubs.
