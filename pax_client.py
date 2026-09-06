"""Schlanker Client für die (gepatchte) Phos-API.

Phase 2 des Experiments. Deckt genau die Endpunkte ab, die der Orchestrator
braucht — plus die Multi-Seat-Erweiterungen aus ``patches/0001-multiseat.patch``.

Zwei LLM-Rollen sauber getrennt halten:

* **Agent** — entscheidet, *was* eine Nation tut. Ein Modell je Nation. Lebt im
  Orchestrator (Phase 3/4), nicht hier.
* **Schiedsrichter** (:class:`RefereeConfig`) — löst auf, *was die Aktion bewirkt*.
  Muss für alle Nationen dasselbe Modell sein, sonst ist nicht unterscheidbar,
  ob ein Unterschied vom Spieler oder vom Schiedsrichter kommt.

Der Phos-Server hat keine Authentifizierung. Er darf ausschließlich an
127.0.0.1 gebunden werden.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from typing import Any, Iterable, Iterator

import httpx

__all__ = ["RefereeConfig", "PaxClient", "PaxError", "RoundLog"]

DEFAULT_BASE_URL = "http://127.0.0.1:8000"
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"


class PaxError(RuntimeError):
    """Fehler aus der Phos-API oder aus einem SSE-Stream."""


@dataclass
class RefereeConfig:
    """LLM-Konfiguration für die Auflösung von Aktionen und Weltereignissen.

    ``provider`` darf **nicht** ``"socle"`` sein: dieser Wert schaltet Phos auf
    die Responses-API mit serverseitigem Agent-Memory um, was uns einen zweiten,
    unkontrollierten Kontextspeicher unterschieben würde.
    """

    api_key: str = field(default_factory=lambda: os.environ.get("OPENROUTER_API_KEY", ""))
    model: str = "anthropic/claude-sonnet-4.5"
    base_url: str = OPENROUTER_BASE_URL
    language: str = "German"
    provider: str = "openrouter"

    def __post_init__(self) -> None:
        if not self.api_key:
            raise ValueError(
                "Kein API-Key. OPENROUTER_API_KEY setzen oder api_key übergeben."
            )
        if self.provider == "socle":
            raise ValueError(
                'provider="socle" aktiviert serverseitiges Agent-Memory in Phos. '
                "Für reproduzierbare Läufe einen anderen Wert verwenden."
            )

    def headers(self) -> dict[str, str]:
        return {
            "X-Api-Key": self.api_key,
            "X-Api-Base-Url": self.base_url,
            "X-Api-Model": self.model,
            "X-Api-Provider": self.provider,
            "X-Api-Language": self.language,
        }

    def __repr__(self) -> str:  # Key niemals in Logs oder Tracebacks
        return (
            f"RefereeConfig(model={self.model!r}, base_url={self.base_url!r}, "
            f"provider={self.provider!r}, language={self.language!r}, api_key=***)"
        )


@dataclass
class RoundLog:
    """Eine Runde, nach Ereignistyp und Nation aufgeschlüsselt.

    Rohmaterial für Phase 5 — deshalb bleibt ``raw`` vollständig erhalten.
    """

    world_events: list[dict] = field(default_factory=list)
    action_results: list[dict] = field(default_factory=list)
    domestic_events: list[dict] = field(default_factory=list)
    pois: list[dict] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    done: dict | None = None
    raw: list[dict] = field(default_factory=list)

    def results_for(self, country_id: str) -> list[dict]:
        return [r for r in self.action_results if r.get("actor_id") == country_id]


class PaxClient:
    """Synchroner Client. Ein Orchestrator-Durchlauf ist ohnehin sequentiell."""

    def __init__(
        self,
        base_url: str = DEFAULT_BASE_URL,
        referee: RefereeConfig | None = None,
        timeout: float = 30.0,
        stream_read_timeout: float | None = 600.0,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.referee = referee
        self._http = httpx.Client(
            base_url=self.base_url,
            timeout=httpx.Timeout(timeout),
            # Der Server ist lokal; ein Proxy davor würde nur stören.
            trust_env=False,
        )
        self._stream_timeout = httpx.Timeout(
            timeout, read=stream_read_timeout, write=timeout, pool=timeout
        )

    # ── intern ────────────────────────────────────────────────────────────

    def _ai_headers(self) -> dict[str, str]:
        if self.referee is None:
            raise PaxError(
                "Dieser Aufruf braucht ein LLM. PaxClient(referee=RefereeConfig(...)) setzen."
            )
        return self.referee.headers()

    def _request(self, method: str, path: str, **kw: Any) -> Any:
        try:
            r = self._http.request(method, path, **kw)
        except httpx.HTTPError as exc:
            raise PaxError(f"{method} {path} fehlgeschlagen: {exc}") from exc
        if r.status_code >= 400:
            raise PaxError(f"{method} {path} → HTTP {r.status_code}: {r.text[:400]}")
        return r.json() if r.content else None

    def _stream_sse(self, path: str, payload: dict | None = None) -> Iterator[dict]:
        """Liest einen ``text/event-stream`` und gibt die JSON-Payloads aus."""
        try:
            with self._http.stream(
                "POST",
                path,
                json=payload if payload is not None else {},
                headers=self._ai_headers(),
                timeout=self._stream_timeout,
            ) as r:
                if r.status_code >= 400:
                    r.read()
                    raise PaxError(f"POST {path} → HTTP {r.status_code}: {r.text[:400]}")
                for line in r.iter_lines():
                    if not line or not line.startswith("data:"):
                        continue
                    body = line[5:].strip()
                    if not body:
                        continue
                    try:
                        yield json.loads(body)
                    except json.JSONDecodeError:
                        # Kaputte Zeile lieber überspringen als die Runde abbrechen.
                        continue
        except httpx.HTTPError as exc:
            raise PaxError(f"Stream {path} abgebrochen: {exc}") from exc

    @staticmethod
    def _join_chunks(events: Iterable[dict]) -> str:
        out: list[str] = []
        for ev in events:
            if "error" in ev:
                raise PaxError(f"Server meldet Fehler: {ev['error']}")
            if chunk := ev.get("chunk"):
                out.append(chunk)
        return "".join(out)

    # ── Server / Szenarien ────────────────────────────────────────────────

    def health(self) -> dict:
        return self._request("GET", "/api/health")

    def list_scenarios(self) -> list[dict]:
        return self._request("GET", "/api/scenarios/")

    # ── Partie ────────────────────────────────────────────────────────────

    def create_game(
        self,
        scenario_id: str,
        player_country_id: str,
        agent_country_ids: Iterable[str] = (),
    ) -> str:
        """Legt eine Partie an und gibt die ``session_id`` zurück.

        ``player_country_id`` ist immer ein Agentensitz; ``agent_country_ids``
        sind die weiteren. Braucht den Multi-Seat-Patch.
        """
        data = self._request(
            "POST",
            "/api/game/",
            json={
                "scenario_id": scenario_id,
                "player_country_id": player_country_id,
                "agent_country_ids": list(agent_country_ids),
            },
        )
        return data["session_id"]

    def get_state(self, session_id: str) -> dict:
        """Voller Weltzustand: alle Nationen, Beziehungen, Ereignisse, Verträge."""
        return self._request("GET", f"/api/game/{session_id}")

    def list_sessions(self) -> list[dict]:
        return self._request("GET", "/api/game/sessions")

    def delete_game(self, session_id: str) -> None:
        self._request("DELETE", f"/api/game/{session_id}")

    def seats(self, session_id: str) -> list[str]:
        return self.get_state(session_id).get("agent_country_ids", [])

    # ── Aktionen ──────────────────────────────────────────────────────────

    def queue_action(self, session_id: str, content: str, acting_country_id: str) -> list[dict]:
        """Stellt eine Aktion in die Warteschlange, ohne sie aufzulösen.

        Der simultane Modus: alle Nationen stellen ein, danach löst **ein**
        :meth:`simulate` die Runde gemeinsam auf. Niemand sieht die Züge der
        anderen, bevor er selbst gezogen hat.
        """
        return self._request(
            "POST",
            f"/api/game/{session_id}/queue",
            json={"content": content, "acting_country_id": acting_country_id},
        )["queue"]

    def remove_queued_action(self, session_id: str, index: int) -> list[dict]:
        return self._request("DELETE", f"/api/game/{session_id}/queue/{index}")["queue"]

    def clear_queue(self, session_id: str) -> None:
        while self.get_state(session_id)["pending_actions"]:
            self.remove_queued_action(session_id, 0)

    def submit_action(self, session_id: str, content: str, acting_country_id: str) -> dict:
        """Löst eine einzelne Aktion sofort auf (sequentiell).

        Für den simultanen Modus **nicht** verwenden — dort
        :meth:`queue_action` + :meth:`simulate`.
        """
        state = self.get_state(session_id)
        return self._request(
            "POST",
            f"/api/game/{session_id}/action",
            json={
                "content": content,
                "year": state["year"],
                "month": state["month"],
                "acting_country_id": acting_country_id,
            },
            headers=self._ai_headers(),
            timeout=self._stream_timeout,
        )

    # ── Zeitsprung ────────────────────────────────────────────────────────

    def simulate_stream(
        self, session_id: str, months: int = 1, weeks: int = 0
    ) -> Iterator[dict]:
        """Roher SSE-Strom des Zeitsprungs (Events siehe docs/api-notes.md)."""
        return self._stream_sse(
            f"/api/game/{session_id}/simulate", {"months": months, "weeks": weeks}
        )

    def simulate(self, session_id: str, months: int = 1, weeks: int = 0) -> RoundLog:
        """Zeitsprung, Ergebnis nach Typ sortiert.

        Löst alle eingestellten Aktionen gemeinsam auf — der simultane Zug.
        """
        log = RoundLog()
        for ev in self.simulate_stream(session_id, months=months, weeks=weeks):
            log.raw.append(ev)
            match ev.get("type"):
                case "world_event":
                    log.world_events.append(ev)
                case "action_result":
                    log.action_results.append(ev)
                case "domestic_event":
                    log.domestic_events.append(ev)
                case "poi_added":
                    log.pois.append(ev)
                case "done":
                    log.done = ev
                case "error":
                    log.errors.append(ev.get("message", "unbekannter Fehler"))
        return log

    # ── Snapshots ─────────────────────────────────────────────────────────

    def list_snapshots(self, session_id: str) -> list[dict]:
        return self._request("GET", f"/api/game/{session_id}/snapshots")

    def restore_snapshot(self, session_id: str, turn: int) -> dict:
        """Setzt die Partie auf eine frühere Runde zurück (reproduzierbare Starts)."""
        return self._request("POST", f"/api/game/{session_id}/restore/{turn}")

    # ── Berater / Diplomatie ──────────────────────────────────────────────

    def ask_advisor(self, session_id: str, question: str) -> str:
        return self._join_chunks(
            self._stream_sse(f"/api/advisor/{session_id}/ask", {"question": question})
        )

    def send_diplomatic_message(
        self, session_id: str, target_country_id: str, message: str
    ) -> str:
        """Nachricht an eine **nicht** agentengesteuerte Nation.

        Die Antwort kommt von der Phos-Engine-KI. Für Diplomatie *zwischen*
        unseren Agenten vermittelt der Orchestrator direkt — sonst würde die
        Engine antworten statt des Agenten.
        """
        return self._join_chunks(
            self._stream_sse(
                f"/api/diplomacy/{session_id}/message",
                {"target_country_id": target_country_id, "message": message},
            )
        )

    def diplomatic_history(self, session_id: str) -> list[dict]:
        return self._request("GET", f"/api/diplomacy/{session_id}/history")

    # ── Lifecycle ─────────────────────────────────────────────────────────

    def close(self) -> None:
        self._http.close()

    def __enter__(self) -> "PaxClient":
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()
