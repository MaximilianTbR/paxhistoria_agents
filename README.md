# paxhistoria_agents

Experiment: mehrere LLM-Agenten (via OpenRouter — GPT, Claude, Gemini, DeepSeek)
spielen gemeinsam eine Partie Geopolitik-Simulation, jeder Agent steuert eine
Nation. Ausgewertet wird, wer kooperiert, wer täuscht und wer eskaliert — mit
Trennung zwischen privater Strategie-Notiz und öffentlicher Aktion.

## Status

**Phase 0–2 abgeschlossen.** Zielplattform: Phos, mit Multi-Seat-Fork.

Ergebnis: Automatisiertes Spielen auf paxhistoria.co ist laut Terms of Service
untersagt. Empfehlung ist der Wechsel auf den MIT-lizenzierten offenen Nachbau
[Phos](https://github.com/Ant3iros/Phos).

→ Details, Zitate und Quellen in [`docs/phase0-feasibility.md`](docs/phase0-feasibility.md)

**Phase 1 (Recon) abgeschlossen.** Phos lokal verifiziert, API-Schema ausgewertet:
[`docs/api-notes.md`](docs/api-notes.md). Kernbefund: Phos hat keine Auth, wählt das
LLM pro Request über Header (ideal für ein Modell je Nation) — ist aber
Einzelspieler. Für N Agenten in einer geteilten Welt braucht es einen kleinen,
mechanischen Fork.

## Geplanter Aufbau

| Phase | Inhalt |
|---|---|
| 1 | ✅ Recon: API-Schema Phos → `docs/api-notes.md` |
| 2 | ✅ Phos-Fork (Multi-Seat) + `pax_client.py` |
| 3 | `Agent`-Klasse über OpenRouter, private Notiz + öffentliche Aktion |
| 4 | Orchestrator: Rundenschleife, vollständiges JSON-Log pro Partie |
| 5 | Auswertung: Kriegserklärungen, Kooperationsrate, Wortbruch-Erkennung |

## Loslegen

```bash
./scripts/setup_phos.sh            # klont Phos @ f0aaa4b, spielt den Patch ein
python3 scripts/smoke_multiseat.py # beweist Multi-Seat, ohne einen LLM-Token
```

Für echte Läufe zusätzlich `cp .env.example .env` und den OpenRouter-Key eintragen.

Backend danach starten mit:

```bash
cd vendor/phos/backend && PAX_HOST=127.0.0.1 python3 -m uvicorn app.main:app --port 8000
```

## Aufbau

| Datei | Zweck |
|---|---|
| `pax_client.py` | API-Client für den gepatchten Phos-Server |
| `patches/0001-multiseat.patch` | der Fork: N Nationen unter Agentenkontrolle in einer Welt |
| `scripts/setup_phos.sh` | Phos beim gepinnten Commit holen + patchen |
| `scripts/smoke_multiseat.py` | Selbsttest mit Stub-Schiedsrichter, kostenlos |
| `tests/fake_referee.py` | deterministischer OpenAI-kompatibler Stub |

Phos wird **nicht** ins Repo vendored — wir halten nur den Patch gegen einen
gepinnten Upstream-Commit. Phos ist MIT-lizenziert
([Ant3iros/Phos](https://github.com/Ant3iros/Phos)).

## Die zwei LLM-Rollen

Sauber getrennt zu halten, sonst ist das Experiment nicht auswertbar:

- **Agent** — entscheidet, *was* eine Nation tut. Ein Modell je Nation
  (GPT, Claude, Gemini, DeepSeek). Lebt im Orchestrator, Phase 3/4.
- **Schiedsrichter** — löst auf, *was die Aktion bewirkt*. Für alle Nationen
  dasselbe Modell. Sonst könnten Unterschiede im Ergebnis vom Schiedsrichter
  statt vom Spieler kommen.

## Sicherheitshinweis

API-Keys gehören in `.env` (steht in `.gitignore`), niemals ins Repository und
niemals in Logausgaben. `RefereeConfig.__repr__` maskiert den Key.

**Der Phos-Server hat keinerlei Authentifizierung** — kein Login, kein Token,
keine Rate-Limits. Wer den Port erreicht, hat vollen Zugriff auf alle Partien.
Nur an `127.0.0.1` binden, nie öffentlich exponieren.
