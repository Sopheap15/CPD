"""Receipt verification using local OCR (Tesseract).

KHQR receipts (from ABA, ACLEDA, Wing, etc.) show the RECIPIENT NAME,
not the destination account number. We verify by checking:
  1. The recipient name (or account number as fallback).
  2. The expected fee amount appears as an actual monetary value.
  3. The receipt reference has not been used before (anti-replay).

Configure via .env:
  ABA_MERCHANT_NAME  = SOPHEAP OENG   ← name shown under "To Account"
  ABA_ACCOUNT_NUMBER = 002370133      ← fallback for direct-transfer receipts
"""
import os
import re
import logging
from pathlib import Path

import cv2
import numpy as np
from PIL import Image
import pytesseract

from cpd.services.registrations import has_payment_ref

logger = logging.getLogger(__name__)

# Cap the longest side before OCR. Tesseract runtime explodes with image
# size; anything above this adds seconds without improving accuracy.
MAX_OCR_SIDE = 2000

# Configure Tesseract path for Windows users
if os.name == "nt":
    # Try common Windows install paths
    _tess_candidates = [
        r"C:\Program Files\Tesseract-OCR\tesseract.exe",
        r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
        r"C:\Users\osopheap\AppData\Local\Programs\Tesseract-OCR\tesseract.exe",
    ]
    for _p in _tess_candidates:
        if os.path.exists(_p):
            pytesseract.pytesseract.tesseract_cmd = _p
            logger.info("Tesseract found at: %s", _p)
            break
    else:
        logger.warning(
            "Tesseract-OCR not found in common locations on Windows. "
            "Install it from https://github.com/UB-Mannheim/tesseract/wiki "
            "or run: .\\run.ps1 install"
        )

ABA_MERCHANT_NAME = os.environ.get("ABA_MERCHANT_NAME", "").strip()
ABA_ACCOUNT_NUMBER = os.environ.get("ABA_ACCOUNT_NUMBER", "002370133").strip()

def is_duplicate_receipt(ref: str) -> bool:
    """Return True if this reference was already used for a successful payment."""
    if not ref:
        return False
    return has_payment_ref(ref)


# ── Text helpers ───────────────────────────────────────────────────────────────

def _clean(text: str) -> str:
    """Strip spaces/newlines/commas and lowercase for flexible matching."""
    return text.replace(" ", "").replace("\n", "").replace(",", "").lower()


def _extract_reference(text: str) -> str | None:
    """Extract the transaction reference number from OCR text.

    Looks for patterns printed on KHQR/ABA receipts such as:
      External Txn Ref : eb30ea2d
      Reference No.    : 62324148054
    Returns the longest ref found, or None.
    """
    patterns = [
        # "External Txn Ref : eb30ea2d"
        r"external\s*txn\s*ref\s*[:\.]?\s*([a-z0-9]{6,})",
        # "Reference No. : 62324148054"  or  "Reference No 162324148054"
        r"reference\s*no\.?\s*[:\.]?\s*([a-z0-9]{6,})",
        # "Ref No : ..."
        r"ref\s*no\.?\s*[:\.]?\s*([a-z0-9]{6,})",
        # "Transaction ID : ..."
        r"transaction\s*(?:id|ref)\s*[:\.]?\s*([a-z0-9]{6,})",
    ]
    t = re.sub(r"\s+", " ", text.lower())
    found = []
    for pat in patterns:
        m = re.search(pat, t)
        if m:
            found.append(m.group(1).strip())
    if not found:
        return None
    # Return the longest reference (most unique / least likely to collide)
    return max(found, key=len)


def _extract_amounts(text: str) -> set[float]:
    """Extract all monetary values from OCR text.

    Only looks for numbers in a clear financial context (near $, USD, labels).
    """
    amounts: set[float] = set()
    t = re.sub(r"\s+", " ", text.lower())

    patterns = [
        r"\$\s*(\d{1,7}(?:[.,]\d{1,2})?)",
        r"(\d{1,7}(?:[.,]\d{1,2})?)\s*\$",
        r"(\d{1,7}(?:[.,]\d{1,2})?)\s*usd",
        r"usd\s*(\d{1,7}(?:[.,]\d{1,2})?)",
        r"debit\s*amount\s*[:\-]*\s*-?\s*(\d{1,7}(?:[.,]\d{1,2})?)",
        r"\bamount\s*[:\-]\s*(\d{1,7}(?:[.,]\d{1,2})?)",
        r"[—\-]\s*(\d{1,7}[.,]\d{2})\s*(?:\$|usd|khr)?",
    ]
    for pat in patterns:
        for m in re.findall(pat, t):
            try:
                val = float(m.replace(",", "."))
                if val > 0:
                    amounts.add(round(val, 2))
            except ValueError:
                pass
    return amounts


