"""Validate the AlgoTest Leg Builder strategy definition against the canonical schema."""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "apps" / "api"))

from app.quant.schema import validate_definition


def main() -> int:
    definition_path = Path(__file__).parent / "strategy_algotest_leg_builder.json"
    with open(definition_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    errors, warnings = validate_definition(data)

    if errors:
        print("VALIDATION FAILED")
        for err in errors:
            print(f"  ERROR: {err}")
        return 1

    print("VALIDATION PASSED")
    if warnings:
        for w in warnings:
            print(f"  WARNING: {w}")
    else:
        print("  No warnings.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
