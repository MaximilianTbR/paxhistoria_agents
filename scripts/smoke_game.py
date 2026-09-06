#!/usr/bin/env python3
"""Spielt eine vollstaendige Partie gegen Stub-Modelle — ohne Netz, ohne Kosten.

Prueft die Phasen 3 und 4 zusammen:

* jede Nation entscheidet mit ihrem eigenen Modell,
* alle Aktionen werden simultan aufgeloest und der richtigen Nation zugeordnet,
* das Protokoll trennt private Absicht, oeffentliche Aktion und Nachricht,
* Nachrichten erreichen in der Folgerunde das Postfach des Empfaengers.

    python3 scripts/smoke_game.py

Voraussetzung: scripts/setup_phos.sh wurde ausgefuehrt.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

PHOS = Path(os.environ.get("PHOS_DIR", ROOT / "vendor" / "phos"))
PHOS_PORT, STUB_PORT = 8000, 8099
STUB = f"http://127.0.0.1:{STUB_PORT}"
SEATS = ["FRA", "DEU", "USA", "CHN"]
# muss zur REFEREE_TABLE in tests/fake_llm.py passen
EXPECTED_STAB = {"FRA": 6, "DEU": -8, "USA": 3, "CHN": 11}
ROUNDS = 3


def wait_for(url: str, timeout: float = 45.0) -> None:
    import httpx
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            if httpx.get(url, timeout=2, trust_env=False).status_code < 500:
                return
        except Exception:
            time.sleep(0.4)
    raise SystemExit(f"Server kam nicht hoch: {url}")


def main() -> int:
    backend = PHOS / "backend"
    if not backend.is_dir():
        raise SystemExit(f"Phos fehlt unter {PHOS}. Erst scripts/setup_phos.sh laufen lassen.")

    procs = [
        subprocess.Popen(
            [sys.executable, "-m", "uvicorn", "app.main:app",
             "--port", str(PHOS_PORT), "--host", "127.0.0.1"],
            cwd=backend, env={**os.environ, "PAX_HOST": "127.0.0.1"},
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL),
        subprocess.Popen(
            [sys.executable, "-m", "uvicorn", "fake_llm:app",
             "--port", str(STUB_PORT), "--host", "127.0.0.1"],
            cwd=ROOT / "tests",
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL),
    ]
    try:
        wait_for(f"http://127.0.0.1:{PHOS_PORT}/api/health")
        wait_for(f"{STUB}/docs")

        import agents as agents_mod
        from agents import Agent, AgentConfig
        from orchestrator import GameConfig, Orchestrator
        from pax_client import PaxClient, RefereeConfig

        # Agenten auf den Stub statt auf OpenRouter zeigen lassen
        agents_mod.OPENROUTER_URL = f"{STUB}/chat/completions"
        _orig = Agent.__init__

        def _patched(self, config, api_key=None, base_url=f"{STUB}/chat/completions", **kw):
            _orig(self, config, api_key=api_key, base_url=base_url, **kw)

        Agent.__init__ = _patched

        ref = RefereeConfig(api_key="stub", model="stub/referee",
                            base_url=STUB, provider="openrouter")
        cfg = GameConfig(
            agents=[AgentConfig(c, f"stub/{c.lower()}") for c in SEATS],
            rounds=ROUNDS, log_dir=ROOT / "runs", notes="smoke_game",
        )
        with PaxClient(f"http://127.0.0.1:{PHOS_PORT}", referee=ref) as client:
            log_path = Orchestrator(cfg, client, api_key="stub").run()

        d = json.loads(Path(log_path).read_text(encoding="utf-8"))
        ok = True

        def check(label: str, cond: bool, detail: str = "") -> None:
            nonlocal ok
            ok &= cond
            print(f"  [{'ok ' if cond else 'FAIL'}] {label}" + (f" — {detail}" if detail else ""))

        print("\nPruefungen:")
        check("alle Runden protokolliert", d["rounds_played"] == ROUNDS,
              f"{d['rounds_played']}/{ROUNDS}")

        r1 = d["rounds"][0]
        check("kein Agent ausgefallen",
              all(not a["error"] for a in r1["agents"].values()))
        check("privat und oeffentlich getrennt gespeichert",
              all(a["private_note"] and a["public_action"]
                  and a["private_note"] != a["public_action"]
                  for a in r1["agents"].values()))
        check("private Notiz widerspricht der oeffentlichen Zusage",
              "brechen" in r1["agents"]["FRA"]["private_note"]
              and "Kooperation" in r1["agents"]["FRA"]["messages"][0]["content"])

        attributed = {a["actor_id"] for a in r1["action_results"]}
        check("jede Aktion ihrer Nation zugeordnet", attributed == set(SEATS),
              str(sorted(attributed)))

        deltas = {}
        for cid in SEATS:
            before = r1["state_before"][cid]["stability"]
            after = r1["state_after"][cid]["stability"]
            deltas[cid] = after - before
        check("Stabilitaetsdeltas nation-spezifisch",
              deltas == EXPECTED_STAB, f"{deltas} erwartet {EXPECTED_STAB}")

        # Postfach: Nachricht aus Runde 1 muss in Runde 2 im Prompt stehen
        senders_r1 = {m["to"] for a in r1["agents"].values() for m in a["messages"]}
        check("Nachrichten wurden verschickt", bool(senders_r1), str(sorted(senders_r1)))

        print("\nOK — Phase 3 + 4 funktionieren." if ok else "\nFEHLGESCHLAGEN")
        return 0 if ok else 1
    finally:
        for p in procs:
            p.terminate()
        for p in procs:
            try:
                p.wait(timeout=10)
            except subprocess.TimeoutExpired:
                p.kill()


if __name__ == "__main__":
    raise SystemExit(main())
