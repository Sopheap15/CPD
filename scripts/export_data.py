"""Export the Excel data files into the JSON blob the Cloudflare Worker reads.

Cloudflare Python Workers run on Pyodide, which does not have pandas or
openpyxl, so the Excel files cannot be read on the server. Instead this script
runs locally (where pandas/openpyxl are available), reuses the exact same
parsing logic as the polling bot (cpd.services.data_loader), and writes a single
``worker/data.json`` file. You upload that file to Cloudflare KV and the
Worker serves it.

Run it after staff update any file in ``data/``:

    pixi run export        # macOS/Linux
    .\\run.ps1 export      # Windows (after adding the task)

It deliberately skips live Google Sheets even when GS_ID_* are configured in
.env, because the Worker deployment is Excel-driven for now.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

# Force the Excel-only loading path (skip live Google Sheets) BEFORE the
# cpd.config module reads the environment. load_dotenv() never overrides keys
# that are already present in os.environ.
os.environ["GS_ID_R"] = ""
os.environ["GS_ID_C"] = ""

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from cpd.services.data_loader import CpdData  # noqa: E402

OUT_FILE = ROOT / "worker" / "data.json"


def main() -> None:
    data = CpdData()
    data.reload()

    payload = {
        "participants": [p.__dict__ for p in data.participants],
        "trainings": [t.__dict__ for t in data.trainings],
        "certificates": [c.__dict__ for c in data.certificates],
        "courses": [c.__dict__ for c in data.courses],
    }

    OUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    OUT_FILE.write_text(
        json.dumps(payload, ensure_ascii=False, indent=1),
        encoding="utf-8",
    )

    print(f"Wrote {OUT_FILE}")
    print(f"  participants : {len(payload['participants'])}")
    print(f"  trainings    : {len(payload['trainings'])}")
    print(f"  certificates : {len(payload['certificates'])}")
    print(f"  courses      : {len(payload['courses'])}")


if __name__ == "__main__":
    main()