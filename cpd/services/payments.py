"""Payment tracking module.

Tracks pending payments in memory while the user is uploading a receipt screenshot.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field

@dataclass
class PendingPayment:
    """A payment we are waiting for the user to upload a receipt for."""
    bill_number: str
    chat_id: int
    telegram_id: int
    course_id: str
    course_title: str
    amount: float
    created_at: float = field(default_factory=time.time)
    user_data: dict = field(default_factory=dict)


# chat_id -> PendingPayment, tracked while waiting for receipt upload
_pending: dict[int, PendingPayment] = {}
_pending_lock = threading.Lock()


def create_payment(chat_id: int, telegram_id: int, course,
                   participant=None, user_data: dict | None = None) -> PendingPayment | None:
    """Track a new pending payment."""
    fee = float(course.fee or 0)
    if fee <= 0:
        return None

    bill_number = (f"CPD{course.course_id}-{telegram_id}-"
                   f"{int(time.time()) % 1000000}")
    
    pending = PendingPayment(
        bill_number=bill_number,
        chat_id=chat_id,
        telegram_id=telegram_id,
        course_id=course.course_id,
        course_title=course.title,
        amount=fee,
        user_data=user_data or {},
    )
    pending.user_data["bill_number"] = bill_number

    with _pending_lock:
        _pending[chat_id] = pending
    return pending


def get_pending(chat_id: int) -> PendingPayment | None:
    """Retrieve the pending payment for a chat ID."""
    with _pending_lock:
        return _pending.get(chat_id)


def drop_payment(chat_id: int) -> None:
    """Remove a pending payment."""
    with _pending_lock:
        _pending.pop(chat_id, None)


def payment_expired(chat_id: int, now: float | None = None) -> bool:
    """True when the pending payment has outlived a 30-minute timeout."""
    pending = get_pending(chat_id)
    if pending is None:
        return True
    now = now if now is not None else time.time()
    return (now - pending.created_at) > (30 * 60)