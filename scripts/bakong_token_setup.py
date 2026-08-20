"""One-time Bakong developer registration: request a code, verify it, save the token.

Bakong's ``renew_token`` endpoint only returns a token for emails that have
already completed the two-step registration. This script walks you through it:

    pixi run python scripts/bakong_token_setup.py

Step 1 asks Bakong to email a verification code to your address, step 2 swaps
that code for a JWT token, and the token is written into ``.env`` (BAKONG_TOKEN).
The bot's automatic renewal takes over from there.
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def main() -> int:
    from cpd.config import BAKONG_EMAIL
    from cpd.services import bakong_token
    from cpd.services import payments

    email = input(f"Registered email [{BAKONG_EMAIL or 'osopheap1@puthisastra.edu.kh'}]: ").strip() \
        or BAKONG_EMAIL or "osopheap1@puthisastra.edu.kh"

    print("\nStep 1 — asking Bakong to email a verification code...")
    try:
        message = bakong_token.request_token(
            email=email,
            organization=input("Organization name (e.g. Puthisastra): ").strip(),
            project=input("Project name (e.g. CPD Track): ").strip(),
        )
        print(f"Bakong: {message}")
    except ValueError as exc:
        print(f"\nRequest failed: {exc}")
        return 1

    code = input("\nPaste the verification code from the email: ").strip()
    if not code:
        print("No code entered - aborting.")
        return 1

    print("\nStep 2 — verifying the code and fetching your token...")
    try:
        token = bakong_token.verify_token(code)
    except ValueError as exc:
        print(f"\nVerification failed: {exc}")
        return 1

    bakong_token.write_token_to_env(token)
    payments.set_token(token)
    expiry = bakong_token.token_expiry(token)
    left = (expiry - __import__("time").time()) / 86400.0 if expiry else None
    print(f"\nToken saved to .env (expires in ~{left:.0f} days)." if left else
          "\nToken saved to .env.")
    print("Restart the bot (watchdog) to start automatic payment verification.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())