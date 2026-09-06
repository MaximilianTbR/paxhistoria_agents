# paxhistoria_agents

Experiment: mehrere LLM-Agenten (via OpenRouter — GPT, Claude, Gemini, DeepSeek)
spielen gemeinsam eine Partie Geopolitik-Simulation, jeder Agent steuert eine
Nation. Ausgewertet wird, wer kooperiert, wer täuscht und wer eskaliert — mit
Trennung zwischen privater Strategie-Notiz und öffentlicher Aktion.

## Status

**Phase 0–4 abgeschlossen.** Zielplattform: Phos, mit Multi-Seat-Fork.
Spielbar gegen Stub-Modelle; für echte Läufe fehlt nur der OpenRouter-Key.

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
| 3 | ✅ `Agent`-Klasse über OpenRouter, private Notiz + öffentliche Aktion |
| 4 | ✅ Orchestrator: Rundenschleife, vollständiges JSON-Log pro Partie |
| 5 | Auswertung: Kriegserklärungen, Kooperationsrate, Wortbruch-Erkennung |

## Loslegen

```bash
./scripts/setup_phos.sh             # klont Phos @ f0aaa4b, spielt den Patch ein
python3 scripts/smoke_multiseat.py  # beweist Multi-Seat
python3 scripts/smoke_game.py       # spielt eine ganze Partie gegen Stub-Modelle
python3 tests/test_worldview.py     # prüft die Informationsgrenze
```

Alle drei laufen **ohne Netz und ohne API-Kosten** gegen deterministische Stubs.

Für einen echten Lauf:

```bash
cp .env.example .env                # OPENROUTER_API_KEY eintragen
cd vendor/phos/backend && PAX_HOST=127.0.0.1 python3 -m uvicorn app.main:app --port 8000 &
python3 run_game.py --rounds 8
```

Sitze frei belegen:

```bash
python3 run_game.py \
  --seat FRA=openai/gpt-5 \
  --seat CHN=deepseek/deepseek-chat \
  --seat USA=google/gemini-2.5-pro \
  --rounds 12
```

## Aufbau

| Datei | Zweck |
|---|---|
| `pax_client.py` | API-Client für den gepatchten Phos-Server |
| `worldview.py` | verdichtet 160 Nationen auf die Sicht *einer* Nation |
| `agents.py` | Agent über OpenRouter: private Notiz, öffentliche Aktion, Nachrichten |
| `orchestrator.py` | Rundenschleife + vollständiges JSON-Protokoll je Partie |
| `run_game.py` | CLI zum Starten einer Partie |
| `patches/0001-multiseat.patch` | der Fork: N Nationen unter Agentenkontrolle in einer Welt |
| `scripts/setup_phos.sh` | Phos beim gepinnten Commit holen + patchen |
| `scripts/smoke_multiseat.py` | Selbsttest mit Stub-Schiedsrichter, kostenlos |
| `scripts/smoke_game.py` | ganze Partie gegen Stub-Modelle, kostenlos |
| `tests/fake_referee.py` | Stub-Schiedsrichter |
| `tests/fake_llm.py` | Stub für beide Rollen — Agent und Schiedsrichter |
| `tests/test_worldview.py` | Informationsgrenze zwischen den Agenten |

Phos wird **nicht** ins Repo vendored — wir halten nur den Patch gegen einen
gepinnten Upstream-Commit. Phos ist MIT-lizenziert
([Ant3iros/Phos](https://github.com/Ant3iros/Phos)).

## Wie eine Runde abläuft

1. Weltzustand **einmal** holen — alle Agenten sehen denselben.
2. Jeder Agent entscheidet, ohne die Züge der anderen zu kennen.
3. Alle Aktionen werden eingestellt (`/queue`).
4. **Ein** Zeitsprung löst sie gemeinsam auf (`/simulate`).
5. Ergebnisse zurück an die Agenten, Nachrichten ins Postfach der nächsten Runde.
6. Alles wird protokolliert.

Der simultane Zug ist der Grund für diese Reihenfolge: zöge ein Agent nach dem
anderen und sähe dabei die Folgen des Vorgängers, wäre Täuschung wertlos — man
könnte einfach abwarten.

## Was ein Agent zurückgibt

| Feld | Sichtbar für | Zweck |
|---|---|---|
| `public_action` | alle (über die Folgen) | was die Nation tut |
| `messages` | nur der Empfänger, nächste Runde | was sie anderen *sagt* — Zusagen, Drohungen |
| `private_note` | **niemand sonst** | was sie wirklich vorhat |

Phase 5 misst die Lücke zwischen diesen dreien. Durchgesetzt wird die Trennung
in `worldview.build_view()` — beim Zuschnitt der Sicht, nicht im Prompt, denn ein
Prompt kann sich verplappern. `tests/test_worldview.py` prüft das.

Die Verdichtung ist auch eine Kostenfrage: der rohe Weltzustand sind ~90.000
Tokens, die Agentensicht ~700 — 99,2 % weniger, pro Agent und Runde.

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
