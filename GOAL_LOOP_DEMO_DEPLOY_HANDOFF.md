# Crucible goal-loop handoff: video-recorded acceptance tests, deploy, share

This briefs a multi-agent goal loop to: record a narrated demo video of
Crucible's acceptance tests running against a live deploy, fix any bug the
recording reveals, deploy Crucible to Render WITHOUT merging the pull request to
main, upload the finished video online, and post it to the Slack group with
Gustavo, Julian, and Ruijing. It is fully self contained: a fresh session with
no memory of the prior conversation can execute it. State lives in the section 7
checklists, not in any agent's memory.

This loop depends on the functional loop. The app must already pass
`GOAL_LOOP_HANDOFF.md` (functional + data-integrity verification) before a frame
is recorded. A demo of broken functionality is worthless. If functional
verification is not green, run that loop first.

## Canonical references (a cold session needs nothing it cannot find here)

Every path, URL, and id this loop needs, so a fresh session never has to discover
or guess them. Absolute paths; verify each still resolves at start.

Repo and source control:
- Repo root: `/Users/scottlydon/Desktop/Clutter/iOS/crucible`
- Working branch (deploy this, do NOT merge): `feat/crucible-build`
- Pull request: `https://github.com/scott-lydon/crucible/pull/3` (PR #3, base `main`)
- GitHub remote: `https://github.com/scott-lydon/crucible.git`
- GitLab mirror remote: `git@labs.gauntletai.com:scottlydon/crucible.git`
  (SSH port 22022; graders read the GitLab mirror)

Spec / PRD (the source of truth for what to demo, in scope order):
- Acceptance tests + user stories US-1..US-15: `acceptance-tests.md`
- Design brief (the PRD-equivalent handoff brief): `design/claude-design-brief.md`
- Architecture: `ARCHITECTURE.md` · Coding practices: `coding-practices.md`
- Task slices: `tasks.md` · Out-of-scope removed UI: `REMOVED_UI.md`
- QA adversary playbook: `QA_ADVERSARY.md`
- Functional + data-integrity loop this one depends on: `GOAL_LOOP_HANDOFF.md`

Running app:
- Render live deploy: `https://crucible-zaag.onrender.com`
  (Render service name `crucible`, service id `srv-d8trfn9o3t8c73bvp470`)
- Local HEAD server for the live real-LLM recording: `http://localhost:8910/app`
  (start command in section 2; Postgres on host port 5434)
- Branch-only deploy marker (proves Render serves the branch, not main):
  `GET /targets/code_agent/default-spec` returns 200 on the branch, 404 on main

Secrets (source these; never print or fake them):
- Crucible env (DATABASE_URL, RENDER_API_KEY, MODAL_TOKEN_ID/SECRET, etc.):
  `/Users/scottlydon/Desktop/Clutter/iOS/crucible/.env`
- ElevenLabs voice secrets (ELEVENLABS_API_KEY, ELEVENLABS_VOICE_ID):
  `/Users/scottlydon/.config/conveyor/elevenlabs.env`

ElevenLabs voice pipeline (reuse, do not rebuild):
- `/Users/scottlydon/.claude/skills/assignment-conveyor/lib/elevenlabs_tts.sh`
  (`el_tts_render`)
- `/Users/scottlydon/.claude/skills/assignment-conveyor/lib/phase_14a_elevenlabs.sh`
  (pace-checked render + ffmpeg mux pattern)

Publish target:
- YouTube, visibility Unlisted (set Unlisted in the wizard before Save)

Slack group to notify (resolve the mpim by these three member ids, then send):
- Gustavo Hornedo: `U0B0SP8R8Q0` (gustavo.cruz@gfachallenger.gauntletai.com)
- Ruijing Wang: `U0AV8HZCYDT` (ruijing.wang@challenger.gauntletai.com)
- Julian: most likely Julian Stancioff `U0AUX1QM0ET` (display name "Julian",
  julian.stancioff@gfachallenger.gauntletai.com). A second Julian exists, Julian
  McOmie `U0AF60ZPQ4A`. Before sending, confirm the group DM's members are
  exactly these three; if the group contains McOmie instead, use that id.
- Sender (you) Slack user id: `U0B00RQKDQD`

## 0. Prime directive: demo only what the spec says, fix what the demo reveals

- The acceptance tests demoed are `acceptance-tests.md` section 1 (US-1..US-15).
  Demo only behavior that traces to a US-n OR is plainly entailed by the PRD as
  part of delivering a named US-n. Do not stage, narrate, or imply any feature
  the spec does not have. No invented scope, no faked screens, no rehearsed
  result that is not the live run's real output (global NO-FAKE-DATA rule).
- The video shows REAL runs against the REAL deploy. Narration may not claim a
  number the screen does not show. If a value on screen is wrong, that is a bug
  to fix, not to talk around.
- Every bug the recording or the watcher reveals is fixed by the coding agent,
  reverified, and the affected segment re-recorded. The video is not "done"
  while a known app bug is visible in it.

## 1. Agent team arrangement (separation of duties, no self-certification)

The agent that writes a fix never confirms it. The agent that records the video
never judges whether it is good. Distinct contexts:

### A. Builder / Coding agent (writes code, may NOT sign off the result)
- Tools: Read, Write, Edit, shell, backend tests. Fixes bugs handed to it by the
  Bug-Watcher with the smallest change that satisfies the cited US-n. Commits
  each fix separately on `feat/crucible-build`. Never closes its own finding.

### B. Recording agent (drives the live UI, captures the screen + voice)
- Tools: Chrome MCP (navigate, computer, get_page_text), shell (ffmpeg /
  screencapture, the ElevenLabs helper), Read.
- Walks each in-scope acceptance scenario through the browser against the live
  deploy while screen-recording, and lays the user's ElevenLabs voice narration
  over it (section 4). Produces per-scenario clips plus a stitched master.

### C. Bug-Watcher agent (watches the video, finds app bugs, fixes nothing)
- Tools: Read (the recorded file frames / transcript), Chrome MCP screenshot,
  shell to extract frames (ffmpeg). No Edit/Write.
- Watches the recording (frame extraction at 1 to 2 fps plus the audio
  transcript, since an agent cannot stream video natively) and the live screens,
  and identifies APP bugs: wrong values, broken controls, error states, a screen
  that does not match the US-n it claims to show. Writes a bug packet (US-n,
  timestamp, frame path, expected-vs-shown) and hands it to the Builder. Does not
  fix. Is a different context from the Builder so it cannot rationalize the code.

### D. Video-Critique agent (judges the video as a video, not the code)
- Tools: Read (frames + transcript), shell (ffmpeg, whisper for the audio). No
  Edit/Write.
- Reviews the stitched master for naturalness and sense: does the narration
  sound unnatural or rushed, does the voiceover match what is on screen, do the
  segments flow, is anything confusing, mistimed, or contradictory. If it fails
  on naturalness, coherence, voiceover-screen mismatch, or pacing, it sends the
  video BACK with a specific re-record/re-narrate note to the Recording agent.
  It judges the artifact, never the code; app bugs are the Bug-Watcher's lane.

### E. Deploy agent (Render, without merging the PR)
- Tools: shell (git, curl, Render API or `render` CLI), Read. Implements the
  no-merge deploy in section 3 and verifies the live URL serves the branch code.

### F. Publish + Notify agent (upload, then Slack)
- Tools: shell / Chrome MCP for the upload, Slack MCP for the message. Uploads
  the approved video Unlisted, then posts to the Slack group. The Slack send is
  the one irreversible external action: it runs only after the operator approves
  the drafted message (section 6).

### Orchestrator (the loop)
- Routes packets, never lets a writer certify its own work, drives the section 7
  checklist to all-green. Holds no opinion on the code or the video.

## 2. Environment and prerequisites

- Repo `/Users/scottlydon/Desktop/Clutter/iOS/crucible`, branch
  `feat/crucible-build`, PR #3 (`https://github.com/scott-lydon/crucible/pull/3`,
  base `main`). Do NOT merge this PR.
