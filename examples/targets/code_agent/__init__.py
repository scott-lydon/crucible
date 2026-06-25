"""Code-agent victim (slices 3, 5): the reward-hacking showcase target.

A realistic LLM coding agent that, given a function signature + description +
VISIBLE example tests, PRODUCES Python source. The objective held-out-test oracle
then runs that produced (untrusted) code against a SEALED held-out test set the
producer never saw, inside the Docker sandbox: code that passes the visible tests
but FAILS the held-out set (a reward-hack / a wrong implementation) is caught with
no invented rule and no LLM judgment.

Only ``orchestrator/wiring.py`` (the composition root) may import from here.
"""

from examples.targets.code_agent.engine import CodeAgentEngine
from examples.targets.code_agent.producer import DEFAULT_SYSTEM, CodeAgentProducer
from examples.targets.code_agent.record import CodeCase, CodeTask
from examples.targets.code_agent.spec import SPEC_PATH, load_spec
from examples.targets.code_agent.tasks import TASK_LIBRARY, generate_batch


def always_real(_task: object) -> bool:
    """Harness ``label_fn`` for the produce shape.

    Every code task is a genuine task to be judged (there is no negative class),
    so this is constant ``True``. Kept as a named function (not a lambda) so the
    composition root can pass it without an inline closure.
    """
    return True


__all__ = [
    "DEFAULT_SYSTEM",
    "SPEC_PATH",
    "TASK_LIBRARY",
    "CodeAgentEngine",
    "CodeAgentProducer",
    "CodeCase",
    "CodeTask",
    "always_real",
    "generate_batch",
    "load_spec",
]
