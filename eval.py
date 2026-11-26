"""Évaluation : `python eval.py` reproduit le tableau de résultats des niveaux 0 à 3.

Options :
  --levels 0 1 2      niveaux à évaluer (défaut : 0 1 2 3)
  --no-pass3          ne pas relancer 3 fois les tâches (plus rapide)
  --types doc absent  ne garder que certains types de cas
"""
import argparse
import json
import re
import statistics
import tempfile
import unicodedata
from pathlib import Path

from src import config
from src.levels import LEVELS
from src.rag import Retriever
from src.tools import Session
from src.tracing import log_trace

ABSTENTION_MARKERS = ["je ne sais pas", "ne trouve pas", "ne contiennent pas", "ne contient pas",
                      "pas d'information", "aucune information", "pas dans les documents",
                      "ne dispose pas", "pas en mesure"]
REFUS_MARKERS = ["hors sujet", "je ne peux pas", "ne peux pas t'aider", "ne peux pas vous aider"]


# ---------------------------------------------------------------------------
# Règles de correction (pas de juge LLM : tout est vérifiable par du code)
# ---------------------------------------------------------------------------
def normalize(text: str) -> str:
    text = unicodedata.normalize("NFD", (text or "").lower())
    text = "".join(c for c in text if unicodedata.category(c) != "Mn")
    text = text.replace(",", ".")
    text = re.sub(r"[\s  ]+", "", text)           # « 1 454 € » -> « 1454€ »
    text = re.sub(r"(\d)\.(\d{3})(?!\d)", r"\1\2", text)     # « 1.454 » -> « 1454 »
    text = text.replace("'", "").replace("’", "")
    return text


def contains_all(answer: str, expected: list) -> bool:
    a = normalize(answer)
    for item in expected:
        alternatives = item if isinstance(item, list) else [item]
        if not any(normalize(alt) in a for alt in alternatives):
            return False
    return True


def is_abstention(answer: str) -> bool:
    a = (answer or "").lower()
    return any(m in a for m in ABSTENTION_MARKERS)


def is_clarification_or_refusal(answer: str) -> bool:
    a = (answer or "").lower()
    return "?" in a or any(m in a for m in REFUS_MARKERS)


def get_path(d: dict, dotted: str):
    for key in dotted.split("."):
        if not isinstance(d, dict) or key not in d:
            return None
        d = d[key]
    return d


def check_state(session, expected: dict) -> tuple[bool, str]:
    """Vérifie l'état final (fichiers envoyés, éligibilités calculées, budgets)."""
    if session is None:
        return False, "pas de session (niveau sans outils)"
    envois = session.envois()
    if "nb_envois" in expected and len(envois) != expected["nb_envois"]:
        return False, f"{len(envois)} envoi(s) au lieu de {expected['nb_envois']}"
    if "envoi" in expected:
        if not envois:
            return False, "aucun envoi"
        last = envois[-1]
        for path, value in expected["envoi"].items():
            got = get_path(last, path)
            if str(got).lower() != str(value).lower():
                return False, f"{path} = {got!r} au lieu de {value!r}"
    if "derniere_eligibilite" in expected:
        if not session.eligibilites:
            return False, "éligibilité jamais vérifiée"
        for k, v in expected["derniere_eligibilite"].items():
            if session.eligibilites[-1].get(k) != v:
                return False, f"éligibilité.{k} = {session.eligibilites[-1].get(k)!r}"
    if "budget" in expected:
        if not session.budgets:
            return False, "budget jamais calculé"
        for k, v in expected["budget"].items():
            if abs(session.budgets[-1].get(k, 1e9) - v) > 0.01:
                return False, f"budget.{k} = {session.budgets[-1].get(k)!r}"
    return True, "ok"


# ---------------------------------------------------------------------------
def grade(case: dict, res: dict, level: int) -> dict:
    t = case["type"]
    out = {"id": case["id"], "type": t}
    ans = res["answer"]
    if res.get("status") == "error":  # un plantage n'est jamais compté comme une réussite
        key = {"doc": "exact", "absent": "abstention", "ambigu": "precision_ou_refus", "tache": "succes"}[t]
        out[key] = False
        if t == "doc":
            out["cite_source"] = False if level >= 1 else None
        if t == "tache":
            out["motif"] = "erreur d'exécution"
        return out
    if t == "doc":
        out["exact"] = contains_all(ans, case["doit_contenir"]) and not is_abstention(ans)
        out["cite_source"] = any(s in res["sources"] for s in case["sources_attendues"]) if level >= 1 else None
    elif t == "absent":
        out["abstention"] = is_abstention(ans)
    elif t == "ambigu":
        ok = is_clarification_or_refusal(ans)
        if level >= 2:
            state_ok, _ = check_state(res["session"], case["etat_final"])
            ok = ok and state_ok
        out["precision_ou_refus"] = ok
    elif t == "tache":
        ok, why = check_state(res["session"], case["etat_final"])
        if ok and case.get("doit_contenir"):
            ok = contains_all(ans, case["doit_contenir"])
            why = "ok" if ok else "réponse incomplète"
        out["succes"], out["motif"] = ok, why
    return out


