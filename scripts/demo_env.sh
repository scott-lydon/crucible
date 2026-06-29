#!/usr/bin/env bash
# Source this before a LIVE Crucible demo:  source scripts/demo_env.sh
#
# It does NOT contain any secret. The OpenRouter key is read by the app from
# ~/.config/crucible/openrouter.key (or the OPENROUTER_API_KEY env var). Without
# that key present, every CRUCIBLE_REAL_* flag below is a silent no-op and the
# demo runs on the free deterministic ScriptedLLM mocks (agents ignore their
# prompt, co-evolution curves stay flat). See shared/config.py + orchestrator/wiring.py.

# --- Real-model flags (each flips one call-site from mock to a real model) ---
export CRUCIBLE_REAL_AGENT=1         # the producer (support-bot / code-agent) follows its prompt  [most important]
export CRUCIBLE_REAL_RED=1           # the attacker reasons adaptively instead of replaying scripts
export CRUCIBLE_REAL_JUDGE=1         # the LLM-judge oracle (Opus) grades for real
export CRUCIBLE_REAL_BLUE=1          # the defender rewrites the system prompt for real (needed for co-evolution)
export CRUCIBLE_REAL_DIFFERENTIAL=1  # the second independent corroborator oracle is real
# Cross-family differential: Crucible AUTO-picks a different family than the producer
# (shared/model_family.py). Producer is Claude here, so it selects openai/gpt-5.5 on its own —
# no hardwiring. To FORCE a specific model, uncomment:
# export CRUCIBLE_DIFFERENTIAL_MODEL=google/gemini-3.5-flash
export CRUCIBLE_REAL_HELDOUT=1       # LLM-generated held-out checks — REQUIRED to detect
                                     # correctness misses (keyword detectors only catch PII/refund/secrets)
# Optional — leave off to save cost unless you specifically show them:
# export CRUCIBLE_REAL_SPEC=1        # LLM spec compiler (only if you compile a spec live)

# --- Safety / cost ---
export CRUCIBLE_GLOBAL_BUDGET=25     # hard dollar cap protecting the shared key (default 25.0)
# Certification is ADVISORY, not blocking (api.py no longer 409s). 0 is the kill-switch:
# halt_state() returns halted=false, so the yellow "not certified" banner never renders.
# The feature stays in the code — raise this to 0.70 to bring the advisory warning back.
export CRUCIBLE_HALT_RECALL=0

# --- Reminders (printed, not enforced) ---
echo "[demo_env] Real-model flags exported (AGENT/RED/JUDGE/BLUE/DIFFERENTIAL)."
if [ -f "$HOME/.config/crucible/openrouter.key" ] || [ -n "$OPENROUTER_API_KEY" ]; then
  echo "[demo_env] OpenRouter key: FOUND — real models will run."
else
  echo "[demo_env] WARNING: no OpenRouter key found — runs will fall back to MOCKS."
fi
echo "[demo_env] Reminder: Docker must be running for any code_agent (sandbox) run."
