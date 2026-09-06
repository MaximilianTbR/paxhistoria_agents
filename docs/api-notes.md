# Phase 1 — API-Notes: Phos

**Stand:** 2026-09-06
**Grundlage:** `github.com/Ant3iros/Phos` @ `main` (MIT), lokal geklont, Backend real
gestartet, Schema aus `/openapi.json` gezogen. Alle Angaben unten sind am laufenden
Server verifiziert, nicht aus dem Quelltext geraten.

Interne Bezeichnung des Projekts ist `OpenPaxHistoria 0.1.0` (FastAPI).

---

## 1. Setup

### Wichtig: das Makefile ist Windows-only

`make up` und `make dev-backend` rufen `powershell -Command ...` auf, um `.env`
anzulegen. Auf Linux/macOS schlägt das fehl. Direkt starten:

```bash
cd backend
cp .env.example .env
pip install -r requirements.txt
uvicorn app.main:app --port 8000
```

Docker Compose selbst ist plattformneutral (`docker compose up -d`), nur das
Makefile-Wrapper nicht. `backend/.env` ist in `docker-compose.yml` als
`required: false` eingebunden — der Server startet auch ohne.

### Verifiziert

```
GET /api/health
→ {"status":"ok","api_base_url":"https://app.socle.ai/api/v1","model":"MJ Phos"}
```

Interaktive Docs: `http://localhost:8000/docs`, Schema: `/openapi.json`.

---

## 2. Auth — es gibt keine

```
components.securitySchemes : NONE
global security             : NONE
```

**Das Backend hat keinerlei Authentifizierung.** Kein Login, kein Session-Token,
kein CSRF, keine Rate-Limits. Wer den Port erreicht, hat vollen Zugriff auf alle
Sessions.

Konsequenzen für uns:

- `login(session_token)` aus dem ursprünglichen Phase-2-Entwurf **entfällt ersatzlos**.
- Der Server darf **niemals öffentlich exponiert werden** — nur `127.0.0.1` binden.
  Standard ist `host = "0.0.0.0"` in `config.py`; für unseren Betrieb auf
  `127.0.0.1` setzen (`PAX_HOST=127.0.0.1`).

### Was die Header stattdessen tragen

`app/dependencies.py` liest die LLM-Konfiguration **pro Request** aus Headern:

| Header | Bedeutung | Default (aus `.env`) |
|---|---|---|
| `X-Api-Key` | LLM-API-Key | `PAX_API_KEY` |
| `X-Api-Base-Url` | OpenAI-kompatible Base-URL | `PAX_API_BASE_URL` |
| `X-Api-Model` | Modellname | `PAX_MODEL` |
| `X-Api-Provider` | `socle` \| `ollama` | `socle` |
| `X-Api-Language` | Ausgabesprache | `English` |

**Das ist der wichtigste Hebel des ganzen Projekts.** Weil Modell und Key
*pro Request* kommen und nicht global konfiguriert sind, kann derselbe laufende
Server für jede Nation ein anderes Modell verwenden — genau das, was das Experiment
braucht. Kein Neustart, keine Instanz pro Agent.

### OpenRouter-Anbindung

`ai_service.py` nutzt `AsyncOpenAI(api_key=..., base_url=...)` und ruft
`chat.completions.create()`. OpenRouter ist damit direkt kompatibel:

```
X-Api-Base-Url: https://openrouter.ai/api/v1
X-Api-Key:      <OPENROUTER_API_KEY>
X-Api-Model:    anthropic/claude-opus-4.6      # bzw. openai/…, google/…, deepseek/…
X-Api-Provider: ollama
```

> **`X-Api-Provider: ollama` ist kein Tippfehler.** `_is_socle()` prüft schlicht
> `provider == "socle"` (Default!). Trifft das zu, läuft alles über die
> *Responses*-API mit serverseitiger Agent- und Memory-Logik (`_resolve_model`,
> `sync_agent`, `_agent_cache`) — ein persistenter Agent pro Session, der
> Gesprächsverlauf mitführt. Für unser Experiment ist das schädlich: wir wollen
> pro Runde exakt den Kontext liefern, den wir kontrollieren, und keinen
> versteckten Zweitspeicher.
>
> Jeder Wert ≠ `socle` nimmt den generischen Chat-Completions-Pfad
> (zustandslos, `config.model` direkt). `ollama` ist dabei nur das Label für
> "OpenAI-kompatibel, kein Socle" — es wird nichts Ollama-Spezifisches getan.