def _ocr_image(image_path: str) -> str:
    """Run Tesseract OCR on an image file, with OpenCV pre-processing fallback.

    Always operates on a *copy* of the pixel data so the file handle is never
    held open when pytesseract spawns the Tesseract subprocess — important on
    Windows where open file handles block child-process access.
    """
    # Read image bytes into memory first, then close the file.
    img_arr = np.frombuffer(Path(image_path).read_bytes(), dtype=np.uint8)
    bgr = cv2.imdecode(img_arr, cv2.IMREAD_COLOR)
    if bgr is None:
        raise ValueError(f"cv2 could not decode image: {image_path}")

    # Downscale very large photos (e.g. full-resolution phone cameras or
    # document scans) so OCR stays within the handler's timeout budget.
    h, w = bgr.shape[:2]
    if max(h, w) > MAX_OCR_SIDE:
        scale = MAX_OCR_SIDE / max(h, w)
        bgr = cv2.resize(
            bgr,
            (int(w * scale), int(h * scale)),
            interpolation=cv2.INTER_AREA,
        )

    # Try once with the raw image
    pil_img = Image.fromarray(cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB))
    text = pytesseract.image_to_string(pil_img)

    # If OCR yield is too low, pre-process with grayscale + Otsu threshold
    if len(text.strip()) < 20:
        gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
        _, thresh = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        text = pytesseract.image_to_string(Image.fromarray(thresh))

    return text


# ── Main verification ──────────────────────────────────────────────────────────

def verify_receipt(
    image_path: str, expected_amount: float
) -> tuple[bool, str, str | None]:
    """Verify an uploaded ABA/KHQR receipt image using local OCR.

    Checks:
      1. Recipient name OR account number is present on the receipt.
      2. The expected fee amount appears as an actual monetary value.
      3. The receipt reference has not already been used.

    Returns:
      (success: bool, message_in_khmer: str, ref_number: str | None)

    The handler must record the registration in the CSV using the returned reference
    upon success to prevent future replay attacks.
    """
    try:
        text = _ocr_image(image_path)
    except Exception as exc:
        # Surface the real error (e.g. TesseractNotFoundError) so the caller
        # can display it to the admin instead of a vague "clearer photo" msg.
        logger.error("OCR failed: %s", exc, exc_info=True)
        raise

    logger.debug("OCR raw text:\n%s", text)
    text_clean = _clean(text)

    # ── Extract reference number ───────────────────────────────────────
    ref = _extract_reference(text)
    logger.debug("Receipt reference extracted: %s", ref)

    # ── Duplicate check ────────────────────────────────────────────────
    if ref and is_duplicate_receipt(ref):
        return (
            False,
            f"❌ វិកាយបត្រនេះធ្លាប់ត្រូវបានប្រើរួចហើយ (Ref: {ref})។ "
            "សូមផ្ញើវិកាយបត្រផ្សេង ឬទាក់ទងអ្នករៀបចំ។",
            ref,
        )

    # ── Recipient check ────────────────────────────────────────────────
    recipient_ok = False
    if ABA_MERCHANT_NAME:
        words = [w for w in ABA_MERCHANT_NAME.upper().split() if len(w) > 1]
        recipient_ok = all(_clean(w) in text_clean for w in words)

    if not recipient_ok:
        acc = re.sub(r"\D", "", ABA_ACCOUNT_NUMBER)
        acc_pattern = "".join(
            f"(?:{d}|{'o' if d == '0' else 'l' if d == '1' else 'z' if d == '2' else d})"
            for d in acc
        )
        recipient_ok = bool(re.search(acc_pattern, text_clean))

    if not recipient_ok:
        dest = ABA_MERCHANT_NAME or ABA_ACCOUNT_NUMBER
        return (
            False,
            f"❌ គណនីទទួលប្រាក់មិនត្រឹមត្រូវ។ "
            f"សូមបង់ទៅ {dest} ហើយបញ្ចូលវិកាយបត្រនោះ។",
            ref,
        )

    # ── Amount check ───────────────────────────────────────────────────
    found_amounts = _extract_amounts(text)
    logger.debug("Amounts on receipt: %s  expected: %.2f", found_amounts, expected_amount)

    if round(expected_amount, 2) not in found_amounts:
        return (
            False,
            f"❌ ចំនួនទឹកប្រាក់មិនត្រូវគ្នា។ "
            f"រកមិនឃើញ ${expected_amount:.2f} នៅក្នុងវិកាយបត្រ។",
            ref,
        )

    return True, "✅ ការបង់ប្រាក់បានផ្ទៀងផ្ទាត់ដោយជោគជ័យ!", ref
