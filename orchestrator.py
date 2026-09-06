"""Phase 4 — die Rundenschleife.

Eine Runde:

1. Weltzustand einmal holen. **Alle** Agenten sehen denselben Zustand.
2. Jeder Agent entscheidet — ohne die Züge der anderen zu kennen.
3. Alle Aktionen werden eingestellt (``/queue``).
4. **Ein** Zeitsprung löst sie gemeinsam auf (``/simulate``).
5. Ergebnisse werden verteilt, Nachrichten in die Postfächer der nächsten Runde gelegt.
6. Alles wird protokolliert.

Der simultane Zug ist der Grund für diese Reihenfolge: würde ein Agent nach dem
anderen ziehen und dabei die Folgen des Vorgängers sehen, wäre Täuschung
wertlos — man könnte einfach abwarten.

Protokolliert wird pro Partie eine JSON-Datei mit privatem Reasoning,
öffentlicher Aktion, gesendeten Nachrichten und den resultierenden
Weltereignissen. Das ist die Datengrundlage für Phase 5.
"""

from __future__ import annotations

import json
import os
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Iterable

from agents import Agent, AgentConfig, AgentTurn
from pax_client import PaxClient, RefereeConfig, RoundLog
from worldview import Message

__all__ = ["GameConfig", "Orchestrator"]

DEFAULT_LOG_DIR = Path("runs")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass
class GameConfig:
    """Alles, was eine Partie festlegt."""

    agents: list[AgentConfig]
    scenario_id: str = "default_2016"
    rounds: int = 10
    months_per_round: int = 1
    log_dir: Path = DEFAULT_LOG_DIR
    # Agenten parallel befragen. Aendert das Ergebnis nicht — alle sehen ohnehin
    # denselben Zustand —, spart aber Wanduhrzeit bei vielen Nationen.
    parallel_agents: bool = True
    notes: str = ""

    @property
    def seats(self) -> list[str]:
        return [a.country_id for a in self.agents]


def _snapshot(state: dict, seats: Iterable[str]) -> dict:
    """Kompakter Zustand der Agentennationen — pro Runde vor und nach dem Sprung.

    Genau die Groessen, die Phase 5 auswertet.
    """
    countries = state.get("countries") or {}
    out: dict = {}
    for cid in seats:
        c = countries.get(cid) or {}
        eco = c.get("economy") or {}
        out[cid] = {
            "stability": c.get("stability"),
            "gdp_bn": eco.get("gdp"),
            "gdp_growth": eco.get("gdp_growth"),
            "military_modifier": c.get("military_modifier"),
            "at_war_with": c.get("at_war_with") or [],
            "sanctions_by": c.get("sanctions_by") or [],
            "relations": {o: (c.get("relations") or {}).get(o)
                          for o in seats if o != cid},
        }
    return out


