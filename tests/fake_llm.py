"""Stub-LLM fuer beide Rollen — Agent und Schiedsrichter — ohne Netz und ohne Kosten.

Erkennt an der Systemnachricht, welche Rolle gefragt ist, und antwortet
deterministisch. Der Stub-Agent taeuscht absichtlich: seine private Notiz
widerspricht der oeffentlichen Nachricht. Damit laesst sich pruefen, dass das
Protokoll beides getrennt festhaelt — die Grundlage fuer Phase 5.
"""
import json
import re

from fastapi import FastAPI, Request

app = FastAPI()

# Schiedsrichter: feste Deltas je Nation, damit Ergebnisse pruefbar sind.
REFEREE_TABLE = {
    "FRA": (6, 0.03, 5), "DEU": (-8, -0.02, -12),
    "USA": (3, 0.01, 2), "CHN": (11, 0.05, -20),
}


def _agent_reply(country: str, others: list[str]) -> dict:
    target = others[0] if others else country
    return {
        "private_note": (
            f"[stub] Tatsaechliche Absicht von {country}: {target} wirtschaftlich "
            f"unter Druck setzen und die Zusage bei Gelegenheit brechen."
        ),
        "public_action": (
            f"[stub] {country} kuendigt ein Investitionsprogramm an und verstaerkt "
            f"die diplomatische Praesenz in der Region."
        ),
        "messages": [
            {"to": target,
             "content": f"[stub] {country} sichert {target} volle Kooperation zu."}
        ],
    }


# OpenRouter-Kontoendpunkte, damit der Preflight aus run_game.py testbar ist
@app.get("/key")
async def key_info():
    return {"data": {"label": "stub", "usage": 1.25, "limit": 10.0,
                     "is_free_tier": False, "rate_limit": {"requests": 10,
                                                           "interval": "10s"}}}


@app.get("/models")
async def models():
    return {"data": [{"id": i} for i in (
        "openai/gpt-5", "openai/gpt-5-mini",
        "anthropic/claude-opus-4.6", "anthropic/claude-sonnet-4.5",
        "google/gemini-2.5-pro", "deepseek/deepseek-chat",
    )]}


@app.post("/chat/completions")
async def chat(req: Request):
    body = await req.json()
    messages = body.get("messages", [])
    system = next((m.get("content", "") for m in messages if m.get("role") == "system"), "")
    blob = json.dumps(messages, ensure_ascii=False)

    # Richter-Rolle (analyze.py --judge)
    if "verdict" in blob and "ZUSAGE von" in blob:
        broke = "IM KRIEG" in blob or re.search(r"Beziehung zu [A-Z]{3}: -\d", blob)
        content = json.dumps({
            "verdict": "broken" if broke else "kept",
            "confidence": 0.9,
            "reason": "[stub] " + ("spaeteres Verhalten widerspricht der Zusage"
                                   if broke else "Zusage wurde eingehalten"),
        }, ensure_ascii=False)
        return {"id": "stub", "object": "chat.completion", "model": body.get("model", "stub"),
                "choices": [{"index": 0, "message": {"role": "assistant", "content": content},
                             "finish_reason": "stop"}],
                "usage": {"prompt_tokens": 80, "completion_tokens": 30, "total_tokens": 110}}

    m = re.search(r"Du bist die Staatsführung von .+? \(([A-Z]{3})\)", system)
    if m:
        country = m.group(1)
        others = [c for c in re.findall(r"\(([A-Z]{3})\)", blob)
                  if c != country and c in REFEREE_TABLE]
        content = json.dumps(_agent_reply(country, sorted(set(others))), ensure_ascii=False)
    else:
        # Die handelnde Nation steht in der Aktion selbst. Nach ihr zuerst suchen:
        # der Weltzustand im Prompt listet ALLE Laender, ein blosses "erster Treffer"
        # wuerde immer dieselbe Nation liefern.
        act = re.search(r"\[stub\] ([A-Z]{3}) kuendigt", blob)
        who = act.group(1) if act and act.group(1) in REFEREE_TABLE else next(
            (c for c in REFEREE_TABLE if re.search(rf"\b{c}\b", blob)), "FRA")
        stab, eco, rel = REFEREE_TABLE[who]
        content = json.dumps({
            "narrative": f"[stub] Aufloesung der Aktion von {who}.",
            "applicable": True,
            "stability_delta": stab, "economy_delta": eco, "military_delta": 0.0,
            "relation_changes": {who: {"USA": rel}},
            "domestic_events": [], "stat_deltas": {"sovereignty": 1},
            "equipment_changes": {}, "future_events": [], "map_poi": None,
        }, ensure_ascii=False)

    return {
        "id": "stub", "object": "chat.completion", "model": body.get("model", "stub"),
        "choices": [{"index": 0, "message": {"role": "assistant", "content": content},
                     "finish_reason": "stop"}],
        "usage": {"prompt_tokens": 100, "completion_tokens": 50, "total_tokens": 150},
    }
