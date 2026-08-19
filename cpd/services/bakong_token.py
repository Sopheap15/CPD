"""Bakong developer-token renewal.

Bakong Open API tokens are valid for ~90 days. Rather than pasting a fresh
token from the developer portal every time, this module renews it via the
official ``POST /v1/renew_token`` endpoint (which only needs the registered
email) and stores it back into ``.env`` so the bot keeps working across
restarts.

Typical usage::

    from cpd.services import bakong_token
    renewed, message = bakong_token.renew_if_due()
"""

from __future__ import annotations

import base64
import json
import time
import urllib.error
import urllib.request

from cpd.config import BAKONG_BASE_URL, BAKONG_EMAIL, BAKONG_TOKEN_RENEW_DAYS, BASE_DIR


def renew_token(email: str | None = None, base_url: str | None = None) -> str:
    """Request a fresh Bakong developer token for *email*.

    Raises ``ValueError`` if no email is configured or Bakong rejects the
    request. Returns the new JWT token string.
    """
    email = (email or BAKONG_EMAIL or "").strip()
    if not email:
        raise ValueError(
            "BAKONG_EMAIL is not set - add the email you registered at "
            "https://api-bakong.nbc.gov.kh/register to .env to enable "
            "automatic token renewal."
        )
    base_url = (base_url or BAKONG_BASE_URL or "").rstrip("/")
    payload = json.dumps({"email": email}).encode("utf-8")
    req = urllib.request.Request(
        f"{base_url}/v1/renew_token",
        data=payload,
        headers={"Content-Type": "application/json", "Accept": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=45) as resp:
            body = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:300]
        raise ValueError(f"Bakong renew_token HTTP {exc.code}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise ValueError(f"Bakong renew_token unreachable: {exc}") from exc

    if isinstance(body, dict) and body.get("responseCode") not in (None, 0, "0"):
        raise ValueError(
            f"Bakong renew_token failed: "
            f"{body.get('responseCode')} {body.get('responseMessage') or body}"
        )
    token = ""
    if isinstance(body, dict):
        token = str(body.get("token") or "").strip()
        if not token and isinstance(body.get("data"), dict):
            token = str(body["data"].get("token") or "").strip()
    if not token:
        raise ValueError(f"Bakong renew_token returned no token: {body!r}")
    return token


def token_expiry(token: str | None) -> float | None:
    """Return the JWT ``exp`` timestamp of *token*, or None if undecodable."""
    if not token:
        return None
    try:
        # JWT = header.payload.signature (payload is base64url, no padding).
        payload = token.split(".")[1]
        payload += "=" * (-len(payload) % 4)
        claims = json.loads(base64.urlsafe_b64decode(payload))
        exp = claims.get("exp")
        return float(exp) if exp is not None else None
    except Exception:  # noqa: BLE001 - not a JWT we can read
        return None


def days_until_expiry(token: str | None, now: float | None = None) -> float | None:
    """Days left until *token* expires (None when unknown/invalid)."""
    exp = token_expiry(token)
    if exp is None:
        return None
    return (exp - (now if now is not None else time.time())) / 86400.0


def write_token_to_env(token: str) -> None:
    """Replace the BAKONG_TOKEN= line in ``.env`` with *token*."""
    env_path = BASE_DIR / ".env"
    text = env_path.read_text(encoding="utf-8") if env_path.exists() else ""
    lines = text.splitlines()
    replaced = False
    for i, line in enumerate(lines):
        if line.strip().startswith("BAKONG_TOKEN"):
            lines[i] = f"BAKONG_TOKEN={token}"
            replaced = True
            break
    if not replaced:
        lines.append(f"BAKONG_TOKEN={token}")
    env_path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")


def renew_if_due(min_days: int | None = None) -> tuple[bool, str]:
    """Renew the Bakong token when missing or expiring within *min_days*.

    Returns ``(renewed, message)``. ``renewed`` is True when a new token was
    fetched and applied (in memory and written to ``.env``).
    """
    from cpd.services import payments

    min_days = min_days if min_days is not None else BAKONG_TOKEN_RENEW_DAYS
    current = payments.get_token()
    remaining = days_until_expiry(current)

    if remaining is not None and remaining > min_days:
        return False, f"Token valid for {remaining:.0f} more days - no renewal needed."

    try:
        token = renew_token()
    except ValueError as exc:
        return False, f"Renewal skipped: {exc}"

    payments.set_token(token)
    write_token_to_env(token)
    remaining = days_until_expiry(token)
    left = f"{remaining:.0f} days" if remaining is not None else "unknown"
    return True, f"Bakong token renewed (expires in ~{left})."


def main() -> int:
    """CLI entry point for the standalone renewal script."""
    from cpd.config import BAKONG_TOKEN_RENEW_DAYS

    renewed, message = renew_if_due()
    print(message)
    return 0 if renewed or "no renewal" in message else 1


if __name__ == "__main__":
    raise SystemExit(main())
