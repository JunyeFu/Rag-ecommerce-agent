"""Run the trusted operations administrator command from this source checkout."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [
    str(ROOT / path)
    for path in (
        "apps/api/src",
        "packages/domain/src",
        "packages/agent-runtime/src",
        "packages/contracts/generated/python",
    )
]

from ragcommerce_api.ops_admin import main  # noqa: E402

if __name__ == "__main__":
    main()
