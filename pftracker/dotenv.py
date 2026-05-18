"""Load .env from project root into os.environ (setdefault — does not override)."""
import os
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent


def load_dotenv(path: Path | None = None) -> None:
    env_file = path or (_PROJECT_ROOT / '.env')
    if not env_file.is_file():
        return
    with env_file.open() as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith('#') or '=' not in line:
                continue
            key, _, value = line.partition('=')
            os.environ.setdefault(key.strip(), value.strip())