class Orchestrator:
    """Führt eine Partie und schreibt das Protokoll."""

    def __init__(
        self,
        config: GameConfig,
        client: PaxClient,
        api_key: str | None = None,
        on_event: Callable[[str], None] | None = None,
    ) -> None:
        self.config = config
        self.client = client
        self.log = on_event or (lambda msg: print(msg, flush=True))
        self.agents: dict[str, Agent] = {
            a.country_id: Agent(a, api_key=api_key) for a in config.agents
        }
        self.session_id: str | None = None
        self.game_id = f"{int(time.time())}-{'-'.join(config.seats)}"
        self.rounds: list[dict] = []
        # Nachrichten, die in der naechsten Runde zugestellt werden
        self._inboxes: dict[str, list[Message]] = {c: [] for c in config.seats}

    # ── Partie ────────────────────────────────────────────────────────────

    def setup(self) -> str:
        seats = self.config.seats
        self.session_id = self.client.create_game(
            self.config.scenario_id, seats[0], seats[1:]
        )
        actual = self.client.seats(self.session_id)
        if actual != seats:
            raise RuntimeError(f"Sitze weichen ab: erwartet {seats}, bekommen {actual}")
        self.log(f"Partie {self.session_id} — Sitze: " +
                 ", ".join(f"{a.country_id}={a.label}" for a in self.config.agents))
        return self.session_id

    def run(self) -> Path:
        """Spielt die konfigurierte Rundenzahl und gibt den Pfad zum Protokoll zurück."""
        if self.session_id is None:
            self.setup()
        try:
            for n in range(1, self.config.rounds + 1):
                self.play_round(n)
                self._write_log()   # nach jeder Runde, damit ein Abbruch nichts kostet
        finally:
            path = self._write_log()
            for a in self.agents.values():
                a.close()
        self.log(f"\nProtokoll: {path}")
        return path

    # ── Eine Runde ────────────────────────────────────────────────────────

    def play_round(self, round_no: int) -> dict:
        assert self.session_id
        sid = self.session_id
        seats = self.config.seats

        state_before = self.client.get_state(sid)
        self.log(f"\n=== Runde {round_no} — {state_before['year']}-{state_before['month']:02d} ===")

        # 1. Alle Agenten entscheiden gegen DENSELBEN Zustand.
        turns = self._collect_turns(state_before, seats, round_no)

        # 2. Aktionen einstellen. Erst jetzt erfaehrt die Engine ueberhaupt davon.
        queued: list[str] = []
        for cid in seats:
            t = turns[cid]
            if not t.ok:
                self.log(f"  [{cid}] AUSGEFALLEN: {t.error}")
                continue
            self.client.queue_action(sid, t.public_action, cid)
            queued.append(cid)
            self.log(f"  [{cid}] {t.public_action[:110]}")

        # 3. Ein gemeinsamer Zeitsprung loest alles gleichzeitig auf.
        if queued:
            self.log("  → Zeitsprung …")
            result: RoundLog = self.client.simulate(
                sid, months=self.config.months_per_round
            )
        else:
            self.log("  → keine Aktionen, Runde uebersprungen")
            result = RoundLog()

        state_after = self.client.get_state(sid)

        # 4. Ergebnisse an die Agenten zurueckspielen.
        for cid in seats:
            outcome = " | ".join(
                r.get("narrative", "") for r in result.results_for(cid)
            ) or "(kein Ergebnis)"
            self.agents[cid].remember(turns[cid], outcome)

        # 5. Nachrichten fuer die naechste Runde zustellen.
        self._deliver_messages(turns, round_no)

        for ev in result.world_events:
            self.log(f"  ! {ev.get('title')}")
        if result.errors:
            self.log(f"  Fehler der Engine: {result.errors}")

        record = {
            "round": round_no,
            "date": f"{state_before['year']}-{state_before['month']:02d}",
            "turn_before": state_before.get("turn"),
            "turn_after": state_after.get("turn"),
            "state_before": _snapshot(state_before, seats),
            "agents": {cid: turns[cid].to_dict() for cid in seats},
            "world_events": result.world_events,
            "action_results": result.action_results,
            "domestic_events": result.domestic_events,
            "engine_errors": result.errors,
            "simulate_done": result.done,
            "state_after": _snapshot(state_after, seats),
        }
        self.rounds.append(record)
        return record

    def _collect_turns(
        self, state: dict, seats: list[str], round_no: int
    ) -> dict[str, AgentTurn]:
        def decide(cid: str) -> tuple[str, AgentTurn]:
            return cid, self.agents[cid].decide(
                state, seats, round_no, inbox=self._inboxes.get(cid, [])
            )

        if self.config.parallel_agents and len(seats) > 1:
            with ThreadPoolExecutor(max_workers=len(seats)) as pool:
                return dict(pool.map(decide, seats))
        return dict(decide(cid) for cid in seats)

    def _deliver_messages(self, turns: dict[str, AgentTurn], round_no: int) -> None:
        fresh: dict[str, list[Message]] = {c: [] for c in self.config.seats}
        for sender, turn in turns.items():
            for msg in turn.messages:
                recipient = msg["to"]
                if recipient in fresh:
                    fresh[recipient].append(Message(
                        sender=sender, recipient=recipient,
                        content=msg["content"], round=round_no,
                    ))
                    self.log(f"  ✉ {sender} → {recipient}: {msg['content'][:80]}")
        self._inboxes = fresh

    # ── Protokoll ─────────────────────────────────────────────────────────

    def _write_log(self) -> Path:
        d = Path(self.config.log_dir)
        d.mkdir(parents=True, exist_ok=True)
        path = d / f"game-{self.game_id}.json"
        payload = {
            "game_id": self.game_id,
            "written_at": _now(),
            "session_id": self.session_id,
            "scenario_id": self.config.scenario_id,
            "rounds_played": len(self.rounds),
            "rounds_configured": self.config.rounds,
            "months_per_round": self.config.months_per_round,
            "notes": self.config.notes,
            "seats": {
                a.country_id: {"model": a.model, "label": a.label,
                               "temperature": a.temperature}
                for a in self.config.agents
            },
            "referee": (
                {"model": self.client.referee.model,
                 "base_url": self.client.referee.base_url}
                if self.client.referee else None
            ),
            "rounds": self.rounds,
        }
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return path
