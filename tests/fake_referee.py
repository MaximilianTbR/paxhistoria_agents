"""Minimaler OpenAI-kompatibler Stub-Schiedsrichter — deterministisch, ohne Netz."""
import json, re
from fastapi import FastAPI, Request

app = FastAPI()

@app.post("/chat/completions")
async def chat(req: Request):
    body = await req.json()
    text = json.dumps(body.get("messages", []))
    # Nation aus dem Prompt fischen, damit jede Nation ein anderes Ergebnis bekommt
    m = re.search(r'\b(FRA|DEU|USA|CHN)\b', text)
    who = m.group(1) if m else "FRA"
    table = {"FRA": (6, 0.03, 5), "DEU": (-8, -0.02, -12), "USA": (3, 0.01, 2), "CHN": (11, 0.05, -20)}
    stab, eco, rel = table[who]
    payload = {
        "narrative": f"[stub] Auflösung der Aktion von {who}.",
        "applicable": True,
        "stability_delta": stab,
        "economy_delta": eco,
        "military_delta": 0.0,
        "relation_changes": {who: {"USA": rel}},
        "domestic_events": [],
        "stat_deltas": {"sovereignty": 1},
        "equipment_changes": {},
        "future_events": [],
        "map_poi": None,
    }
    return {"id": "stub", "object": "chat.completion", "model": body.get("model", "stub"),
            "choices": [{"index": 0, "message": {"role": "assistant",
                        "content": json.dumps(payload)}, "finish_reason": "stop"}]}
