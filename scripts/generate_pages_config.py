#!/usr/bin/env python3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ENV_PATH = ROOT / ".env"
DOCS_CONFIG_PATH = ROOT / "docs" / "config.js"


def load_env(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip()
    return values


def main() -> None:
    env = load_env(ENV_PATH)
    supabase_url = env.get("SUPABASE_URL", "")
    supabase_key = env.get("SUPABASE_KEY", "")

    if not supabase_url or not supabase_key:
        raise SystemExit("SUPABASE_URL and SUPABASE_KEY must be set in .env")

    DOCS_CONFIG_PATH.write_text(
        "window.PLANT_CONFIG = "
        + "{\n"
        + f'  SUPABASE_URL: "{supabase_url}",\n'
        + f'  SUPABASE_KEY: "{supabase_key}"\n'
        + "};\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
