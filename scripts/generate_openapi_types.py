#!/usr/bin/env python
"""Generate a small TypeScript schema index from FastAPI OpenAPI."""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.api.app import app

OUTPUT = Path("dashboard/generated/api-types.ts")


def render() -> str:
    schemas = app.openapi().get("components", {}).get("schemas", {})
    body = json.dumps(schemas, indent=2, sort_keys=True)
    return (
        "// Generated from FastAPI OpenAPI schemas. Run `npm run generate:api-types` in dashboard.\n"
        f"export const generatedApiSchemas = {body} as const;\n"
        "export type GeneratedApiSchemas = typeof generatedApiSchemas;\n"
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    content = render()
    if args.check:
        current = OUTPUT.read_text() if OUTPUT.exists() else ""
        if current != content:
            print(f"{OUTPUT} is stale; run npm run generate:api-types")
            return 1
        print(f"{OUTPUT} is up to date")
        return 0
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(content)
    print(f"wrote {OUTPUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
