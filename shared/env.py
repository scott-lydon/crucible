from pathlib import Path

from dotenv import load_dotenv

_REPO_ROOT = Path(__file__).resolve().parents[1]


def load_env(path: Path | None = None) -> bool:
    """Load the repo-root .env into os.environ (idempotent; real env vars win).

    Returns True if a .env file was found and loaded. Never raises if absent.
    Secrets are never logged/printed.
    """
    env_path = path if path is not None else _REPO_ROOT / ".env"
    return load_dotenv(dotenv_path=env_path, override=False)