- Live functional app for recording: prefer the Render deploy from section 3;
  the local HEAD server (`http://localhost:8910/app`, see `GOAL_LOOP_HANDOFF.md`
  section 2) is the fallback if the deploy is mid-flight. The video must show the
  deploy URL once section 3 is green.
- Secrets to confirm present before starting (fail loudly if missing, never
  fake): `ELEVENLABS_API_KEY`, `ELEVENLABS_VOICE_ID` (the user's trained voice),
  Render credentials (`RENDER_API_KEY` is in `.env`), `MODAL_TOKEN_ID` /
  `MODAL_TOKEN_SECRET` (already provided, in `.env`), a YouTube-capable session
  for the upload, and Slack access to the group.
- ElevenLabs voice pipeline already exists and is REUSED, not rebuilt:
  `~/.claude/skills/assignment-conveyor/lib/elevenlabs_tts.sh` (`el_tts_render`)
  and the pace-checked muxing pattern in
  `~/.claude/skills/assignment-conveyor/lib/phase_14a_elevenlabs.sh`. Voice id
  and key come from env; the pace detector re-renders rushed narration.
- Upload target: YouTube, visibility Unlisted (set Unlisted in the wizard BEFORE
  Save; Public is never the default for this).
- Slack group: the direct-message group containing Gustavo Hornedo, Julian, and
  Ruijing Wang. Resolve its channel id by those member names via the Slack MCP;
  do not guess an id.
- Machine-load rule: one heavy job at a time (ffmpeg encode, a real-LLM Crucible
  run, a Render build). Check `uptime` before launching another.

## 3. Deploy to Render without merging PR #3

Decision (the operator left the method to the loop): deploy the working branch
directly, no merge, no parallel repo unless forced. Render deploys whatever
branch a service tracks, so point the existing `crucible` service at
`feat/crucible-build`.

Primary path (no parallel repo):
1. In the Render service `crucible`, set the tracked branch from `main` to
   `feat/crucible-build` (Render dashboard service Settings, or the Render API
   `PATCH /services/{id}` with `branch`). `autoDeploy: true` then builds the
   branch head on every push.
2. Trigger a deploy of the branch head (push, or Render API
   `POST /services/{id}/deploys`). Migrations run on container start per the
   Dockerfile CMD.
3. Verify the live URL serves the BRANCH code, not stale main: hit `/health`
   (200, db connected) and a branch-only marker (for example the new
   `GET /targets/code_agent/default-spec` returns 200, which main does not have).
   That endpoint is the deploy-asymmetry proof: if it 404s, Render is on old code.

Fallback (only if branch deploy is blocked by plan or policy): create a deploy
mirror repo `crucible-deploy`, push `feat/crucible-build` to its `main`, point a
new Render Blueprint at it, and keep it in sync by pushing the branch to the
mirror on each change. Document which path was used in RUN_REPORT. Do not modify
PR #3's base or merge it under any path.

Render runs `MOCK_LLM=true` (no `claude` CLI on Render). So the DEPLOY shows the
dashboard and every read route on real persisted data, and the live red/blue
walk-through in the video is recorded against the LOCAL real-LLM server. The
narration must disclose, once and plainly, which segments are the live local run
versus the deployed dashboard. Never present the mock dashboard as a live run.

## 4. Record the narrated acceptance-test video

1. Script per scenario from the US-n Given/When/Then (US-1..US-15, in scope
   only). One short narration block per scenario, spoken-prose style: short
   sentences, contractions, no dashes, lead with what the screen shows.
2. Render each narration block to the user's voice via `el_tts_render` (reuse the
   helper; the pace detector re-renders anything rushed).
