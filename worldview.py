"""Verdichtet den Phos-Weltzustand zu dem, was ein Agent tatsächlich sehen darf.

Zwei Aufgaben, die zusammengehören:

1. **Token-Budget.** ``GET /api/game/{sid}`` liefert 160 Nationen mit vollem
   Datensatz. Ungefiltert ist das pro Runde und Agent unbezahlbar.
2. **Informationsgrenze.** Ein Agent darf die privaten Notizen der anderen nie
   sehen. Der Zuschnitt hier ist die Stelle, an der das durchgesetzt wird —
   nicht der Prompt, der sich verplappern kann.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

# Grossmaechte, die als Kulisse sichtbar bleiben, auch wenn kein Agent sie steuert.
DEFAULT_BACKDROP = ("USA", "CHN", "RUS", "DEU", "GBR", "FRA", "IND", "JPN")
MAX_BACKDROP = 6
MAX_RELATIONS = 12
MAX_WORLD_EVENTS = 8
MAX_OWN_EVENTS = 5
MAX_HISTORY = 6


@dataclass
class Message:
    """Öffentliche Nachricht von einer Agentennation an eine andere."""

    sender: str
    recipient: str
    content: str
    round: int

    def to_dict(self) -> dict:
        return {"sender": self.sender, "recipient": self.recipient,
                "content": self.content, "round": self.round}


@dataclass
class TurnRecord:
    """Was eine Nation in einer vergangenen Runde getan hat — aus ihrer eigenen Sicht."""

    round: int
    public_action: str
    private_note: str = ""
    outcome: str = ""
    messages_sent: list[dict] = field(default_factory=list)


def _country_brief(c: dict, viewer_relations: dict | None = None) -> dict:
    """Kompakter Steckbrief einer fremden Nation."""
    eco = c.get("economy") or {}
    mil = c.get("military") or {}
    brief = {
        "id": c.get("id"),
        "name": c.get("name"),
        "leader": c.get("leader"),
        "ideology": c.get("ideology"),
        "stability": c.get("stability"),
        "gdp_bn": eco.get("gdp"),
        "military_strength": mil.get("strength"),
        "nuclear": mil.get("nuclear_weapons"),
        "at_war_with": c.get("at_war_with") or [],
        "alliances": c.get("alliances") or [],
    }
    if viewer_relations is not None:
        brief["relation_to_you"] = (c.get("relations") or {}).get(
            viewer_relations.get("_self_id", "")
        )
    return brief


def build_view(
    state: dict,
    country_id: str,
    seats: list[str],
    round_no: int,
    history: list[TurnRecord] | None = None,
    inbox: list[Message] | None = None,
    backdrop: tuple[str, ...] = DEFAULT_BACKDROP,
) -> dict:
    """Baut die Sicht **einer** Nation auf die Welt.

    Enthält nie die privaten Notizen anderer Nationen — ``history`` ist immer
    die eigene.
    """
    countries: dict = state.get("countries") or {}
    me = countries.get(country_id) or {}
    my_relations: dict = me.get("relations") or {}

    # Rivalen: die anderen agentengesteuerten Nationen. Immer vollständig sichtbar,
    # denn gegen die wird gespielt.
    rivals = []
    for cid in seats:
        if cid == country_id or cid not in countries:
            continue
        other = countries[cid]
        rivals.append({
            **_country_brief(other),
            "your_relation_to_them": my_relations.get(cid),
            "their_relation_to_you": (other.get("relations") or {}).get(country_id),
        })

    # Kulisse: grosse Nationen ohne Agent, damit die Welt nicht leer wirkt.
    backdrop_ids = [c for c in backdrop if c not in seats and c in countries][:MAX_BACKDROP]
    backdrop_view = [
        {**_country_brief(countries[c]), "your_relation_to_them": my_relations.get(c)}
        for c in backdrop_ids
    ]

    # Stärkste und schwächste Beziehungen — verrät Bündnisse und Konflikte.
    ranked = sorted(
        ((cid, v) for cid, v in my_relations.items() if cid in countries),
        key=lambda kv: kv[1],
    )
    notable_relations = {
        countries[cid]["name"]: v
        for cid, v in (ranked[:MAX_RELATIONS // 2] + ranked[-MAX_RELATIONS // 2:])
    }

    eco = me.get("economy") or {}
    mil = me.get("military") or {}
    return {
        "round": round_no,
        "date": f"{state.get('year')}-{state.get('month'):02d}",
        "you": {
            "id": country_id,
            "name": me.get("name"),
            "leader": me.get("leader"),
            "government": me.get("government_type"),
            "ideology": me.get("ideology"),
            "stability": me.get("stability"),
            "economy": {
                "gdp_bn": eco.get("gdp"),
                "gdp_growth": eco.get("gdp_growth"),
                "unemployment": eco.get("unemployment"),
                "debt_pct_gdp": eco.get("debt_pct_gdp"),
            },
            "military": {
                "strength": mil.get("strength"),
                "active_personnel": mil.get("active_personnel"),
                "nuclear_weapons": mil.get("nuclear_weapons"),
                "equipment": mil.get("equipment"),
            },
            "national_stats": me.get("national_stats"),
            "at_war_with": me.get("at_war_with") or [],
            "sanctions_by": me.get("sanctions_by") or [],
            "alliances": me.get("alliances") or [],
        },
        "rivals": rivals,
        "other_powers": backdrop_view,
        "notable_relations": notable_relations,
        "recent_world_events": [
            {"title": e.get("title"), "description": e.get("description"),
             "affected": e.get("affected_countries") or []}
            for e in (state.get("recent_events") or [])[-MAX_WORLD_EVENTS:]
        ],
        "your_recent_domestic_events": [
            {"title": e.get("title"), "severity": e.get("severity"),
             "stability_impact": e.get("stability_impact")}
            for e in (state.get("domestic_events") or [])[-MAX_OWN_EVENTS:]
        ],
        "treaties": [
            {"type": t.get("type"), "with": (t.get("country_b") if t.get("country_a") == country_id
                                             else t.get("country_a")),
             "summary": t.get("summary")}
            for t in (state.get("treaties") or [])
            if country_id in (t.get("country_a"), t.get("country_b"))
        ],
        "inbox": [m.to_dict() for m in (inbox or [])],
        "your_history": [
            {"round": h.round, "action": h.public_action,
             "private_note": h.private_note, "outcome": h.outcome}
            for h in (history or [])[-MAX_HISTORY:]
        ],
    }


def render_view(view: dict) -> str:
    """Macht aus der Sicht einen lesbaren Prompt-Block.

    Fliesstext statt rohem JSON: Modelle folgen strukturiertem Text zuverlaessiger
    und es spart Tokens gegenueber eingerueckten JSON-Dumps.
    """
    you = view["you"]
    L: list[str] = []
    add = L.append

    add(f"=== RUNDE {view['round']} — {view['date']} ===")
    add("")
    add(f"DEINE NATION: {you['name']} ({you['id']})")
    add(f"  Führung: {you['leader']} | {you['government']} | {you['ideology']}")
    add(f"  Stabilität: {you['stability']}/100")
    e = you["economy"]
    add(f"  Wirtschaft: BIP {e['gdp_bn']} Mrd | Wachstum {e['gdp_growth']}% | "
        f"Arbeitslosigkeit {e['unemployment']}% | Schulden {e['debt_pct_gdp']}% BIP")
    m = you["military"]
    add(f"  Militär: Stärke {m['strength']}/10 | {m['active_personnel']} aktiv | "
        f"Nuklear: {'ja' if m['nuclear_weapons'] else 'nein'}")
    if m.get("equipment"):
        add(f"  Ausrüstung: {m['equipment']}")
    if you.get("national_stats"):
        add(f"  Kennzahlen: {you['national_stats']}")
    if you["at_war_with"]:
        add(f"  IM KRIEG MIT: {', '.join(you['at_war_with'])}")
    if you["sanctions_by"]:
        add(f"  Sanktioniert von: {', '.join(you['sanctions_by'])}")
    if you["alliances"]:
        add(f"  Bündnisse: {', '.join(you['alliances'])}")

    add("")
    add("RIVALEN (ebenfalls von KI-Agenten gesteuert):")
    for r in view["rivals"]:
        war = f" | IM KRIEG MIT {', '.join(r['at_war_with'])}" if r["at_war_with"] else ""
        add(f"  {r['name']} ({r['id']}) — {r['leader']}, {r['ideology']}")
        add(f"    Stabilität {r['stability']} | BIP {r['gdp_bn']} Mrd | "
            f"Militär {r['military_strength']}/10 | Nuklear: {'ja' if r['nuclear'] else 'nein'}{war}")
        add(f"    Beziehung du→sie: {r['your_relation_to_them']} | "
            f"sie→du: {r['their_relation_to_you']}")

    if view["other_powers"]:
        add("")
        add("WEITERE MÄCHTE (nicht agentengesteuert):")
        for p in view["other_powers"]:
            add(f"  {p['name']} ({p['id']}) — Stabilität {p['stability']}, "
                f"Militär {p['military_strength']}/10, Beziehung zu dir: {p['your_relation_to_them']}")

    if view["notable_relations"]:
        add("")
        add(f"BEZIEHUNGEN (Auswahl): {view['notable_relations']}")

    if view["treaties"]:
        add("")
        add("DEINE VERTRÄGE:")
        for t in view["treaties"]:
            add(f"  [{t['type']}] mit {t['with']}: {t['summary']}")

    if view["recent_world_events"]:
        add("")
        add("JÜNGSTE WELTEREIGNISSE:")
        for ev in view["recent_world_events"]:
            add(f"  • {ev['title']} — {ev['description'][:180]}")

    if view["your_recent_domestic_events"]:
        add("")
        add("INNENPOLITIK:")
        for ev in view["your_recent_domestic_events"]:
            add(f"  • {ev['title']} (Schwere {ev['severity']}, "
                f"Stabilität {ev['stability_impact']:+d})")

    if view["inbox"]:
        add("")
        add("NACHRICHTEN AN DICH (letzte Runde):")
        for msg in view["inbox"]:
            add(f"  Von {msg['sender']}: {msg['content']}")

    if view["your_history"]:
        add("")
        add("DEINE BISHERIGEN RUNDEN (deine privaten Notizen sieht niemand sonst):")
        for h in view["your_history"]:
            add(f"  Runde {h['round']}:")
            add(f"    Öffentliche Aktion: {h['action']}")
            if h["private_note"]:
                add(f"    Deine Notiz: {h['private_note']}")
            if h["outcome"]:
                add(f"    Ergebnis: {h['outcome'][:220]}")

    return "\n".join(L)
