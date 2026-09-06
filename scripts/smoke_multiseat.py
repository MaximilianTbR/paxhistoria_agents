#!/usr/bin/env python3
"""Beweist den Multi-Seat-Patch ohne einen einzigen echten LLM-Token.

Startet den gepatchten Phos-Server und einen deterministischen Stub-Schiedsrichter,
spielt eine simultane Runde mit vier Nationen und prueft, dass die Deltas jeder
Nation genau auf dieser Nation landen.

    python3 scripts/smoke_multiseat.py

Voraussetzung: scripts/setup_phos.sh wurde ausgefuehrt.
"""
from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

PHOS = Path(os.environ.get("PHOS_DIR", ROOT / "vendor" / "phos"))
PHOS_PORT = 8000
REFEREE_PORT = 8099

SEATS = ["FRA", "DEU", "USA", "CHN"]
# muss zur Tabelle in tests/fake_referee.py passen
EXPECTED = {"FRA": (6, 5), "DEU": (-8, -12), "USA": (3, 2), "CHN": (11, -20)}


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

    env = {**os.environ, "PAX_HOST": "127.0.0.1", "PYTHONPATH": str(backend)}
    procs = [
        subprocess.Popen(
            [sys.executable, "-m", "uvicorn", "app.main:app",
             "--port", str(PHOS_PORT), "--host", "127.0.0.1"],
            cwd=backend, env=env,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        ),
        subprocess.Popen(
            [sys.executable, "-m", "uvicorn", "fake_referee:app",
             "--port", str(REFEREE_PORT), "--host", "127.0.0.1"],
            cwd=ROOT / "tests", env={**os.environ, "PYTHONPATH": str(ROOT / "tests")},
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        ),
    ]
    try:
        wait_for(f"http://127.0.0.1:{PHOS_PORT}/api/health")
        wait_for(f"http://127.0.0.1:{REFEREE_PORT}/docs")

        from pax_client import PaxClient, RefereeConfig

        ref = RefereeConfig(api_key="stub", model="stub/model",
                            base_url=f"http://127.0.0.1:{REFEREE_PORT}",
                            provider="openrouter")
        with PaxClient(f"http://127.0.0.1:{PHOS_PORT}", referee=ref) as c:
            sid = c.create_game("default_2016", SEATS[0], SEATS[1:])
            assert c.seats(sid) == SEATS, c.seats(sid)

            before = c.get_state(sid)["countries"]
            for cid in SEATS:
                c.queue_action(sid, f"Testaktion von {cid}", cid)

            log = c.simulate(sid, months=1)
            assert not log.errors, log.errors
            assert len(log.action_results) == len(SEATS), log.action_results

            after = c.get_state(sid)["countries"]
            ok = True
            for cid in SEATS:
                d_stab, d_rel = EXPECTED[cid]
                got_s = after[cid]["stability"]
                exp_s = max(0, min(100, before[cid]["stability"] + d_stab))
                got_r = after[cid]["relations"].get("USA")
                exp_r = (before[cid]["relations"].get("USA") or 0) + d_rel
                mark = "ok " if (got_s == exp_s and got_r == exp_r) else "FAIL"
                ok &= got_s == exp_s and got_r == exp_r
                print(f"  [{mark}] {cid}: stability {before[cid]['stability']}->{got_s} "
                      f"(erwartet {exp_s}), rel->USA {got_r} (erwartet {exp_r})")

            attributed = {r["actor_id"] for r in log.action_results}
            assert attributed == set(SEATS), attributed
            print(f"  [ok ] jede Aktion im SSE-Stream ihrer Nation zugeordnet: {sorted(attributed)}")
            c.delete_game(sid)

        print("\nOK — Multi-Seat funktioniert." if ok else "\nFEHLGESCHLAGEN")
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
