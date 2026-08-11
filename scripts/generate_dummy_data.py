"""Generates dummy CPD data (.xlsx files) for development and testing.

Run:  python scripts/generate_dummy_data.py
Output: data/participants.xlsx, data/trainings.xlsx, data/certificate_pickup.xlsx
"""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path
from random import Random

import pandas as pd

DATA_DIR = Path(__file__).resolve().parent.parent / "data"

rng = Random(42)

FIRST_NAMES = [
    "Sokha", "Dara", "Vireak", "Sreynich", "Ratha", "Kolab", "Vicheka",
    "Sovann", "Channary", "Phalla", "Raksmey", "Bopha", "Serey", "Bunthoeun",
    "Malis", "Sophea", "Vathana", "Sreypov",
]
LAST_NAMES = [
    "Chan", "Sok", "Kim", "Heng", "Meas", "Ly", "Chea", "Sao", "Ouk",
    "Tep", "Nuon", "Phan", "Yin", "Neang", "Khun", "Vann",
]
PROFESSIONS = ["Pharmacist", "Nurse", "Doctor", "Medical Technologist", "Midwife"]
DEPARTMENTS = ["Pharmacy", "Internal Medicine", "Pediatrics", "Laboratory", "Obstetrics"]

TRAININGS = [
    ("Antimicrobial Stewardship in Practice", 2.0, 8),
    ("Basic Cardiac Life Support (BCLS)", 3.0, 12),
    ("COVID-19 Vaccine Handling & Storage", 1.5, 6),
    ("Pharmacy Law and Ethics Update", 2.0, 8),
    ("Diabetes Management Essentials", 2.5, 10),
    ("Infection Prevention and Control", 2.0, 8),
    ("Pediatric Emergency Triage", 3.0, 12),
    ("Inventory Management for Pharmacies", 1.0, 4),
    ("Communication Skills in Health Care", 1.5, 6),
    ("Patient Safety and Medication Errors", 2.0, 8),
    ("Maternal Health and Safe Delivery", 3.0, 12),
    ("Laboratory QC and Quality Assurance", 2.5, 10),
    ("First Aid and Emergency Response", 2.0, 8),
    ("Ethics in Clinical Research", 1.0, 4),
    ("Nutrition in Chronic Disease", 1.5, 6),
]
ORGANIZERS = ["MoH Cambodia", "National Institute of Public Health", "Pharmacy Council", "WHO Cambodia", "Local Training Center"]


def gen_participants(n: int) -> pd.DataFrame:
    rows = []
    for i in range(1, n + 1):
        first = rng.choice(FIRST_NAMES)
        last = rng.choice(LAST_NAMES)
        rows.append(
            {
                "id": f"P{i:03d}",
                "name": f"{first} {last}",
                "khmer_name": "",
                "profession": rng.choice(PROFESSIONS),
                "department": rng.choice(DEPARTMENTS),
                "email": f"{first.lower()}.{last.lower()}@example.com",
                "phone": f"0{rng.randint(11, 99)} {rng.randint(100, 999)} {rng.randint(100, 999)}",
            }
        )
    # Ensure a few known names exist for easy manual testing.
    rows[0]["name"] = "Sokha Chan"
    rows[1]["name"] = "Dara Sok"
    rows[2]["name"] = "Channary Kim"
    return pd.DataFrame(rows)


def gen_trainings(participants: pd.DataFrame) -> pd.DataFrame:
    rows = []
    t_id = 1
    for _, p in participants.iterrows():
        count = rng.randint(2, 5)
        chosen = rng.sample(TRAININGS, count)
        base_date = date(2023, 1, 15)
        for title, points, hours in chosen:
            offset = rng.randint(0, 900)
            rows.append(
                {
                    "id": f"T{t_id:04d}",
                    "participant_id": p["id"],
                    "participant_name": p["name"],
                    "title": title,
                    "date": (base_date + timedelta(days=offset)).isoformat(),
                    "organizer": rng.choice(ORGANIZERS),
                    "cpd_points": points,
                    "hours": hours,
                    "status": "Completed",
                }
            )
            t_id += 1
    return pd.DataFrame(rows)


def gen_certificates(trainings: pd.DataFrame) -> pd.DataFrame:
    rows = []
    c_id = 1
    for _, tr in trainings.iterrows():
        if rng.random() < 0.85:
            issued = date.fromisoformat(tr["date"]) + timedelta(days=rng.randint(7, 30))
            picked = rng.random() < 0.65
            rows.append(
                {
                    "id": f"C{c_id:04d}",
                    "participant_id": tr["participant_id"],
                    "participant_name": tr["participant_name"],
                    "training_title": tr["title"],
                    "certificate_number": f"CPD-{2023 + rng.randint(0, 2)}-{c_id:04d}",
                    "issued_date": issued.isoformat(),
                    "picked_up": "Yes" if picked else "No",
                    "pickup_date": (issued + timedelta(days=rng.randint(1, 20))).isoformat() if picked else "",
                    "pickup_by": rng.choice(
                        ["Admin", "HR Office", "Training Coordinator"]
                    ) if picked else "",
                }
            )
            c_id += 1
    return pd.DataFrame(rows)


def main() -> None:
    DATA_DIR.mkdir(exist_ok=True)

    participants = gen_participants(18)
    trainings = gen_trainings(participants)
    certificates = gen_certificates(trainings)

    participants.to_excel(DATA_DIR / "participants.xlsx", index=False)
    trainings.to_excel(DATA_DIR / "trainings.xlsx", index=False)
    certificates.to_excel(DATA_DIR / "certificate_pickup.xlsx", index=False)

    print(f"Wrote {len(participants)} participants, {len(trainings)} trainings, "
          f"{len(certificates)} certificates to {DATA_DIR}")


if __name__ == "__main__":
    main()