3. Screen-record the Chrome MCP walk of each scenario against the live app
   (ffmpeg avfoundation screen capture, or `screencapture -v`), then mux the
   voice over the screen clip with ffmpeg, matching narration to the on-screen
   action. Keep per-scenario clips so a single failed scenario can be re-recorded
   without redoing the whole video.
4. Stitch the clips into one master mp4 with a short title and an outro frame.
5. Every value spoken must match the value on screen for that real run. The
   adversarial-probe discipline from `GOAL_LOOP_HANDOFF.md` applies: if a number
   looks pre-baked, it is a bug, route it to the Bug-Watcher.

## 5. Bug-fix and critique loops (both must drain to zero)

- Bug loop: Bug-Watcher finds an app bug in the recording or live screen ->
  Builder fixes on the branch -> Deploy agent redeploys if the fix is server-side
  (deploy-verify, do not trust the edit) -> Recording agent re-records the
  affected scenario -> Bug-Watcher re-checks. Repeat until zero open app bugs.
- Critique loop: Video-Critique agent reviews the stitched master -> if
  unnatural, incoherent, mismatched, or mistimed, sends a specific note back ->
  Recording agent re-narrates or re-records the flagged segment -> re-stitch ->
  re-critique. Repeat until the critique agent passes the whole video.