---

## 3. Endpunkt-Inventar

Alle unter Prefix `/api`. LLM-Header gelten für die mit **AI** markierten.

### Spiel / Weltzustand

| Methode | Pfad | Body | Zweck |
|---|---|---|---|
| POST | `/game/` | `CreateGameRequest` | Session anlegen |
| GET | `/game/sessions` | — | Sessions auflisten |
| GET | `/game/{sid}` | — | **Voller Weltzustand** |
| DELETE | `/game/{sid}` | — | Session löschen |
| POST | `/game/{sid}/action` **AI** | `PlayerAction` | Aktion sofort ausführen |
| POST | `/game/{sid}/queue` | `QueueActionRequest` | Aktion in Warteschlange |
| DELETE | `/game/{sid}/queue/{i}` | — | aus Warteschlange entfernen |
| POST | `/game/{sid}/simulate` **AI** | `SimulateRequest` | **Zeitsprung, SSE-Stream** |
| POST | `/game/{sid}/end-turn` **AI** | — | Alias für `simulate(months=1)` |
| GET | `/game/{sid}/snapshots` | — | Snapshots auflisten |
| POST | `/game/{sid}/restore/{turn}` | — | **Snapshot wiederherstellen** |
| POST | `/game/{sid}/custom-group` | `CreateCustomGroupRequest` | Gruppe bilden |

### Diplomatie

| Methode | Pfad | Zweck |
|---|---|---|
| POST | `/diplomacy/{sid}/message` **AI** | Nachricht an Land/Gruppe, SSE-Stream |
| GET | `/diplomacy/{sid}/history` | gesamte Diplomatie-Historie |
| GET | `/diplomacy/{sid}/history/{country_id}` | Historie mit einem Land |

### Berater

| Methode | Pfad | Zweck |
|---|---|---|
| POST | `/advisor/{sid}/ask` **AI** | Beraterfrage, SSE-Stream |
| GET | `/advisor/{sid}/briefing` **AI** | vorgefertigtes Lagebriefing |
| POST | `/advisor/{sid}/summary` **AI** | Rundenzusammenfassung |

### Sonstiges

`/scenarios/` (CRUD), `/regions/{sid}` (Besetzung/Unabhängigkeit),
`/maps/` (Custom-Karten), `/ai/sync-agent` (nur Socke-relevant, für uns tot),
`/health`.

### Mapping auf den ursprünglichen Phase-2-Entwurf

| ursprünglich geplant | Phos |
|---|---|
| `login(session_token)` | **entfällt** — keine Auth |
| `get_state(nation_id)` | `GET /api/game/{sid}` (liefert die ganze Welt) |
| `submit_action(nation_id, text)` | `POST /api/game/{sid}/action` |
| `trigger_timejump()` | `POST /api/game/{sid}/simulate` (SSE) |
| `get_advisor_response(...)` | `POST /api/advisor/{sid}/ask` (SSE) |
| — | **neu:** `POST /api/diplomacy/{sid}/message` |

---

## 4. Datenmodell

### Session anlegen

```http
POST /api/game/
{"scenario_id": "default_2016", "player_country_id": "FRA"}
→ {"session_id": "07f46d43-…", "message": "Partie créée avec succès"}
```

Mitgelieferte Szenarien: `default_2016` (160 Länder, verifiziert), `starwars`,
`warhammer40k`.

> Das README nennt 147 Länder; der geladene Zustand enthält tatsächlich **160**
> Einträge in `country_states` (inkl. später ergänzter Kleinstaaten aus
> `scripts/add_small_states.py`, `add_caribbean.py`, `add_africa_ca.py`).

### Weltzustand

`GET /api/game/{sid}` liefert eine *aufbereitete Sicht*, nicht das rohe
Session-Objekt:

```
session_id, scenario_id, year, month, turn,
player_country,        # das eigene Land, Stammdaten + Live-State gemerged
countries,             # dict[country_id → dasselbe Format], 160 Einträge
alliances, custom_groups,
recent_events,         # letzte 10 Weltereignisse
domestic_events,       # letzte 20
map_pois, diplomatic_history (20), action_history (10),
pending_actions, region_state, treaties,
custom_map_id, custom_map_feature_id_property, initial_territories
```

