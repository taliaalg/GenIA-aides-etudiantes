"""Génère data/tests.jsonl (42 cas). Modifiez ce script plutôt que le JSONL à la main.

Champs :
- id, type : doc | absent | tache | ambigu
- question
- sources_attendues : identifiants de fiches (une seule suffit)        [doc]
- doit_contenir : liste ; chaque élément est une chaîne ou une liste d'alternatives
- confirmer : réponse de l'utilisateur si l'agent demande une confirmation  [tache, ambigu]
- etat_final : vérifié par du code après l'exécution                       [tache, ambigu]
"""
import json
from pathlib import Path

NOM = "Camille Martin"
cases = []


def doc(i, q, sources, contenir):
    cases.append({"id": f"doc_{i:02d}", "type": "doc", "question": q,
                  "sources_attendues": sources, "doit_contenir": contenir})


def absent(i, q):
    cases.append({"id": f"absent_{i:02d}", "type": "absent", "question": q})


def ambigu(i, q, etat=None):
    c = {"id": f"ambigu_{i:02d}", "type": "ambigu", "question": q, "confirmer": False,
         "etat_final": etat or {"nb_envois": 0}}
    cases.append(c)


def tache(i, q, etat, confirmer=True, contenir=None):
    c = {"id": f"tache_{i:02d}", "type": "tache", "question": q, "confirmer": confirmer,
         "etat_final": etat}
    if contenir:
        c["doit_contenir"] = contenir
    cases.append(c)


B = "bourse_criteres_sociaux"
# --- 22 questions dont la réponse est dans les documents --------------------
doc(1, "Quel est le montant annuel de la bourse à l'échelon 0 bis ?", [B], ["1454"])
doc(2, "Combien touche par mois un étudiant boursier à l'échelon 4 ?", [B], ["458.7"])
doc(3, "Combien y a-t-il d'échelons de bourse sur critères sociaux ?", [B], ["8"])
doc(4, "Quel âge maximum pour faire une première demande de bourse Crous ?", [B], ["28"])
doc(5, "En combien de mensualités la bourse est-elle versée ?", [B], ["10"])
doc(6, "J'étudie en Guadeloupe, ma bourse est-elle plus élevée ?", [B], ["300"])
doc(7, "Combien coûte la CVEC pour l'année 2026-2027 ?", ["cvec"], ["105"])
doc(8, "Je suis boursière, est-ce que je dois payer la CVEC ?", ["cvec", B], [["exon", "nepaiepas", "pasapayer"]])
doc(9, "Jusqu'à quand peut-on demander le remboursement de la CVEC 2026-2027 ?", ["cvec"], ["31mai2027"])
doc(10, "Combien coûte un repas au restaurant universitaire pour un étudiant non boursier ?", ["repas_crous"], [["1€", "1euro"]])
doc(11, "Depuis quelle date le repas à 1 euro est-il ouvert à tous les étudiants ?", ["repas_crous"], ["4mai2026"])
doc(12, "De quoi ai-je besoin pour payer mon repas Crous à 1 euro ?", ["repas_crous"], ["izly"])
doc(13, "Combien d'années de bourse peut-on avoir au maximum, et combien en licence ?", ["droits_bourse"], ["7", "5"])
doc(14, "Combien de crédits ECTS faut-il avoir validés pour obtenir le 3e droit à bourse ?", ["droits_bourse"], ["60"])
doc(15, "J'ai eu mon bac mention très bien et je suis boursier, quel est le montant de l'aide au mérite ?", ["aides_complementaires"], ["900"])
doc(16, "Combien touche un boursier en mobilité internationale ?", ["aides_complementaires"], ["400"])
doc(17, "J'étudie à 300 km de chez mes parents, combien de points de charge cela me donne-t-il ?", ["bourse_points_plafonds"], ["2point"])
doc(18, "Jusqu'à quel âge un étudiant peut-il demander la garantie Visale ?", ["visale_locapass"], ["30"])
doc(19, "Quel est le montant maximum de l'avance Loca-Pass ?", ["visale_locapass"], ["1200"])
doc(20, "Combien de vœux de logement peut-on faire sur trouverunlogement.lescrous.fr ?", ["logement_crous"], ["10"])
doc(21, "Je loge dans une résidence Crous : je dois demander l'APL ou l'ALS ?", ["aides_logement", "logement_crous"], ["apl"])
doc(22, "Mes parents ont perdu une partie de leurs revenus, à partir de quelle baisse puis-je demander un réexamen de ma bourse ?", ["dse_calendrier"], ["15"])

