#!/usr/bin/env python3
"""Startet eine Partie.

    python3 run_game.py --rounds 8
    python3 run_game.py --seat FRA=openai/gpt-5 --seat CHN=deepseek/deepseek-chat --rounds 5

Voraussetzung: der gepatchte Phos-Server laeuft (scripts/setup_phos.sh) und
OPENROUTER_API_KEY ist gesetzt (.env wird gelesen, falls vorhanden).
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from agents import AgentConfig
from orchestrator import GameConfig, Orchestrator
from pax_client import PaxClient, RefereeConfig

# Ein Modell je Nation — verschiedene Anbieter, ein Gateway.
DEFAULT_SEATS = [
    ("FRA", "openai/gpt-5"),
    ("DEU", "anthropic/claude-opus-4.6"),
    ("USA", "google/gemini-2.5-pro"),
    ("CHN", "deepseek/deepseek-chat"),
]
DEFAULT_REFEREE = "anthropic/claude-sonnet-4.5"


def load_dotenv(path: Path) -> None:
    """Minimaler .env-Leser — keine zusaetzliche Abhaengigkeit noetig."""
    if not path.is_file():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        os.environ.setdefault(k.strip(), v.strip())


def preflight(api_key: str, models: list[str], base_url: str) -> int:
    """Prueft Key und Modell-IDs, bevor eine Partie Tokens verbrennt.

    Falsche Modell-IDs sind der wahrscheinlichste Grund, warum ein erster Lauf
    scheitert — und ohne diese Pruefung faellt das erst mitten in Runde 1 auf,
    nachdem der Rest schon bezahlt ist.
    """
    import httpx

    base = base_url.rstrip("/")
    with httpx.Client(timeout=30) as http:
        # 1. Key gueltig? Gleichzeitig Guthaben und Rate-Limit ablesen.
        try:
            r = http.get(f"{base}/key", headers={"Authorization": f"Bearer {api_key}"})
        except httpx.HTTPError as exc:
            print(f"FEHLER: {base} nicht erreichbar — {exc}", file=sys.stderr)
            return 1
        if r.status_code == 401:
            print("FEHLER: Key wird abgelehnt (401). Neu anlegen unter "
                  "https://openrouter.ai/settings/keys", file=sys.stderr)
            return 1
        if r.status_code >= 400:
            print(f"FEHLER: /key → HTTP {r.status_code}: {r.text[:200]}", file=sys.stderr)
            return 1

        data = (r.json() or {}).get("data") or {}
        usage, limit = data.get("usage"), data.get("limit")
        print("Key gültig.")
        print(f"  verbraucht : {usage}")
        print(f"  Limit      : {limit if limit is not None else 'keins gesetzt'}")
        if data.get("is_free_tier"):
            print("  HINWEIS: Free-Tier — ohne Guthaben laufen nur Modelle mit :free-Suffix.")
        if limit is not None and usage is not None and limit - usage <= 0:
            print("  WARNUNG: Guthaben aufgebraucht.", file=sys.stderr)

        # 2. Existieren die angeforderten Modelle wirklich?
        try:
            mr = http.get(f"{base}/models")
            mr.raise_for_status()
            available = {m["id"] for m in (mr.json() or {}).get("data", [])}
        except (httpx.HTTPError, KeyError, ValueError) as exc:
            print(f"  Modell-Liste nicht abrufbar ({exc}) — IDs ungeprüft.", file=sys.stderr)
            return 0

    print(f"\nModelle ({len(available)} bei OpenRouter verfügbar):")
    missing = []
    for m in models:
        if m in available:
            print(f"  ok    {m}")
        else:
            missing.append(m)
            near = sorted(a for a in available
                          if a.split("/")[0] == m.split("/")[0])[:6]
            print(f"  FEHLT {m}")
            if near:
                print(f"        vorhanden bei {m.split('/')[0]}/: {', '.join(near)}")

    if missing:
        print(f"\n{len(missing)} Modell-ID(en) existieren nicht. Mit --seat bzw. "
              "--referee korrigieren.", file=sys.stderr)
        return 1
    print("\nAlles bereit. Partie starten ohne --check.")
    return 0


def parse_seat(spec: str) -> tuple[str, str]:
    if "=" not in spec:
        raise argparse.ArgumentTypeError(
            f"--seat erwartet LAND=modell, bekam {spec!r}"
        )
    country, _, model = spec.partition("=")
    return country.strip().upper(), model.strip()


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Multi-Agenten-Partie auf Phos")
    p.add_argument("--seat", type=parse_seat, action="append", metavar="LAND=MODELL",
                   help="Nation und Modell. Mehrfach angebbar. Default: 4 Sitze.")
    p.add_argument("--rounds", type=int, default=8, help="Anzahl Runden (Default 8)")
    p.add_argument("--months", type=int, default=1, help="Monate je Runde (Default 1)")
    p.add_argument("--scenario", default="default_2016")
    p.add_argument("--referee", default=os.environ.get("PAX_REFEREE_MODEL", DEFAULT_REFEREE),
                   help="Schiedsrichter-Modell — fuer alle Nationen dasselbe")
    p.add_argument("--server", default=os.environ.get("PAX_SERVER_URL", "http://127.0.0.1:8000"))
    p.add_argument("--referee-url", default=None,
                   help="Abweichende Basis-URL fuer den Schiedsrichter (z.B. Stub im Test)")
    p.add_argument("--log-dir", default="runs")
    p.add_argument("--sequential", action="store_true",
                   help="Agenten nacheinander befragen statt parallel (langsamer, gleiches Ergebnis)")
    p.add_argument("--notes", default="", help="Freitext, landet im Protokoll")
    p.add_argument("--check", action="store_true",
                   help="nur Key und Modell-IDs prüfen, keine Partie spielen")
    p.add_argument("--api-url", default="https://openrouter.ai/api/v1",
                   help="OpenRouter-Basis-URL (für Tests umbiegbar)")
    args = p.parse_args(argv)

    load_dotenv(Path(__file__).parent / ".env")

    key = os.environ.get("OPENROUTER_API_KEY")
    if not key:
        print("OPENROUTER_API_KEY fehlt. .env anlegen (siehe .env.example).", file=sys.stderr)
        return 2

    seats = args.seat or DEFAULT_SEATS

    if args.check:
        return preflight(key, [m for _, m in seats] + [args.referee], args.api_url)

    if len(seats) < 2:
        print("Mindestens zwei Sitze noetig — sonst gibt es nichts zu messen.", file=sys.stderr)
        return 2

    referee = RefereeConfig(api_key=key, model=args.referee,
                            **({"base_url": args.referee_url} if args.referee_url else {}))

    cfg = GameConfig(
        agents=[AgentConfig(country_id=c, model=m) for c, m in seats],
        scenario_id=args.scenario,
        rounds=args.rounds,
        months_per_round=args.months,
        log_dir=Path(args.log_dir),
        parallel_agents=not args.sequential,
        notes=args.notes,
    )

    with PaxClient(args.server, referee=referee) as client:
        try:
            client.health()
        except Exception as exc:
            print(f"Phos-Server unter {args.server} nicht erreichbar: {exc}", file=sys.stderr)
            print("Starten mit: cd vendor/phos/backend && "
                  "PAX_HOST=127.0.0.1 python3 -m uvicorn app.main:app --port 8000",
                  file=sys.stderr)
            return 1
        Orchestrator(cfg, client, api_key=key).run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
