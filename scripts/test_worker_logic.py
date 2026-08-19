"""Local sanity tests for worker/entry.py's pure logic (search + formatting).

Runs under a normal Python interpreter (no Cloudflare runtime). Verifies the
ported fuzzy search and report formatting behave like the original polling bot.

    python scripts/test_worker_logic.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "worker"))

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import entry  # noqa: E402

DATA_FILE = ROOT / "worker" / "data.json"


def load() -> entry.CpdData:
    return entry.CpdData(json.loads(DATA_FILE.read_text(encoding="utf-8")))


def check(label: str, cond: bool) -> None:
    status = "OK " if cond else "FAIL"
    print(f"[{status}] {label}")
    if not cond:
        raise SystemExit(1)


def main() -> None:
    print(f"IS_WORKER (expected False locally): {entry.IS_WORKER}")
    data = load()
    print(f"participants={len(data.participants)} trainings={len(data.trainings)} "
          f"certificates={len(data.certificates)} courses={len(data.courses)}")

    check("all_names not empty", len(data.all_names()) > 200)

    p = data.participants[0]
    print(f"first participant: {p.name!r} / {p.khmer_name!r} / {p.participant_id!r} / {p.phone!r}")

    found, shortlist = entry.search_all_fields(p.name, data)
    check("exact name resolves", found is not None and found.name == p.name)

    found2, _ = entry.search_all_fields(p.phone, data)
    check("phone resolves to same participant", found2 is not None and found2.participant_id == p.participant_id)

    found3, _ = entry.search_all_fields(p.participant_id, data)
    check("participant id resolves", found3 is not None)

    miss, short = entry.search_all_fields("zzzz no such person qqq", data)
    check("garbage query returns nothing", miss is None and not short)

    probe = data.trainings[0].participant_name if data.trainings else p.name
    f, _ = entry.search_all_fields(probe, data)
    if f is None:
        print(f"  (could not resolve training participant {probe!r} by name; using first participant)")
        f = p
    ts = data.trainings_for(f.participant_id, f.name, f.khmer_name)
    cs = data.certificates_for(f.participant_id, f.name, f.khmer_name)
    print(f"  {f.name}: trainings={len(ts)} certificates={len(cs)}")

    sections = entry.summary_sections(f, ts, cs)
    check("summary has >=3 sections", len(sections) >= 3)
    combined = "\n".join(sections)
    check("summary contains participant name", f.name in combined)
    check("summary is HTML-safe output", "<b>" in combined)
    check("summary not empty", len(combined) > 50)

    rep = entry.summary_report(f, ts, cs)
    check("summary_report non-empty", len(rep) > 50)
    trep = entry.training_report(f.name, ts)
    check("training_report non-empty", len(trep) > 20)
    crep = entry.certificate_report(f.name, cs)
    check("certificate_report non-empty", len(crep) > 20)

    courses_open = [c for c in data.courses if c.status.strip().lower() not in ("done", "completed", "ចប់")]
    print(f"open courses: {len(courses_open)}")

    links = {}
    class FakeEnv:
        TELEGRAM_BOT_TOKEN = "x"
        CPD_KV = None
    import asyncio

    async def fake_get(key):
        raw = json.dumps(links, ensure_ascii=False)
        return raw if key == "links" else None

    async def fake_put(key, value):
        links.clear()
        links.update(json.loads(value))

    env = FakeEnv()
    class KV:
        get = staticmethod(fake_get)
        put = staticmethod(fake_put)
    env.CPD_KV = KV()

    async def test_storage():
        await entry.link_account(env, 123, "Sokha Chan")
        got = await entry.get_linked_name(env, 123)
        check("link stored", got == "Sokha Chan")
        all_links = await entry.list_all_links(env)
        check("list links", all_links == {"123": "Sokha Chan"})
        await entry.unlink_account(env, 123)
        check("unlink works", await entry.get_linked_name(env, 123) is None)

    asyncio.run(test_storage())

    print("\nAll local logic tests passed.")


if __name__ == "__main__":
    main()