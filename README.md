# GenIA — Assistant « Aides étudiantes » (projet 2026, parcours Texte)

**ECE Paris · GenIA (IA générative) · Section 2**
Équipe : Talia Toutah, Julia Ezzedine

Un assistant qui répond aux questions des étudiants sur les aides (bourse Crous, CVEC, logement,
repas à 1 €) et qui peut monter une demande, construit en 4 niveaux mesurés sur le même jeu de test.

> Les envois de demandes sont **simulés** (fichiers locaux) : aucune démarche réelle n'est effectuée.
> Le corpus ne contient aucune donnée personnelle réelle ; les profils des tests sont fictifs.

## Résultats

Tableau produit par `python eval.py` sur les 42 cas de `data/tests.jsonl`
(modèle `gemini-3.5-flash-lite`, température 0 ; détail par cas dans `results/`).

| Niveau | Recall@5 | MRR | Exactitude | Citation | Abstention | Précision/refus | Succès tâches | pass^3 | Tokens / requête | Latence (s) |
|---|---|---|---|---|---|---|---|---|---|---|
| 0 · LLM seul | — | — | 55 % | — | 60 % | 100 % | — | — | 159 | 3,65 |
| 1 · RAG | 100 % | 0,94 | 95 % | 91 % | 100 % | 100 % | — | — | 680 | 4,23 |
| 2 · Agent | 100 % | 0,94 | 100 % | 95 % | 100 % | 100 % | 100 % | 100 % | 2 904 | 7,59 |
| 3 · Agent + reranking | 100 % | 0,98 | 100 % | 95 % | 80 % | 100 % | 100 % | 100 % | 2 947 | 9,05 |

**À retenir**
- Le **RAG** fait passer l'exactitude de 55 % à 95 % et l'abstention de 60 % à 100 % : sans documents,
  le modèle donne des montants périmés (ex. CVEC à 103 € au lieu de 105 €) et n'en cite aucune source.
- L'**agent** atteint 100 % et réussit les 10 tâches de façon stable (pass^3 = 100 %), au prix de
  ~4 fois plus de tokens que le RAG et d'une latence environ 2 fois plus élevée.
- La seule erreur du RAG (« J'étudie en Guadeloupe… ») vient d'un écart de vocabulaire avec la fiche
  (« outre-mer ») ; l'agent la corrige en reformulant sa recherche.
- L'**extension (reranking)** place plus souvent la bonne fiche en tête (MRR 0,94 → 0,98) mais
  n'améliore pas les réponses, déjà à 100 %, et ajoute ~1,5 s par requête. Elle introduit même une
  régression d'abstention (question sur le DSE 2027 : la fiche 2026, très proche, est prise pour la
  réponse). Sur ce corpus de petite taille, elle n'est donc pas rentable.

| Niveau | Contenu |
|---|---|
| 0 · LLM seul | prompt soigné, sans documents ni outils (référence à battre) |
| 1 · RAG | découpage par section, recherche hybride BM25 + dense (RRF), citations, abstention |
| 2 · Agent | 5 outils décrits en JSON, boucle bornée écrite à la main, confirmation des actions irréversibles |
| 3 · Extension | RAG avancé : reranking par cross-encoder, mesuré contre le niveau 2 |

## Installation

```bash
python -m venv .venv && source .venv/bin/activate   # Windows : .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env        # puis choisir le LLM (Ollama local, Groq, Mistral…)
```

Avec Ollama : `ollama pull qwen2.5:7b-instruct` (modèle ouvert qui gère l'appel d'outils).

## Utilisation

```bash
streamlit run app.py        # interface (choix du niveau, sources, coûts, trace)
python eval.py              # reproduit le tableau de résultats -> results/tableau.md
python eval.py --levels 0 1 --no-pass3    # évaluation partielle, plus rapide
pytest                      # tests des règles métier (sans LLM)
```

## Structure

```
data/corpus/        10 fiches (bourse, barème, DSE, droits, aides complémentaires, CVEC,
                    repas, aides au logement, Visale/Loca-Pass, logement Crous), sources indiquées
data/tests.jsonl    42 cas : 22 réponses dans les documents, 5 absentes, 10 tâches, 5 ambiguës/hors sujet
scripts/build_tests.py   génère tests.jsonl (modifier ce script, pas le JSONL)
src/rag.py          découpage, BM25, embeddings, fusion RRF, reranking
src/tools.py        outils, schémas JSON, classement par effet, règles métier
src/agent.py        boucle de l'agent (sans framework)
src/levels.py       les 4 niveaux, même interface
src/tracing.py      traces JSONL (logs/)
eval.py             métriques et tableau
app.py              interface Streamlit
```

## Choix techniques

- **Découpage par section** : les fiches sont courtes et organisées en sections « ## » ;
  une section = une idée (50 à 250 mots). Le titre de la fiche est ajouté pour le contexte.
- **Embeddings** : `multilingual-e5-small` (français, léger, tourne sans GPU).
- **Recherche hybride** : BM25 trouve les chiffres et termes exacts (« CVEC », « Loca-Pass »),
  le dense trouve les reformulations (« Guadeloupe » → « outre-mer » : cas raté par BM25 seul).
- **Citations** : chaque extrait porte l'identifiant de sa fiche, le modèle cite `[id]`.
- **Abstention** : consigne « Je ne sais pas » si les extraits ne contiennent pas la réponse.

## Outils de l'agent

| Outil | Effet | Règles vérifiées par du code |
|---|---|---|
| `rechercher_documents` | lecture | — |
| `verifier_eligibilite_bourse` | lecture | points de charge, plafonds 2026-2027, âge < 28 ans (40 si handicap) |
| `calcul_budget` | lecture | montants numériques |
| `generer_courrier` | réversible (brouillon) | type de demande valide |
| `envoyer_demande` | **irréversible** → confirmation | bourse : éligibilité positive vérifiée avant ; CVEC : boursier ; logement : ville |

La boucle s'arrête après `AGENT_MAX_STEPS` appels LLM ou `AGENT_MAX_TOKENS` tokens.
Les erreurs d'outils sont renvoyées au modèle pour qu'il se corrige.
Les envois sont simulés : ils sont écrits dans un dossier de session (`envois/*.json`), ce qui permet
de vérifier l'état final par du code.

## Évaluation

- Recherche : Recall@5 et MRR (au niveau des fiches).
- Réponse : exactitude par règles (valeurs attendues dans la réponse), citation de la bonne source.
- Abstention sur les 5 cas absents ; question de précision ou refus sur les 5 cas ambigus.
- Agent : succès sur l'état final, pass^3 (3 essais réussis sur 3) sur les 10 tâches.
- Coût : tokens et latence moyens par requête.

Les résultats bruts par niveau sont dans `results/`, les traces dans `logs/`.

## Sources du corpus

Fiches rédigées par l'équipe à partir des informations officielles (2026-2027) :
service-public.fr, etudiant.gouv.fr, lescrous.fr, cvec.etudiant.gouv.fr, caf.fr,
actionlogement.fr / visale.fr. La source de chaque fiche est indiquée en tête de fichier.

## Équipe

Projet réalisé par **Julia Ezzedine** et **Talia Toutah** (ECE Paris, Section 2).

| Membre | Contributions |
|---|---|
| Talia Toutah | Mise en place du dépôt et de l'environnement, intégration du LLM (Gemini), évaluation des 4 niveaux, interface Streamlit |
| Julia Ezzedine | Vérification du corpus (bourses, CVEC), analyse des échecs, rapport et vidéo |