Pro Land:

```
id, name, flag, capital, continent, population,
government_type, ideology, leader, alliances,
economy{gdp, gdp_per_capita, gdp_growth, inflation, unemployment,
        debt_pct_gdp, budget_balance_pct_gdp, currency, main_sectors, sectors},
military{strength, active_personnel, nuclear_weapons, defense_budget_pct,
         equipment{chars_combat, avions_chasse, navires_guerre, sous_marins,
                   helicopteres, artillerie, drones}},
national_stats{sovereignty, food_autonomy, energy_autonomy,
               economic_independence, security},
relations{<country_id>: int},      # bilaterale Beziehungswerte
personality_traits, personality, description, nation_brief, color,
initial_stability, stability, economy_modifier, military_modifier,
at_war_with[], sanctions_by[], active_events[]
```

Beispiel (Frankreich, `default_2016`): `stability: 74`,
`relations: {DEU: 82, GBR: 75, USA: 75, ITA: 75, ESP: 72}`,
`national_stats: {sovereignty: 90, food_autonomy: 78, energy_autonomy: 55,
economic_independence: 72, security: 50}`.

**Für Phase 5 ist `relations` die zentrale Messgröße** — eine vollständige
160×160-Beziehungsmatrix, die sich pro Runde bewegt. Kooperation und Verrat sind
daran direkt ablesbar, ohne dass wir sie aus Freitext extrahieren müssen.

### Persistenz

Sessions liegen als JSON unter `backend/app/data/sessions/<session_id>/`,
eine Datei pro Runde (`turn_00001.json`, …). Snapshots sind über
`/snapshots` und `/restore/{turn}` ansprechbar — **das gibt uns
reproduzierbare Startpunkte und die Möglichkeit, eine Runde zu wiederholen.**

### Zeitsprung (SSE)

`POST /game/{sid}/simulate` mit `{"months": 1}` oder `{"weeks": n}` streamt
`text/event-stream`. Event-Typen in Reihenfolge:

```
month_start | week_start   → {year, month, day, turn}
world_event                → {title, description, affected_countries, event_type}
action_result              → {action, narrative, relation_changes, stability_delta,
                              economy_delta, military_delta, stat_deltas,
                              equipment_changes}
domestic_event             → {title, description, event_type, severity, stability_impact}
poi_added                  → {poi_id, poi_name, poi_type, …}
done                       → {final_stability, final_economy_modifier,
                              final_military_modifier, world_event_count,
                              action_count, treaty_count}
error                      → {message}
```

Die Warteschlange (`/queue`) wird beim Simulieren geleert und über die
Simulationseinheiten verteilt (`actions_by_unit[i % total_units]`).

---

## 5. Der entscheidende Befund: Phos ist Einzelspieler

`GameSession` hat **genau einen Sitz**:

```python
class GameSession(BaseModel):
    player_country_id: str        # <- Singular
    country_states: Dict[str, dict]
```

Alle 160 Nationen existieren im `country_states`-Dict mit vollem Zustand — die
**Welt ist geteilt**, nur der *Spielersitz* ist einer. Alle anderen Nationen
werden von der eingebauten Engine-KI gespielt. Es gibt keinen Endpunkt, der eine
Aktion für ein anderes Land als `player_country_id` entgegennimmt.

Das kollidiert mit dem Kern des Experiments: N Agenten, N Nationen, **eine**
gemeinsame Welt.

### Was nicht funktioniert

Eine Session pro Agent auf demselben Szenario. Die Welten laufen dann getrennt
auseinander — die Agenten würden nie miteinander interagieren, und Phase 5 hätte
nichts zu messen.

### Was funktioniert — verifiziert

Die Zustandsanwendung ist **nirgends an den Spieler gebunden, nur an einen
Ländercode**. In `apply_action_result_to_session()` steht 8× dasselbe Muster:

```python
ps = session.country_states.get(session.player_country_id, {})
...
session.country_states[session.player_country_id] = ps
```

`session.player_country_id` ist dort schlicht "das handelnde Land". Auch die
darunterliegenden Helfer sind bereits parametrisiert
(`_apply_economy_delta(session, country_id, delta)`), und `ai_service` bekommt das
Land ohnehin als Argument (`process_player_action(player_country=…)`).

