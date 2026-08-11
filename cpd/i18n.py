"""Lightweight bilingual (English / Khmer) message helper.

Every message is defined with an English and a Khmer version.
``t()`` returns both, joined so the bot shows EN then KH side by side.
"""

from __future__ import annotations

# Each entry: key -> (english, khmer)
TRANSLATIONS: dict[str, tuple[str, str]] = {
    "welcome": (
        "Welcome! What can I help you with?",
        "សូមស្វាគមន៍! តើមានអ្វីដែលខ្ញុំអាចជួយអ្នកបានទេ?",
    ),
    "ask_name": (
        "Please enter your full name to view your CPD history (e.g. Sokha Chan).",
        "សូមបញ្ចូលឈ្មោះពេញរបស់អ្នកដើម្បីមើលប្រវត្តិ CPD (ឧទាហរណ៍៖ សុខា ចាន់ / Sokha Chan)។",
    ),
    "cancel": ("Search cancelled.", "បានលុបចោលការស្វែងរក។"),
    "cancel_hint": (
        "You can send /cancel at any time to stop.",
        "អ្នកអាចផ្ញើ /cancel បានគ្រប់ពេល ដើម្បីបញ្ឈប់។",
    ),
    "not_found": (
        "No participant found with the name \"{name}\".\n"
        "Please check the spelling, or try your family name only (e.g. \"Chan\").",
        "រកមិនឃើញអ្នកចូលរួមដែលមានឈ្មោះ \"{name}\" ទេ។\n"
        "សូមពិនិត្យអក្ខរាវិរុទ្ធ ឬសាកល្បងតែគោត្តនាម (ឧ. \"ចាន់ / Chan\")។",
    ),
    "multiple_matches": (
        "I found {count} participants with a similar name. Please choose one:",
        "ខ្ញុំបានរកឃើញអ្នកចូលរួម {count} នាក់ដែលមានឈ្មោះប្រហាក់ប្រហែល។ សូមជ្រើសរើសមួយ៖",
    ),
    "section_training": ("Training History", "ប្រវត្តិបណ្ដុះបណ្ដាល"),
    "section_certificate": ("CPD Certificate Pickup", "ការទទួលវិញ្ញាបនបត្រ CPD"),
    "section_summary": ("Summary", "សង្ខេប"),
    "no_training": (
        "No training records found for this participant.",
        "រកមិនឃើញប្រវត្តិបណ្ដុះបណ្ដាលសម្រាប់អ្នកចូលរួមរូបនេះទេ។",
    ),
    "no_certificate": (
        "No certificate pickup records found for this participant.",
        "រកមិនឃើញប្រវត្តិវិញ្ញាបនបត្រសម្រាប់អ្នកចូលរួមរូបនេះទេ។",
    ),
    "picked_up": ("Picked up", "បានទទួល"),
    "not_picked_up": ("Not picked up", "មិនទាន់ទទួល"),
    "not_applicable": ("-", "-"),
    "help": (
        "Commands:\n"
        "/start - Start a new search\n"
        "/help - Show this help\n"
        "/cancel - Cancel the current search\n\n"
        "Just send your name at any time and I will show your CPD history.",
        "ពាក្យបញ្ជា៖\n"
        "/start - ចាប់ផ្ដើមការស្វែងរកថ្មី\n"
        "/help - បង្ហាញជំនួយនេះ\n"
        "/cancel - បោះបង់ការស្វែងរកបច្ចុប្បន្ន\n\n"
        "គ្រាន់តែផ្ញើឈ្មោះរបស់អ្នកណាមួយ ខ្ញុំនឹងបង្ហាញប្រវត្តិ CPD របស់អ្នក។",
    ),
    "search_again": ("Search another name", "ស្វែងរកឈ្មោះផ្សេងទៀត"),
    "done": (
        "Thank you! You can start a new search any time with /start.",
        "សូមអរគុណ! អ្នកអាចចាប់ផ្ដើមការស្វែងរកថ្មីនៅពេលណាក៏បានដោយផ្ញើ /start។",
    ),
    "menu_title": (
        "What would you like to see?",
        "តើអ្នកចង់មើលអ្វី?",
    ),
    "error": (
        "Sorry, something went wrong. Please try again later.",
        "សូមទោស មានបញ្ហាអ្វីមួយកើតឡើង។ សូមព្យាយាមម្ដងទៀតនៅពេលក្រោយ។",
    ),
    "loading_error": (
        "The CPD data files could not be loaded. Please contact the administrator.",
        "មិនអាចផ្ទុកឯកសារទិន្នន័យ CPD បានទេ។ សូមទាក់ទងអ្នកគ្រប់គ្រង។",
    ),
    "further_info": (
        "For further information, please contact CPD officer Eng Sophanith (+855 98 448 619).",
        "សម្រាប់ព័ត៌មានបន្ថែម សូមទាក់ទងបុគ្គលិក CPD លោក អៀង សុផានិត (Telegram: +855 98 448 619)។",
    ),
}

DEFAULT_LANG = "en"


def t(key: str) -> str:
    """Return the Khmer string for *key*."""
    pair = TRANSLATIONS.get(key)
    if pair is None:
        raise KeyError(f"Unknown translation key: {key}")
    _, kh = pair
    return kh


def inline(key: str, **kwargs) -> str:
    """Return the Khmer string for *key*."""
    pair = TRANSLATIONS.get(key)
    if pair is None:
        raise KeyError(f"Unknown translation key: {key}")
    _, kh = pair
    return kh.format(**kwargs)


def fmt(key: str, **kwargs) -> str:
    """Return the Khmer string formatted with the given keyword args."""
    pair = TRANSLATIONS.get(key)
    if pair is None:
        raise KeyError(f"Unknown translation key: {key}")
    _, kh = pair
    return kh.format(**kwargs)