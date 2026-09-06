# Phase 0 — Machbarkeit & Regeln

**Stand:** 2026-09-06
**Ergebnis:** ⛔ Automatisiertes Spielen auf der echten Plattform ist laut ToS **untersagt**.
**Empfehlung:** Weiter mit dem offenen Nachbau **Phos**, nicht mit paxhistoria.co.

---

## 0. Wichtige Korrektur vorab: die Domain

Im Ausgangs-Prompt steht `paxhistoria.com`. Die tatsächliche Plattform liegt auf
**`paxhistoria.co`** (Pax Historia, Co., YC W2026). Alle Rechtsdokumente hängen dort:

- ToS: `https://www.paxhistoria.co/legal/terms-of-service.pdf` (Effective Date: 13.08.2025)
- Privacy Policy: `https://www.paxhistoria.co/legal/privacy-policy.pdf` (Effective Date: 13.08.2025)
- Wiki: `https://wiki.paxhistoria.co/`

### Einschränkung dieser Recherche

Die Egress-Policy dieser Session **blockt `paxhistoria.co` und `wiki.paxhistoria.co`**
(`EGRESS_BLOCKED` vom Agent-Proxy). Ich habe das nicht umgangen. Die Zitate unten
stammen daher aus Suchmaschinen-Indexierung der Original-PDFs, nicht aus einem
direkten Abruf.

> **To-do für dich:** Lies die beiden PDFs einmal selbst im Browser gegen. Die
> Kernaussage ist eindeutig genug, um die Entscheidung zu tragen, aber die exakte
> Abschnittsnummerierung habe ich nicht am Volltext verifizieren können.

---

## 1. Erlaubt automatisiertes Spielen / Bot-Zugriff? → **Nein, explizit verboten**

Die ToS enthalten im Abschnitt *Prohibited Conduct* (nach vorliegenden Fundstellen
Section 5) eine Klausel, die genau unseren Anwendungsfall trifft:

> "access, monitor, copy, extract, scrape, data-mine, or harvest data from the
> Services (manually or by automated means such as **bots, spiders, or scrapers**)
> except as expressly permitted **in writing**"

Das ist keine Grauzone:

- **"automated means … bots"** — ein Orchestrator, der `submit_action` und
  `trigger_timejump` gegen die Endpunkte feuert, ist genau das.
- **"access, monitor"** — schon das reine Auslesen des Weltzustands per Skript
  (`get_state`) fällt darunter, nicht erst das Schreiben.
- **"except as expressly permitted in writing"** — es gibt einen legalen Weg, aber
  der führt über eine schriftliche Genehmigung, nicht über stillschweigendes Machen.

Zwei weitere Klauseln treffen uns zusätzlich:

> "You may not copy, modify, distribute, sell, lease, **reverse engineer**, or create
> derivative works of the Services or any part thereof."

Phase 1 des Plans — HAR-Datei auswerten, um undokumentierte interne Endpunkte und
deren Schema zu rekonstruieren — ist genau die Tätigkeit, die diese Klausel meint.
Es gibt **keine öffentliche, dokumentierte API**; alles, was wir ansprechen würden,
wäre eine private Schnittstelle des Web-Clients.

> "circumvent or attempt to circumvent access controls or security" und
> "interfere with the proper functioning of the Services"

Relevant, weil die Plattform aktiv Bot-Erkennung einsetzt (siehe Punkt 3).

**Fazit zu Punkt 1:** Nicht "nicht erwähnt", nicht "geduldet" — sondern namentlich
untersagt. Dein eigenes Konto zu benutzen ändert daran nichts: die Klausel verbietet
die *Zugriffsart*, nicht den *Zugriff auf fremde Daten*.

---

## 2. Rate-Limits / Fair-Use → **hartes Ökonomie-Limit, kein technisches Kontingent**

Pax Historia rationiert AI-Nutzung nicht über Requests/Sekunde, sondern über ein
**Token-System** (Wiki: *Token System*, *Pax Patron*):

| Posten | Wert |
|---|---|
| Startguthaben bei Account-Erstellung | 1 Token |
| Täglicher Login-Bonus | 0,20 Token, Reset alle 20 h |
| Überlauf des Daily-Buckets | nicht möglich (Cap bei 0,20) |
| Verbrauch | pro Event-Generierung, Time-Jump, AI-Kommunikation |
| Skalierung | steigt mit Schwierigkeitsgrad und Rundenzahl |

Ein Token entspricht ungefähr einem Dollar Gegenwert (der Daily-Bucket wird in den
Wiki-Quellen als "$0.2" beschrieben). Laut der Drittanbieter-Recherche zu
Pax-Automata können späte Runden (~Runde 80) **100k Token pro Interaktion**
verbrauchen.

**Was das für das Experiment bedeutet, unabhängig von der Rechtslage:**
Fünf Agenten × mehrere Runden × Advisor-Calls wäre auf der echten Plattform teuer
und würde am Daily-Cap von 0,20 hängen. Selbst mit Genehmigung wäre das kein
Setup, in dem man mal eben 20 Partien für die Auswertung in Phase 5 fährt.

Es gibt **Pax Patron / BYOK** (eigener OpenRouter-Key, AES-256-verschlüsselt
hinterlegt) — das löst die Kostenfrage, aber **nicht** die ToS-Frage: BYOK ändert,
wer das Modell bezahlt, nicht, ob automatisierter Zugriff erlaubt ist.

---

## 3. Bot-Erkennung → **vorhanden, also Abbruchkriterium erfüllt**

Die Privacy Policy nennt ausdrücklich, dass Pax Historia

> "security signals (such as **risk scores from bot/fraud prevention services**)"