**Gegenprobe am laufenden Code** — zwei Nationen handeln in *einer* Welt,
indem der Sitz um den Aufruf herum getauscht wird:

```
BEFORE  FRA: (stab 74, rel→USA 75)   DEU: (stab 83, rel→USA 72)
  act(FRA, stability +7,  relation→USA +10)
  act(DEU, stability -12, relation→USA -20)
AFTER   FRA: (stab 81, rel→USA 85)   DEU: (stab 71, rel→USA 52)
world size still: 160
```

Beide Nationen wurden unabhängig verändert, im selben `country_states`. Das
Zustandsmodell trägt Mehrspieler-Betrieb bereits — es fehlt nur der Weg hinein.

### Vorgeschlagene Lösung für Phase 2

Kleiner Fork von Phos (MIT erlaubt das ausdrücklich), rein mechanisch:

1. `actor_id: str | None = None` als Parameter in
   `apply_action_result_to_session()` und `apply_action_result()`, intern
   `actor = actor_id or session.player_country_id`. Reines Suchen-und-Ersetzen,
   keine Logikänderung.
2. Optionales Feld `acting_country_id` in `PlayerAction`, das
   `POST /game/{sid}/action` an den Actor durchreicht.
3. Der Orchestrator hält **eine** Session und schickt pro Runde N Aktionen mit
   je eigenem `acting_country_id` **und je eigenen LLM-Headern**.

Aufwand: überschaubar, weil `game_engine.py` (1263 Zeilen) den Sitz zwar an ~30
Stellen nennt, aber nirgends Sonderlogik daran hängt.

> Der Sitz-Tausch aus der Gegenprobe funktioniert auch ohne Fork, ist aber nicht
> nebenläufigkeitssicher (globaler Prozesszustand). Für einen sequentiellen
> Orchestrator wäre er ein gangbarer Zwischenschritt, falls wir Phase 3–5 zuerst
> bauen wollen; sauber ist Variante 1.

### Was der Fork *nicht* lösen muss

`POST /diplomacy/{sid}/message` lässt Nationen antworten — aber mit der
**Engine-KI**, nicht mit unseren Agenten. Für Agent-zu-Agent-Diplomatie
brauchen wir diesen Endpunkt gar nicht: der Orchestrator vermittelt Nachrichten
selbst zwischen den Agenten und schreibt sie nur zur Nachvollziehbarkeit in die
Historie. Der Endpunkt bleibt nützlich für Kontakte zu *nicht* agentengesteuerten
Nationen (den anderen 155).

---

## 6. Determinismus — Einschränkung für Phase 5

`game_engine.py` nutzt das globale `random`-Modul **ohne Seed**:

- `_check_stability_crisis` — `random.random() > 0.6`
- `_progress_war_invasions` — Angreifer/Verteidiger-Wurf, Eroberungschance,
  Kontrollverlust `random.uniform(8, 18)`
- Regionenauswahl, Farbwahl für neue Staaten

Dazu kommt die LLM-Varianz: `_chat_completions()` übergibt **weder `temperature`
noch `seed`**.

Für Phase 5 heißt das: **einzelne Partien sind nicht reproduzierbar.** Zwei
Optionen, nicht exklusiv:

1. `random.seed(...)` pro Session im Fork setzen — nimmt die Engine-Varianz raus,
   nicht die LLM-Varianz.
2. Genug Partien fahren, dass die Kennzahlen über Rauschen liegen, und die
   Startlage über `/restore/{turn}` identisch halten.

Weil auf Phos keine Token-Kosten der Plattform anfallen (nur OpenRouter-Inferenz),
ist Variante 2 realistisch — auf der echten Plattform wäre sie es nicht.

---

## 7. Phase 2 — was daraus gebaut wurde

Der Fork liegt als `patches/0001-multiseat.patch` gegen Upstream-Commit
`f0aaa4b` vor. Phos wird bewusst **nicht** ins Repo vendored.

### Was der Patch ändert

