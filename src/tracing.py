"""Traces d'exécution en JSONL (une ligne par requête) pour l'analyse d'erreurs."""
import json
from datetime import datetime

from . import config


def log_trace(level: int, question: str, result: dict, test_id: str | None = None,
              filename: str = "traces.jsonl") -> None:
    config.LOGS_DIR.mkdir(exist_ok=True)
    entry = {
        "horodatage": datetime.now().isoformat(timespec="seconds"),
        "test_id": test_id,
        "niveau": level,
        "question": question,
        "reponse": result.get("answer"),
        "statut": result.get("status"),
        "sources_citees": result.get("sources"),
        "documents_recuperes": result.get("retrieved"),
        "etapes": result.get("steps"),
        "tokens": result.get("tokens"),
        "appels_llm": result.get("llm_calls"),
        "duree_s": round(result.get("latency_s", 0), 3),
    }
    with open(config.LOGS_DIR / filename, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
