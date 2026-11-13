"""Export the FastAPI OpenAPI schema to ``docs/openapi.json``.

Usage::

    python -m scripts.export_openapi
    python -m scripts.export_openapi --output build/openapi.json
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from app.main import app


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        default="docs/openapi.json",
        help="Output path (default: docs/openapi.json)",
    )
    args = parser.parse_args()

    schema = app.openapi()
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(schema, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    operations = sum(
        1
        for methods in schema.get("paths", {}).values()
        for method in methods
        if method in {"get", "post", "put", "patch", "delete", "head", "options"}
    )
    print(f"OpenAPI written to {output} ({operations} operations)")


if __name__ == "__main__":
    main()
