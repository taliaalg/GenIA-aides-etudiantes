| niveau | Recall@5 | MRR | Exactitude | Citation | Abstention | Précision/refus | Succès tâches | pass^3 | Tokens / requête | Latence (s) |
|---|---|---|---|---|---|---|---|---|---|---|
| 0 · LLM seul | — | — | 55 % | — | 60 % | 100 % | — | — | 159 | 3.65 |
| 1 · RAG | 100 % | 0.94 | 95 % | 91 % | 100 % | 100 % | — | — | 680 | 4.23 |
| 2 · Agent | 100 % | 0.94 | 100 % | 95 % | 100 % | 100 % | 100 % | 100 % | 2904 | 7.59 |
| 3 · Agent + reranking | 100 % | 0.98 | 100 % | 95 % | 80 % | 100 % | 100 % | 100 % | 2947 | 9.05 |

Modèle : gemini-3.5-flash-lite, température 0. Niveaux 0-2 : `python eval.py --levels 0 1 2` ; niveau 3 : `python eval.py --levels 3` (26/11/2026).
