# paxhistoria_agents

Experiment: mehrere LLM-Agenten (via OpenRouter — GPT, Claude, Gemini, DeepSeek)
spielen gemeinsam eine Partie Geopolitik-Simulation, jeder Agent steuert eine
Nation. Ausgewertet wird, wer kooperiert, wer täuscht und wer eskaliert — mit
Trennung zwischen privater Strategie-Notiz und öffentlicher Aktion.

## Status

**Phase 0 (Machbarkeit) + Phase 1 (Recon) abgeschlossen. Zielplattform: Phos.**

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
| 2 | Phos-Fork (Multi-Seat) + `pax_client.py` |
| 3 | `Agent`-Klasse über OpenRouter, private Notiz + öffentliche Aktion |
| 4 | Orchestrator: Rundenschleife, vollständiges JSON-Log pro Partie |
| 5 | Auswertung: Kriegserklärungen, Kooperationsrate, Wortbruch-Erkennung |

## Sicherheitshinweis

API-Keys und Session-Tokens gehören in `.env` (steht in `.gitignore`), niemals
ins Repository und niemals in Logausgaben.
