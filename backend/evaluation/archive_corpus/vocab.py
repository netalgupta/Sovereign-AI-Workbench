"""The fixed entity set every generator draws from.

Every name here already appears somewhere in MRPL_RAG_Test_Corpus, in
this repo's own tests, or in a teammate's tool description (the depot
names match Netal's row 60 exactly). Reusing them rather than inventing
per-document is what lets an incident report from 2022 and a
maintenance log from 2024 reference the same pump -- which is the only
way the graph gets edges instead of 500 isolated nodes.
"""

from __future__ import annotations

import random

YEARS = list(range(2020, 2027))  # 2020..2026 inclusive

UNITS = [
    "Hydrocracker-1", "Hydrocracker-2", "CCR-1", "CCR-2",
    "PSA-1", "PSA-2", "PSA-3", "LPG Merox", "Kero Merox",
    "Novolen (Gas-phase Ziegler-Natta)", "Aromatic Complex (MSEZ)",
]

# Equipment tags actually referenced elsewhere in this repo (FFC-201 is
# the feed controller from the fabricated-payload saga; TK-K-01/02/03
# are the tank farm from SAP_Mock_Materials_Master_Export.xlsx; D-102
# is the regeneration gas dryer from the boilerplate-detection commits).
EQUIPMENT = [
    "R-201", "R-101", "K-201", "FFC-201", "F-140-A",
    "TK-K-01", "TK-K-02", "TK-K-03", "D-102", "P-HS-02",
    "Beds 1-3", "Vacuum system",
]

DEPOTS = ["Kasargod", "Hindupur", "Hosur"]

# A small recurring cast, not a new name per document -- so "who signed
# off on this" has a consistent, checkable answer across years.
PERSONNEL = [
    ("R. Kamath", "Shift Supervisor"),
    ("A. Menon", "HSE Officer"),
    ("S. Bhat", "Process Engineer"),
    ("V. Shenoy", "Maintenance Lead"),
    ("D. Pai", "Inspection Engineer"),
    ("K. Rao", "Quality Control Officer"),
    ("N. Acharya", "Depot Coordinator"),
]

INCIDENT_KINDS = [
    "pressure drop and slow response", "H2S monitoring threshold exceedance",
    "pyrophoric catalyst handling deviation", "DCS alarm response delay",
    "regeneration gas dryer bed saturation", "vacuum system seal failure",
    "grade changeover checklist non-conformance", "tank calibration discrepancy",
]

SPEC_PARAMS = [
    ("Sulphur", "ppm", 10.0, 0.35),
    ("MFI", "g/10min", 3.4, 0.6),
    ("Hydrogen Purity", "%", 99.9, 0.15),
    ("WABT", "°C", 385.0, 12.0),
    ("Catalyst Bed dP", "kPa", 45.0, 6.0),
]


def rng_for(seed_key: str) -> random.Random:
    """A reproducible RNG keyed on a string.

    Same document description always produces the same synthetic
    numbers -- useful for re-running the generator without every file
    changing byte-for-byte, and for tests that check a specific value.
    """
    return random.Random(hash(seed_key) & 0xFFFFFFFF)


def synthetic_disclaimer() -> str:
    """The same disclaimer wording the existing corpus uses.

    Kept identical on purpose: the boilerplate detector
    (backend/ingestion/boilerplate.py) already knows how to find and
    strip this exact recurring sentence. A differently-worded disclaimer
    would just be a second boilerplate pattern nothing has been tuned
    against.
    """
    return (
        "This is a synthetic, illustrative document generated for "
        "RAG/retrieval testing purposes. It does not represent an actual "
        "MRPL record."
    )
