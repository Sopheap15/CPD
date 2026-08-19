"""Bakong KHQR payment generation and verification.

Generates a dynamic KHQR (amount locked) for a course fee, renders it to a
PNG image, and checks whether the participant has paid by polling Bakong's
``check_transaction_by_md5`` endpoint.

The bot itself cannot receive inbound webhooks (it runs behind a long-polling
Telegram connection on a local machine), so "automatic" payment confirmation is
implemented as background polling: a pending payment is registered with
:func:`track_payment` and a periodic job calls :func:`check_payment` until the
transaction is found or the timeout is reached.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field

from cpd.config import (
    BAKONG_ACCOUNT_ID,
    BAKONG_CURRENCY,
    BAKONG_MERCHANT_CITY,
    BAKONG_MERCHANT_NAME,
    BAKONG_TOKEN,
    BAKONG_PAYMENT_TIMEOUT_MINUTES,
)

# The developer token can be renewed at runtime (see cpd.bakong_token), so it
# is held in a module-level slot rather than read from config on every call.
_token = BAKONG_TOKEN or None

_khqr_lock = threading.Lock()
_khqr = None


def get_token() -> str | None:
    """Return the current Bakong developer token (may be renewed at runtime)."""
    return _token


def set_token(token: str | None) -> None:
    """Replace the Bakong developer token used for verification."""
    global _token, _khqr
    token = (token or "").strip() or None
    with _khqr_lock:
        _token = token
        _khqr = None  # force the KHQR client to rebuild with the new token


def _get_khqr():
    """Return a shared KHQR instance (created lazily)."""
    global _khqr
    with _khqr_lock:
        if _khqr is None:
            from bakong_khqr import KHQR

            _khqr = KHQR(_token)
        return _khqr


def _qr_merchant_name(course) -> str:
    """Merchant name shown on the QR: the course title (max 25 chars).

    Falls back to the configured merchant name when the course has no title.
    """
    name = (course.title or BAKONG_MERCHANT_NAME or "").strip()
    if len(name) > 25:
        cut = name[:25].rfind(" ")
        name = name[:cut] if cut > 0 else name[:25]
    return name.rstrip()


@dataclass
class PendingPayment:
    """A payment we are waiting for."""

    md5: str
    bill_number: str
    chat_id: int
    telegram_id: int
    course_id: str
    course_title: str
    amount: float
    created_at: float = field(default_factory=time.time)
    user_data: dict = field(default_factory=dict)


# chat_id -> PendingPayment, tracked while the bot polls Bakong.
_pending: dict[int, PendingPayment] = {}
_pending_lock = threading.Lock()


def payment_enabled() -> bool:
    """True when Bakong automatic verification is fully configured."""
    return bool(BAKONG_ACCOUNT_ID and _token)


def qr_enabled() -> bool:
    """True when a KHQR code can be generated (merchant account set).

    The developer token is only needed to *verify* a payment; the QR image
    itself can be produced without it.
    """
    return bool(BAKONG_ACCOUNT_ID)


def can_verify() -> bool:
    """True when payment status can be checked automatically."""
    return bool(_token)


def create_payment(chat_id: int, telegram_id: int, course,
                   participant=None, user_data: dict | None = None) -> PendingPayment | None:
    """Create a dynamic KHQR for a course fee.

    Returns a :class:`PendingPayment` with the generated QR image path, or
    ``None`` if the merchant isn't configured or the course has no fee.
    """
    fee = float(course.fee or 0)
    if not qr_enabled() or fee <= 0:
        return None

    bill_number = (f"CPD{course.course_id}-{telegram_id}-"
                   f"{int(time.time()) % 1000000}")
    khqr = _get_khqr()

    qr = khqr.create_qr(
        account_id=BAKONG_ACCOUNT_ID,
        merchant_name=_qr_merchant_name(course),
        merchant_city=BAKONG_MERCHANT_CITY,
        amount=fee,
        currency=BAKONG_CURRENCY,
        store_label=course.course_id,
        bill_number=bill_number,
        static=False,
        expiration=1,
    )
    md5 = khqr.generate_md5(qr)
    image_path = khqr.qr_image(qr, format="png")

    pending = PendingPayment(
        md5=md5,
        bill_number=bill_number,
        chat_id=chat_id,
        telegram_id=telegram_id,
        course_id=course.course_id,
        course_title=course.title,
        amount=fee,
        user_data=user_data or {},
    )
    pending.user_data["qr_image_path"] = image_path
    pending.user_data["qr_md5"] = md5
    pending.user_data["bill_number"] = bill_number
    pending.user_data["can_verify"] = can_verify()

    with _pending_lock:
        _pending[chat_id] = pending
    return pending


def get_pending(chat_id: int) -> PendingPayment | None:
    with _pending_lock:
        return _pending.get(chat_id)


def drop_payment(chat_id: int) -> None:
    with _pending_lock:
        _pending.pop(chat_id, None)


def check_payment(chat_id: int) -> bool:
    """Poll Bakong for the pending payment of *chat_id*.

    Returns True only once the transaction is confirmed as paid. On a
    successful payment the pending entry is removed.
    """
    pending = get_pending(chat_id)
    if pending is None:
        return False
    if not can_verify():
        return False
    try:
        status = _get_khqr().check_payment(pending.md5)
    except Exception:  # noqa: BLE001 - network hiccup: treat as unpaid
        return False
    if status == "PAID":
        drop_payment(chat_id)
        return True
    return False


def payment_expired(chat_id: int, now: float | None = None) -> bool:
    """True when the pending payment has outlived the configured timeout."""
    pending = get_pending(chat_id)
    if pending is None:
        return True
    now = now if now is not None else time.time()
    return (now - pending.created_at) > (BAKONG_PAYMENT_TIMEOUT_MINUTES * 60)


def poll_ready_payments() -> list[PendingPayment]:
    """Return all pending payments that have been confirmed as paid.

    Used by the background job: payments returned here are finalised (the
    participant is registered + offered the group join).
    """
    with _pending_lock:
        chat_ids = list(_pending.keys())
    paid = []
    for chat_id in chat_ids:
        if check_payment(chat_id):
            p = get_pending(chat_id)
            if p is not None:
                paid.append(p)
    return paid