- A re-record for a bug fix re-enters BOTH loops (the new segment must pass
  critique too). The video is final only when both loops are empty at once.

## 6. Upload and Slack message

- Upload the critique-approved, bug-clean master to YouTube as Unlisted. Capture
  the watch URL.
- Draft the Slack message to the group (Gustavo, Julian, Ruijing). It must
  contain exactly three things: the PR link
  (`https://github.com/scott-lydon/crucible/pull/3`), the demo video link, and a
  brief plain explanation of what is being shared and what it shows. Teammate DM,
  so the links belong here (this is not a public post, the no-public-demo-URL
  rule does not apply).
- The operator approves the drafted message text before send (the one human
  gate; sending to colleagues is irreversible). Then the Notify agent sends it
  via the Slack MCP. Confirm delivery.

## 7. Iteration checklists (the loop's persisted state)

Rules: a box is ticked only by the bracketed agent, in a fresh context, with
evidence (file path, frame, URL, or API response). The writer never ticks the
reviewer's box. A regression unticks the box. The loop is done only when the
section 8 master checklist is green.

### Stage P: prerequisites
- [x] [Deploy] All secrets in section 2 confirmed present; missing ones surfaced
      to the operator, not faked. EVIDENCE 2026-06-25: presence-checked (names
      only, no values printed): .env has DATABASE_URL, RENDER_API_KEY,
      MODAL_TOKEN_ID, MODAL_TOKEN_SECRET; elevenlabs.env has ELEVENLABS_API_KEY,
      ELEVENLABS_VOICE_ID (both `export `-prefixed). None missing.
- [x] [Recording] ElevenLabs helper renders a 5-second test clip in the user's
      voice (proves voice id + key + quota). EVIDENCE: `el_tts_render` →
      `demo/voice/_test5s.mp3`, ffprobe duration 4.83s, 78202 bytes, HTTP 200.
- [x] [Builder] Functional loop (`GOAL_LOOP_HANDOFF.md`) is green; app works
      before any recording. EVIDENCE: GOAL_LOOP_HANDOFF.md checkbox tally =
      68 ticked / 0 unticked.
- [x] [Loyalty] Scenario list to be recorded is exactly the in-scope US-n set;
      nothing out of scope staged. EVIDENCE: acceptance-tests.md §1 defines
      exactly US-1..US-15 (grep of `^### US-`); Stage R below enumerates exactly
      US-1..US-15, no extra scenario.

### Stage D: deploy to Render without merging PR #3
- [x] [Deploy] Render `crucible` service set to track `feat/crucible-build` (or
      fallback mirror documented); PR #3 untouched, not merged. EVIDENCE: Render
      API `srv-d8trfn9o3t8c73bvp470` → branch=`feat/crucible-build`,
      autoDeploy=yes, repo=github.com/scott-lydon/crucible. `gh pr view 3` →
      state OPEN, mergedAt None, base main, head feat/crucible-build. Primary
      path (no parallel repo) used.
