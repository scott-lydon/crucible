# Crucible front end

This directory is the Crucible operator dashboard front end, ported verbatim
from the Claude Design project "GitHub Crucible Repository". Each screen is a
self contained `*.dc.html` page. The pages are the canonical artifact, not a
reference mock.

## How it runs

There is no build step. `support.js` is the Claude Design runtime: on load it
pulls React 18, ReactDOM, and Babel standalone from unpkg, parses the `<x-dc>`
template in each page, and renders it. Pages cross link by relative href, so
serving this directory over any static file server gives a navigable app.

```bash
cd frontend
python3 -m http.server 8080
# open http://localhost:8080  (redirects to the Run Launcher, route "/")
```

A network connection is required because `support.js` fetches React and Babel
from unpkg and the pages fetch fonts (Google Fonts) and icons (Simple Icons).

## Entry points

- `index.html` redirects to `slice-01-run-launcher.dc.html` (route `/`).
- `Canvas.dc.html` is the 20 screen contact sheet; every tile links to its page.
- `Crucible Design System.dc.html` documents the palette and components.
- `_palette_notes.md` is the canonical palette ("Graphite Meridian"); the
  architecture site at `../website/index.html` re-syncs to these hex codes.

## What was excluded from the export

The Claude Design project archive also contained an `uploads/` folder (the
capstone proposal PDF and design process screenshots) and a `.thumbnail`. No
page references those, so they are design inputs rather than front end assets
and are not shipped here.