erhebt und Daten mit "security and fraud prevention services such as bot detection
and risk scoring providers" teilt.

Damit greift deine eigene Abbruchregel aus dem Prompt: *"falls die Plattform sowas
einsetzt, brechen wir an der Stelle ab und wechseln auf den Klon."*

Ein Skript, das mit einem aus dem Browser kopierten Session-Token gegen interne
Endpunkte läuft, würde bei einem Risk-Scoring-Anbieter zwangsläufig auffallen
(fehlende Browser-Signale, TLS-Fingerprint, Request-Kadenz). Der einzige Weg, das
"zum Laufen zu bringen", wäre, genau diese Erkennung zu unterlaufen — und das ist
ausgeschlossen, sowohl nach deiner Vorgabe als auch nach den ToS
("circumvent … security").

---

## Empfehlung: Phos statt paxhistoria.co

**`github.com/Ant3iros/Phos`** ist die saubere Grundlage. Was ich verifiziert habe:

| Kriterium | Phos |
|---|---|
| Lizenz | **MIT** — Automatisierung und Forks ausdrücklich erlaubt |
| Backend | Python + FastAPI |
| Frontend | React + TypeScript + Vite |
| Betrieb | Docker Compose (`make up`, dann `localhost:5173`) oder `make install && make dev` |
| LLM-Anbindung | beliebige OpenAI-kompatible Endpunkte — Ollama, DeepSeek, text-generation-webui, **OpenRouter passt hier direkt rein** |
| Szenario | 2016er Weltkarte, 147 Länder mit realen geopolitischen Daten |

### Warum das für dein Experiment sogar besser ist

Der Punkt des Experiments ist die **Agenten-Dynamik** — wer kooperiert, wer täuscht,
wer eskaliert — nicht die konkrete Plattform. Auf Phos bekommst du dafür:

1. **Keine Rechtsfrage.** MIT-Lizenz, dein Server, dein Konto, keine ToS-Kollision.
2. **Kein Token-Budget.** Du zahlst nur die OpenRouter-Inferenz, kein
   Plattform-Rationierungssystem, kein 0,20/Tag-Cap. Für Phase 5 brauchst du viele
   Partien — auf der echten Plattform wäre das der Show-Stopper, auch mit Erlaubnis.
3. **Kein HAR-Reverse-Engineering.** FastAPI liefert OpenAPI-Schema unter `/docs`
   bzw. `/openapi.json`. Phase 1 schrumpft von "Netzwerk-Traffic rekonstruieren" auf
   "Schema lesen". Phase 2 (`pax_client.py`) wird dadurch trivial und stabil, statt
   bei jedem Frontend-Deploy zu brechen.
4. **Reproduzierbar.** Fixierter Spielstand, fixierter Seed, gleiche Startlage für
   alle Läufe — sonst vergleichst du in Phase 5 Partien, die nicht vergleichbar sind.
5. **Determinismus im Schiedsrichter.** Du kontrollierst, welches Modell die Welt
   auflöst. Auf der echten Plattform ist die Engine eine Blackbox, die sich zwischen
   deinen Läufen ändern kann.

### Der legale Weg zur echten Plattform, falls du ihn willst

Die ToS lassen automatisierten Zugriff bei **schriftlicher Genehmigung** zu. Pax
Historia ist ein YC-W2026-Startup; ein Multi-Modell-Agenten-Benchmark auf ihrer
Engine ist für die potenziell interessant. Wenn dir die echte Plattform wichtig ist,
ist der Weg: **anfragen, bevor gebaut wird** — nicht bauen und hoffen. Ich kann dir
dafür eine Mail aufsetzen.

---

## Vorgeschlagenes weiteres Vorgehen

Der ursprüngliche Phasenplan bleibt gültig, nur das Ziel wechselt:

| Phase | ursprünglich | mit Phos |
|---|---|---|
| 1 | HAR-Datei auswerten | Phos lokal hochziehen, `/openapi.json` auswerten → `docs/api-notes.md` |
| 2 | `pax_client.py` gegen interne Endpunkte | `pax_client.py` gegen die dokumentierte FastAPI |
| 3 | Agent-Abstraktion über OpenRouter | unverändert |
| 4 | Orchestrator + JSON-Log pro Partie | unverändert |
| 5 | Auswertung: Kriegserklärungen, Kooperationsrate, Wortbruch | unverändert, aber mit genug Partien für Aussagekraft |

**Keine HAR-Datei mehr nötig.** Phase 1 braucht stattdessen eine laufende
Phos-Instanz.

Phase 3–5 — der eigentlich interessante Teil, inklusive der Trennung von privater
Strategie-Notiz und öffentlicher Aktion — ist von der Plattformfrage komplett
unberührt. Da geht nichts vom Konzept verloren.

---

## Quellen

- [Pax Historia ToS (PDF, 13.08.2025)](https://www.paxhistoria.co/legal/terms-of-service.pdf)
- [Pax Historia Privacy Policy (PDF, 13.08.2025)](https://www.paxhistoria.co/legal/privacy-policy.pdf)
- [Token System — Pax Historia Wiki](https://wiki.paxhistoria.co/wiki/Token_System)
- [Pax Patron — Pax Historia Wiki](https://wiki.paxhistoria.co/wiki/Pax_Patron)
- [FAQ — Pax Historia Wiki](https://wiki.paxhistoria.co/wiki/FAQ)
- [Pax Historia — Y Combinator](https://www.ycombinator.com/companies/pax-historia)
- [Phos — github.com/Ant3iros/Phos](https://github.com/Ant3iros/Phos)
- [Pax-Automata research notes (Drittanbieter, unvollständig)](https://github.com/phillipyan300/Pax-Automata/blob/feature/project-init/docs/pax-historia-research.md)
