"""Renew the Bakong developer token and save it back into .env.

Run it manually (``pixi run python scripts/renew_bakong_token.py``) or let
the bot schedule it every BAKONG_TOKEN_RENEW_DAYS. Only needs the registered
email in .env (BAKONG_EMAIL) - no portal steps.
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from cpd.bakong_token import main  # noqa: E402


if __name__ == "__main__":
    raise SystemExit(main())
