from shared.env import load_env

# Load the repo-root .env at collection time so gated/live tests (e.g. the
# Anthropic smoke in shared/llm/test_llm.py) see the key when a .env exists.
load_env()