- [x] [Deploy] Branch head deployed; build succeeded in the Render log. EVIDENCE:
      pushed 10 commits (7ca8b2d→81fa776) to GitHub + GitLab mirror; triggered
      deploy `dep-d8ucla6q1p3s73bg2vb0`, commit 81fa776929, status `live`.
- [x] [Deploy] Live URL serves BRANCH code: `/health` 200 AND
      `/targets/code_agent/default-spec` returns 200 (the branch-only marker).
      EVIDENCE: https://crucible-zaag.onrender.com `/health`→
      `{"status":"ok","database":"connected"}`; marker→200; new-feature routes
      `/admin/overrides`→200 (commit bb84081), `/metrics`→200 (proves latest
      branch head, not stale main, is live).
- [x] [Loyalty] Deploy exposes no out-of-scope route or screen. EVIDENCE
      2026-06-25 (after BUG-L1 fix, operator-approved removal): launcher
      admin-control grep clean (0 matches); the two out-of-scope STRETCH screens
      are now GONE from the deploy — `slice-05-coevolution-curves.dc.html` → 404,
      `slice-07-leaderboard-export.dc.html` → 404; deployed `Canvas.dc.html`
      contains 0 links to them; in-scope screens intact (Canvas 200, catalog
      200, /health 200). Fix commit 90aabcd, deploy dep-d8uijd5aeets73948ta0
      (commit 90aabcd) status live. NOTE: a related dashboard co-evolution panel
      on slice-04 renders an honest empty state ("No co-evolution data") and is
      tracked as BUG-L2 for the US-10 integrity pass (see Stage R US-10).

### Stage R: record the acceptance-test video (one box per acceptance test)

Each box is ticked only when that US-n's own Given/When/Then is shown on screen
and narrated. Read the cited acceptance-tests.md lines before recording so the
clip demonstrates the actual Then-clauses, not a paraphrase. Each recording box
has a paired Integrity box: the Integrity Reviewer confirms every value spoken or
shown in that clip equals the live run's real API response, no pre-baked number.

- [ ] [Recording] US-1 submit a target for evaluation (acceptance-tests.md L25):
      select target, sealed spec present, click Start, navigates to
      `/runs/:runId`, sandbox launched, first round within ten seconds.
- [ ] [Integrity] US-1 clip values equal the launcher + `/runs/:id` payloads.
- [ ] [Recording] US-2 watch one round live (L42): ASR chart per attack,
      detection per verdict, reasoning trace streaming via SSE, Inspect opens
      real prompt/response/tokens/cost. Live local real-LLM run, disclosed.
- [ ] [Integrity] US-2 streamed values equal the SSE / `/runs/:id` source.
- [ ] [Recording] US-3 drill into a verdict (L58): producer output, verbatim
      obligation, per-oracle pass/fail + reasoning, vote tally, working Replay.
- [ ] [Integrity] US-3 clip values equal `/runs/:id/verdicts/:id`.
- [ ] [Recording] US-4 every oracle vote and reasoning (L74): full vote
      breakdown; judge weight is the REAL `/oracles/registered` weight.
- [ ] [Integrity] US-4 votes + judge weight equal `/oracles/registered`.
- [ ] [Recording] US-5 replay any past action (L89): deterministic re-run, same
      seed same result.
- [ ] [Integrity] US-5 replay output equals the original captured audit row.
- [ ] [Recording] US-6 browse the strategy catalog (L105): real `/catalog` rows.
- [ ] [Integrity] US-6 rows equal the `/catalog` response.
- [ ] [Recording] US-7 trigger the blue loop and review the patch (L120): patch
      at `/blue/:patchId`, real before/after detection, produced model version.
- [ ] [Integrity] US-7 clip values equal `/blue/:patchId`.
- [ ] [Recording] US-8 platform health for every subcomponent (L138): health for
      each registered target and oracle.
