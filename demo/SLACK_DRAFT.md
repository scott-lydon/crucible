# Slack message draft (for operator approval before send)

Recipients: group DM with Gustavo Hornedo (U0B0SP8R8Q0), Ruijing Wang
(U0AV8HZCYDT), Julian Stancioff (U0AUX1QM0ET). Sender: U0B00RQKDQD.

The message must contain exactly three things (handoff §6): the PR link, the
demo video link(s), and a brief plain explanation. Two videos were produced
(local real-LLM run + the live deploy), so both links are included.

---

Hi all, sharing the Crucible capstone for review.

What it is: an adversarial-robustness platform that red-teams a target (a fraud
LightGBM classifier and a code-generation agent), scores how often an informed
attacker gets past the verifier, proposes blue-team patches, and reports it all
for SR 11-7 model risk review. Every number in the UI comes from real API
responses, nothing is mocked.

Pull request: https://github.com/scott-lydon/crucible/pull/3

Demo videos (each walks all 15 user stories, US-1 to US-15):
- Local real-LLM run: <LOCAL_YOUTUBE_URL>
- Live deploy (https://crucible-zaag.onrender.com): <DEPLOY_YOUTUBE_URL>

The deploy serves the branch code with a captured real-LLM data snapshot, and can
run live against the Anthropic API via the admin panel. Happy to walk through any
part of it.

---

NOTE: replace <LOCAL_YOUTUBE_URL> and <DEPLOY_YOUTUBE_URL> with the Unlisted
watch URLs after upload. Do NOT send until the operator approves this text.