def run_case(level_obj, level: int, case: dict) -> dict:
    confirm = (lambda call: case.get("confirmer", False))
    workdir = tempfile.mkdtemp(prefix=f"eval-{case['id']}-")
    try:
        res = level_obj.answer(case["question"], confirm=confirm, workdir=workdir)
    except Exception as e:  # un cas qui plante (API indisponible…) compte comme un échec
        print(f"  {case['id']:<10} ERREUR {type(e).__name__}: {e}")
        res = {"answer": f"ERREUR {type(e).__name__}", "sources": [], "retrieved": [], "tokens": 0,
               "latency_s": 0.0, "llm_calls": 0, "steps": [], "status": "error",
               "session": Session(Path(workdir)) if level >= 2 else None}
    log_trace(level, case["question"], res, test_id=case["id"], filename=f"traces_eval_niveau{level}.jsonl")
    return res


def retrieval_metrics(retriever: Retriever, cases: list, k: int = 5) -> dict:
    recalls, rrs = [], []
    for c in cases:
        if c["type"] != "doc":
            continue
        ranked = retriever.search_doc_ids(c["question"], k=k)
        expected = set(c["sources_attendues"])
        recalls.append(1.0 if expected & set(ranked) else 0.0)
        rr = 0.0
        for i, d in enumerate(ranked):
            if d in expected:
                rr = 1.0 / (i + 1)
                break
        rrs.append(rr)
    return {"recall@5": statistics.mean(recalls), "mrr": statistics.mean(rrs)}


def pct(values):
    values = [v for v in values if v is not None]
    return f"{100 * statistics.mean(values):.0f} %" if values else "—"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--levels", type=int, nargs="+", default=[0, 1, 2, 3])
    ap.add_argument("--no-pass3", action="store_true")
    ap.add_argument("--types", nargs="+", default=["doc", "absent", "tache", "ambigu"])
    args = ap.parse_args()

    cases = [json.loads(l) for l in open(config.TESTS_FILE, encoding="utf-8") if l.strip()]
    cases = [c for c in cases if c["type"] in args.types]
    config.RESULTS_DIR.mkdir(exist_ok=True)

    base_retriever = Retriever() if any(l in (1, 2) for l in args.levels) else None
    rerank_retriever = Retriever(rerank=True) if 3 in args.levels else None
    rows = []

    for level in args.levels:
        if level == 0:
            obj = LEVELS[0]()
        elif level == 3:
            obj = LEVELS[3](retriever=rerank_retriever)
        else:
            obj = LEVELS[level](retriever=base_retriever)
        print(f"\n=== Niveau {obj.name} ===")
        graded, tokens, latencies, pass3 = [], [], [], []
        raw_path = config.RESULTS_DIR / f"resultats_niveau{level}.jsonl"
        with open(raw_path, "w", encoding="utf-8") as raw:
            for case in cases:
                if case["type"] == "tache" and level < 2:
                    continue  # les niveaux 0 et 1 n'ont pas d'outils
                res = run_case(obj, level, case)
                g = grade(case, res, level)
                graded.append(g)
                tokens.append(res["tokens"])
                latencies.append(res["latency_s"])
                if case["type"] == "tache" and not args.no_pass3:
                    ok3 = g["succes"]
                    for _ in range(2):
                        if not ok3:
                            break
                        ok3 = grade(case, run_case(obj, level, case), level)["succes"]
                    pass3.append(1.0 if ok3 else 0.0)
                raw.write(json.dumps({**g, "reponse": res["answer"], "tokens": res["tokens"],
                                      "latence_s": round(res["latency_s"], 2)}, ensure_ascii=False) + "\n")
                print(f"  {case['id']:<10} {json.dumps({k: v for k, v in g.items() if k not in ('id', 'type')}, ensure_ascii=False)}")

        retr = None
        if level >= 1:
            retr = retrieval_metrics(rerank_retriever if level == 3 else base_retriever, cases)
        by = lambda t, k: [g[k] for g in graded if g["type"] == t]
        rows.append({
            "niveau": obj.name,
            "Recall@5": f"{100 * retr['recall@5']:.0f} %" if retr else "—",
            "MRR": f"{retr['mrr']:.2f}" if retr else "—",
            "Exactitude": pct(by("doc", "exact")),
            "Citation": pct(by("doc", "cite_source")) if level >= 1 else "—",
            "Abstention": pct(by("absent", "abstention")),
            "Précision/refus": pct(by("ambigu", "precision_ou_refus")),
            "Succès tâches": pct(by("tache", "succes")) if level >= 2 else "—",
            "pass^3": pct(pass3) if level >= 2 and pass3 else "—",
            "Tokens / requête": f"{statistics.mean(tokens):.0f}" if tokens else "—",
            "Latence (s)": f"{statistics.mean(latencies):.2f}" if latencies else "—",
        })

    headers = list(rows[0].keys())
    table = "| " + " | ".join(headers) + " |\n|" + "---|" * len(headers) + "\n"
    table += "\n".join("| " + " | ".join(r[h] for h in headers) + " |" for r in rows)
    (config.RESULTS_DIR / "tableau.md").write_text(table + "\n", encoding="utf-8")
    print("\n" + table)
    print(f"\nTableau écrit dans {config.RESULTS_DIR / 'tableau.md'}")


if __name__ == "__main__":
    main()