# --- 5 questions dont la réponse n'est PAS dans les documents -> abstention ---
absent(1, "Quel est le montant exact de l'APL pour un studio à 600 € par mois à Lyon ?")
absent(2, "Quelles sont les dates de dépôt du DSE pour la rentrée 2027 ?")
absent(3, "Combien coûte une chambre en résidence Crous à Nantes ?")
absent(4, "Quelle aide la région Île-de-France donne-t-elle pour acheter un ordinateur ?")
absent(5, "Quel est le plafond de ressources de l'échelon 3 pour une famille avec 7 points de charge ?")

# --- 10 tâches en plusieurs étapes -> état final vérifié par du code ---------
tache(1, f"Je m'appelle {NOM}, j'ai 20 ans. Mes parents ont un revenu brut global de 18 000 €, "
         "j'ai un petit frère au lycée et j'étudie à 300 km de chez eux. Vérifie mon échelon de bourse "
         "puis envoie ma demande de bourse.",
      {"nb_envois": 1, "envoi": {"type_demande": "bourse", "details.echelon": "5"}})
tache(2, f"Je suis {NOM}, 19 ans, enfant unique. Mes parents gagnent 40 000 € de revenu brut global et "
         "j'étudie à 10 km de chez eux. Vérifie si j'ai droit à la bourse et, si oui, envoie la demande.",
      {"nb_envois": 0, "derniere_eligibilite": {"eligible": False}})
tache(3, f"{NOM}, 21 ans. Revenu brut global de mes parents : 30 000 €. J'ai deux sœurs au collège et "
         "j'étudie à 100 km. Calcule mon échelon et envoie ma demande de bourse.",
      {"nb_envois": 1, "envoi": {"type_demande": "bourse", "details.echelon": "1"}})
tache(4, f"Je m'appelle {NOM}, j'ai 29 ans et je reprends mes études. C'est ma première demande de bourse. "
         "Mes parents ont 10 000 € de revenu brut global, j'étudie à 50 km. Envoie ma demande de bourse.",
      {"nb_envois": 0, "derniere_eligibilite": {"eligible": False}})
tache(5, f"Je m'appelle {NOM}, j'ai 20 ans. Mes parents ont un revenu brut global de 18 000 €, "
         "j'ai un petit frère au lycée et j'étudie à 300 km de chez eux. Vérifie mon échelon et "
         "prépare l'envoi de ma demande de bourse.",
      {"nb_envois": 0}, confirmer=False)
tache(6, f"Je suis {NOM}, boursière échelon 3, et j'ai payé la CVEC en septembre. "
         "Envoie ma demande de remboursement de la CVEC.",
      {"nb_envois": 1, "envoi": {"type_demande": "remboursement_cvec"}})
tache(7, f"Je suis {NOM}, je ne suis pas boursier mais j'ai payé la CVEC. Envoie une demande de "
         "remboursement de la CVEC.",
      {"nb_envois": 0})
tache(8, "Je touche la bourse échelon 4 (458,70 € par mois), je gagne 300 € avec un job étudiant et je "
         "reçois 180 € d'APL. Mon loyer est de 520 € et je dépense 200 € en courses. "
         "Calcule mon reste à vivre mensuel.",
      {"nb_envois": 0, "budget": {"reste_a_vivre": 218.7}}, contenir=["218.7"])
tache(9, f"Envoie une demande de logement Crous à Lyon au nom de {NOM}.",
      {"nb_envois": 1, "envoi": {"type_demande": "logement_crous", "details.ville": "lyon"}})
tache(10, f"{NOM}, 22 ans. Mes parents ont 33 000 € de revenu brut global. J'ai un frère étudiant à "
          "l'université et une sœur au collège, et j'étudie à 260 km. Vérifie mon échelon puis "
          "envoie ma demande de bourse.",
      {"nb_envois": 1, "envoi": {"type_demande": "bourse", "details.echelon": "2"}})

# --- 5 demandes ambiguës ou hors sujet -> question de précision ou refus -----
ambigu(1, "J'ai besoin d'une aide.")
ambigu(2, "Combien je vais toucher ?")
ambigu(3, "Écris-moi un poème sur la mer.")
ambigu(4, "Quelle équipe a gagné la dernière Ligue des champions ?")
ambigu(5, "Envoie ma demande.")

out = Path(__file__).resolve().parent.parent / "data" / "tests.jsonl"
with open(out, "w", encoding="utf-8") as f:
    for c in cases:
        f.write(json.dumps(c, ensure_ascii=False) + "\n")
print(f"{len(cases)} cas écrits dans {out}")
