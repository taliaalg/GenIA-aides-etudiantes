\# Analyse des échecs



Cas tirés de l'évaluation du 26/11/2026 (`results/`) et des tests manuels dans l'interface.



\## 1. Niveau 0 : montant de la CVEC périmé

\- Question : « Combien coûte la CVEC pour l'année 2026-2027 ? »

\- Réponse : 103 € « pour l'année 2024-2025 », sans source.

\- Cause : le modèle répond de mémoire, avec des connaissances arrêtées à une année antérieure.

\- Correction : niveau 1 (RAG) — la réponse s'appuie sur la fiche à jour et cite \[cvec] (105 €).



\## 2. Niveau 1 : « J'étudie en Guadeloupe, ma bourse est-elle plus élevée ? » (doc\_06)

\- Réponse : incorrecte, la majoration de 300 € n'est pas retrouvée.

\- Cause : écart de vocabulaire entre la question (« Guadeloupe ») et la fiche (« outre-mer ») ;

&#x20; la section concernée n'est pas dans les 5 extraits fournis au modèle.

\- Correction : au niveau 2, l'agent reformule sa recherche (« outre-mer ») et trouve la bonne section.



\## 3. Niveaux 1 à 3 : APL ou ALS en résidence Crous (doc\_21)

\- Réponse : correcte (APL), mais la source citée n'est pas celle attendue

&#x20; (aides\_logement ou logement\_crous).

\- Cause : l'information figure dans deux fiches ; le modèle cite une fiche voisine.

\- Piste : demander dans la consigne de citer toutes les fiches utilisées ; accepter plusieurs sources dans le test.



\## 4. Niveau 3 : dates du DSE pour la rentrée 2027 (absent\_02)

\- Attendu : abstention (l'information n'est pas dans le corpus).

\- Réponse : l'assistant répond avec les dates 2026-2027.

\- Cause : le reranking place la fiche DSE 2026, très proche de la question, en première position ;

&#x20; le modèle la prend pour la réponse.

\- Piste : vérifier l'année demandée dans la consigne d'abstention ; seuil de pertinence.



\## 5. Niveau 2 : confirmation demandée en texte au lieu de l'outil

\- Question : demande de bourse avec envoi.

\- Comportement : l'agent calcule l'échelon puis demande « Confirmez-vous ? » par écrit,

&#x20; sans appeler l'outil envoyer\_demande ; aucune demande n'est envoyée.

\- Cause : consigne ambiguë (« l'utilisateur devra confirmer »).

\- Correction : consigne précisée (appeler directement l'outil, le système gère la confirmation).



\## Bonus : plantage sur un argument au mauvais format

\- Le modèle a envoyé la requête de recherche sous forme de liste au lieu d'un texte → plantage de l'évaluation.

\- Correction : conversion de l'argument et toute erreur d'outil renvoyée au modèle au lieu de faire planter l'agent.

