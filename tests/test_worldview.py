#!/usr/bin/env python3
"""Prueft die Informationsgrenze zwischen den Agenten.

Die wichtigste Sicherheitseigenschaft des Aufbaus: ein Agent darf die private
Notiz eines anderen nie sehen. Durchgesetzt wird das beim Zuschnitt der Sicht
(worldview.build_view), nicht im Prompt — ein Prompt kann sich verplappern.

    python3 tests/test_worldview.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from worldview import Message, TurnRecord, build_view, render_view  # noqa: E402

SEATS = ["FRA", "DEU", "CHN"]
SECRET = "GEHEIM-DEU-WILL-FRA-HINTERGEHEN"

STATE = {
    "year": 2016, "month": 3,
    "countries": {
        "FRA": {"id": "FRA", "name": "France", "leader": "Hollande", "ideology": "lib",
                "stability": 74,
                "economy": {"gdp": 2466.0, "gdp_growth": 1.1, "unemployment": 10.0,
                            "debt_pct_gdp": 96.2},
                "military": {"strength": 7, "active_personnel": 205000,
                             "nuclear_weapons": True, "equipment": {"drones": 120}},
                "national_stats": {"sovereignty": 90},
                "relations": {"DEU": 82, "CHN": 30},
                "at_war_with": [], "sanctions_by": [], "alliances": ["NATO"]},
        "DEU": {"id": "DEU", "name": "Germany", "leader": "Merkel", "ideology": "lib",
                "stability": 83, "economy": {"gdp": 3400.0},
                "military": {"strength": 6, "nuclear_weapons": False},
                "relations": {"FRA": 82}, "at_war_with": [], "alliances": ["NATO"]},
        "CHN": {"id": "CHN", "name": "China", "leader": "Xi", "ideology": "soc",
                "stability": 51, "economy": {"gdp": 11000.0},
                "military": {"strength": 9, "nuclear_weapons": True},
                "relations": {"FRA": 30}, "at_war_with": [], "alliances": []},
    },
    "recent_events": [], "domestic_events": [], "treaties": [],
}


def main() -> int:
    ok = True

    def check(label: str, cond: bool, detail: str = "") -> None:
        nonlocal ok
        ok &= cond
        print(f"  [{'ok ' if cond else 'FAIL'}] {label}" + (f" — {detail}" if detail else ""))

    deu_history = [TurnRecord(round=1, public_action="Handelsabkommen anbieten",
                              private_note=SECRET, outcome="ok")]
    inbox = [Message(sender="DEU", recipient="FRA",
                     content="Wir sichern euch Kooperation zu.", round=1)]

    fra = render_view(build_view(STATE, "FRA", SEATS, 2, history=[], inbox=inbox))
    deu = render_view(build_view(STATE, "DEU", SEATS, 2, history=deu_history, inbox=[]))

    print("Pruefungen:")
    check("DEU sieht die eigene private Notiz", SECRET in deu)
    check("FRA sieht die private Notiz von DEU NICHT", SECRET not in fra)
    check("FRA erhaelt die Nachricht von DEU im Postfach",
          "Wir sichern euch Kooperation zu." in fra)
    check("FRA sieht die Rivalen mit beiden Beziehungsrichtungen",
          "sie→du" in fra and "Germany" in fra and "China" in fra)
    check("eigene Nation ist nicht in der Rivalenliste",
          fra.count("France (FRA)") == 1)

    print("\nOK — Informationsgrenze haelt." if ok else "\nFEHLGESCHLAGEN")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