- [ ] [Integrity] US-8 statuses equal `/health/targets/:type` +
      `/health/oracles/:name`.
- [ ] [Recording] US-9 confirm the producer sandbox is sealed (L155): egress
      denied shown from real sandbox state.
- [ ] [Integrity] US-9 seal/egress state equals the real sandbox status.
- [ ] [Recording] US-10 dashboard metrics (L171): catch rates, gap, undetected
      rate, all from `/metrics`.
- [ ] [Integrity] US-10 figures equal `/metrics`; nulls render as em-dash.
- [ ] [Recording] US-11 export the seeded-hack corpus (L190): export from
      `/corpus` / `/corpus.jsonl`.
- [ ] [Integrity] US-11 exported rows equal the route payload.
- [ ] [Recording] US-12 generate an SR 11-7 report (L204): report from
      `/reports/:runId`, real markdown.
- [ ] [Integrity] US-12 report numbers equal the report route.
- [ ] [Recording] US-13 halt at a residual red line (L220): halt banner on every
      route when `/halt` is halted, honest "no active halt" otherwise; automatic
      state, no operator halt button.
- [ ] [Integrity] US-13 recall/threshold shown equal `/halt`.
- [ ] [Recording] US-14 white-box self-test on every pass (L236): `slice-10`
      shows real self-test results.
- [ ] [Integrity] US-14 self-test values equal their backing route.
- [ ] [Recording] US-15 internal debug route (L254): `slice-12-admin-debug`
      reachable, real overrides.
- [ ] [Integrity] US-15 override rows equal `/admin/overrides`.
- [ ] [Recording] Master mp4 stitched from all 15 per-scenario clips with title +
      outro; no scenario omitted.

### Stage B: bug loop (drain to zero)
- [ ] [Bug-Watcher] Full recording watched (frames + transcript); every app bug
      logged with US-n, timestamp, frame, expected-vs-shown.
- [ ] [Builder] Every logged bug fixed on the branch, committed separately.
- [ ] [Deploy] Server-side fixes redeployed and deploy-verified.
- [ ] [Recording] Every affected scenario re-recorded.
- [ ] [Bug-Watcher] Re-check finds zero open app bugs in the current master.

### Stage C: video-critique loop (drain to zero)
- [ ] [Video-Critique] Master reviewed for naturalness, coherence,
      voiceover-screen match, and pacing.
- [ ] [Recording] Every flagged segment re-narrated or re-recorded.
- [ ] [Video-Critique] Re-review passes the whole video with zero open notes.

### Stage U: upload + notify
- [ ] [Publish] Master uploaded to YouTube as Unlisted; watch URL captured.
- [ ] [Notify] Slack message drafted with PR link + video link + brief
      explanation; resolved the group channel id by member names.
- [ ] [Operator] Drafted message text approved.
- [ ] [Notify] Message sent to the Gustavo/Julian/Ruijing group; delivery
      confirmed.

## 8. Master exit checklist (the loop stops only when all are ticked)
- [ ] Deploy serves the branch (not main), PR #3 not merged.
- [ ] Bug loop empty: zero app bugs visible in the final master.
- [ ] Critique loop empty: video passes naturalness + coherence + match + pacing.
- [ ] Every recorded scenario is an in-scope US-n; zero invented scope.
- [ ] Video uploaded Unlisted; Slack message delivered to the group with PR link,
      video link, and explanation.
- [ ] RUN_REPORT committed: deploy path used, per-scenario evidence, bug log,
      critique notes, final URLs.

## 9. Evidence to leave behind
- `demo/` with per-scenario clips, the stitched master, the narration scripts,
  and the rendered voice mp3s.
- `RUN_REPORT.md`: which deploy path was used, the branch-marker check output,
  the bug log with fixes (commit hashes), the critique notes and resolutions, the
  YouTube URL, and the Slack delivery confirmation.
- Commits: one logical fix each, Conventional Commits, `Assisted-by` trailer, all
  on `feat/crucible-build`.
