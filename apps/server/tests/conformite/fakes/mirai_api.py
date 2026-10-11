"""Fausse MirAI API (OpenAI-compatible) pour le compose de conformité : déterministe, sans modèle.

- `/v1/models` : trois alias ;
- `/v1/chat/completions` : répond selon le dernier message utilisateur :
  * juge de la garde (message système du juge) → `{"complied": false}` ;
  * juge de définition → `{"malicious": true}` si le texte porte « POISON », sinon false ;
  * si le texte contient « APPELLE <nom> » et qu'un outil est déclaré → un appel d'outil
    vers <nom> (déclaré ou non : c'est le serveur qui doit refuser l'outil non déclaré) ;
  * sinon → écho borné du dernier message, préfixé « Réponse : ».
Aucune dépendance au-delà de FastAPI (déjà dans l'image).
"""

import json
import re
import time
import uuid

from fastapi import FastAPI, Request

app = FastAPI(title="fausse-mirai-api")
_APPELLE = re.compile(r"APPELLE\s+([a-z0-9][a-z0-9._-]{2,63})")


@app.get("/v1/models")
async def models():
    return {
        "object": "list",
        "data": [
            {"id": m, "object": "model", "owned_by": "fake"}
            for m in ("chat", "chat-pro", "juge")
        ],
    }


def _texte(message) -> str:
    contenu = message.get("content", "")
    if isinstance(contenu, list):
        return " ".join(p.get("text", "") for p in contenu if isinstance(p, dict))
    return str(contenu or "")


@app.post("/v1/chat/completions")
async def completions(request: Request):
    corps = await request.json()
    messages = corps.get("messages", [])
    systeme = " ".join(_texte(m) for m in messages if m.get("role") == "system")
    dernier = next(
        (_texte(m) for m in reversed(messages) if m.get("role") in ("user", "tool")), ""
    )
    outils = corps.get("tools") or []
    tool_calls = None
    if "juge de sécurité IA" in systeme and "OBJECTIF" in dernier:
        texte = json.dumps({"complied": False, "reason": "fausse api"})
    elif "définition" in systeme.lower() and "malveillant" in systeme.lower():
        texte = json.dumps({"malicious": "POISON" in dernier, "reason": "fausse api"})
    elif "veille documentaire" in systeme and outils:
        # Veille (chantier 3) : le faux modèle appelle une fois chaque outil offert, dans l'ordre
        # du prompt, puis rédige à partir des retours ; déterministe, sans mémoire.
        deja = {
            tc["function"]["name"]
            for m in messages
            if m.get("role") == "assistant"
            for tc in (m.get("tool_calls") or [])
        }
        try:
            args_veille = json.loads(dernier)
        except ValueError, TypeError:
            args_veille = {}
        sujet = str(args_veille.get("sujet") or dernier[:100])
        restants = [o for o in outils if o["function"]["name"] not in deja]
        if restants:
            o = restants[0]
            arguments = {"query": sujet}
            if "urls" in (o["function"].get("parameters") or {}).get("properties", {}):
                arguments["urls"] = list(args_veille.get("seeds") or [])
            tool_calls = [
                {
                    "id": f"call_{uuid.uuid4().hex[:8]}",
                    "type": "function",
                    "function": {
                        "name": o["function"]["name"],
                        "arguments": json.dumps(arguments),
                    },
                }
            ]
            texte = None
        else:
            retours = [_texte(m) for m in messages if m.get("role") == "tool"]
            texte = "Synthèse : " + " | ".join(r[:120] for r in retours)
    else:
        appel = _APPELLE.search(dernier)
        deja_appele = any(m.get("role") == "tool" for m in messages)
        if appel and outils and not deja_appele:
            tool_calls = [
                {
                    "id": f"call_{uuid.uuid4().hex[:8]}",
                    "type": "function",
                    "function": {
                        "name": appel.group(1),
                        "arguments": json.dumps({"text": "sous-question"}),
                    },
                }
            ]
            texte = None
        else:
            texte = f"Réponse : {dernier[:200]}"
    message = {"role": "assistant", "content": texte}
    if tool_calls:
        message["tool_calls"] = tool_calls
    return {
        "id": f"chatcmpl-{uuid.uuid4().hex[:12]}",
        "object": "chat.completion",
        "created": int(time.time()),
        "model": corps.get("model", "chat"),
        "choices": [
            {
                "index": 0,
                "message": message,
                "finish_reason": "tool_calls" if tool_calls else "stop",
            }
        ],
        "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
    }


@app.get("/health")
async def health():
    return {"status": "ok"}