| Datei | Änderung |
|---|---|
| `models/game.py` | `PlayerAction.acting_country_id`, `PendingAction.actor_id`, `PendingConsequence.actor_id`, `GameSession.agent_country_ids`, `CreateGameRequest.agent_country_ids`, `QueueActionRequest.acting_country_id` |
| `services/game_engine.py` | `create_session()` nimmt Agentensitze (validiert, dedupliziert, Spieler immer zuerst); `apply_action_result_to_session()` bekommt `actor_id` — 13 Vorkommen von `session.player_country_id` durch `actor` ersetzt; `apply_simulation_unit()` nimmt eine **Liste** von Aktionsergebnissen und verteilt Weltereignis-Effekte auf **alle** Agentennationen; `_fire_pending_consequences`, `_check_stability_crisis`, `_apply_treaty_effects` arbeiten pro Sitz |
| `routers/game.py` | `/queue` und `/action` nehmen `acting_country_id`; `/simulate` löst jede eingestellte Aktion gegen ihre eigene Nation auf; SSE-`action_result` trägt jetzt `actor_id` |

Rückwärtskompatibel: Sessions ohne `agent_country_ids` (altes JSON) laden und
fallen auf den Einzelspieler-Sitz zurück — verifiziert.

### Simultaneität

`/simulate` zieht vor der Auflösung einen `deepcopy` von `country_states` und löst
**alle** Aktionen der Runde gegen diesen Vorher-Zustand auf. Keine Nation kann
innerhalb der Runde auf den Zug einer anderen reagieren — die Voraussetzung dafür,
dass Täuschung in Phase 5 überhaupt etwas bedeutet.

Reihenfolge innerhalb einer Runde bleibt wie im Original:
Zeit → Weltereignisse → Aktionen → Folgeereignisse → Krieg → Verträge → Wirtschaft.

### Nebenbei gefixt

`POST /game/{sid}/action` war upstream defekt: `process_player_action()` liefert
ein `dict`, das Ergebnis wurde aber in `ActionResult.consequences: str` gesteckt
(Pydantic-ValidationError), und die Deltas der Aktion wurden nie angewendet — nur
Beziehungsänderungen. Der Patch wendet das Ergebnis vollständig an.

### Verifikation ohne LLM-Kosten

`scripts/smoke_multiseat.py` startet den gepatchten Server plus einen
deterministischen Stub-Schiedsrichter (`tests/fake_referee.py`), spielt eine
simultane Runde mit vier Nationen und prüft, dass die Deltas jeder Nation exakt
auf dieser Nation landen:

```
[ok ] FRA: stability 74->80 (erwartet 80), rel->USA 80 (erwartet 80)
[ok ] DEU: stability 83->75 (erwartet 75), rel->USA 60 (erwartet 60)
[ok ] USA: stability 84->87 (erwartet 87), rel->USA 2  (erwartet 2)
[ok ] CHN: stability 51->62 (erwartet 62), rel->USA -40 (erwartet -40)
[ok ] jede Aktion im SSE-Stream ihrer Nation zugeordnet
```

### Offen für Phase 3/4

- **Weltereignisse werden weiterhin aus der Perspektive *eines* Sitzes erzeugt**
  (`generate_turn_events(player_country_id=…, player_nation_context=…)` nutzt den
  nominellen Spieler). Die *Wirkung* verteilt der Patch bereits auf alle
  Agentennationen, die *Erzeugung* ist noch spielerzentriert. Für die Auswertung
  relevant: das kann Ereignisse leicht in Richtung des ersten Sitzes verzerren.
  Sauber wäre, den Kontext aller Agentennationen zu übergeben.
- `apply_simulation_unit` schreibt Aktionen **nicht** in `session.action_history`
  (nur der `/action`-Pfad tut das). Für uns unkritisch, weil der Orchestrator in
  Phase 4 ohnehin selbst vollständig loggt — aber man darf sich nicht auf die
  serverseitige Historie verlassen.
- Diplomatie zwischen unseren Agenten vermittelt der Orchestrator direkt;
  `/diplomacy/message` würde die Engine-KI antworten lassen statt des Agenten.

## 8. Reproduktion dieser Notizen

```bash
git clone --depth 1 https://github.com/Ant3iros/Phos.git
cd Phos/backend && pip install -r requirements.txt
uvicorn app.main:app --port 8000
curl -s localhost:8000/openapi.json | python3 -m json.tool
curl -s -X POST localhost:8000/api/game/ -H 'Content-Type: application/json' \
     -d '{"scenario_id":"default_2016","player_country_id":"FRA"}'
```
