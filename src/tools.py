"""Outils de l'agent : schémas JSON, classement par effet, règles métier vérifiées par du code.

Effets :
- "lecture"      : ne modifie rien (recherche, calculs)
- "reversible"   : écrit un brouillon, qu'on peut supprimer (courrier)
- "irreversible" : envoie une demande -> confirmation de l'utilisateur OBLIGATOIRE
"""
import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path


class ToolError(Exception):
    """Erreur renvoyée au modèle (il peut corriger ses arguments et réessayer)."""


# ---------------------------------------------------------------------------
# Barème 2026-2027 (identique à data/corpus/bourse_*.md)
# ---------------------------------------------------------------------------
ECHELONS = ["0bis", "1", "2", "3", "4", "5", "6", "7"]
MONTANTS_ANNUELS = {"0bis": 1454, "1": 2163, "2": 3071, "3": 3828,
                    "4": 4587, "5": 5212, "6": 5506, "7": 6335}
PLAFONDS = {  # points de charge -> plafonds pour 0bis, 1, ..., 7
    0: [35086, 23850, 19281, 17034, 14829, 12667, 7992, 265],
    1: [38966, 26500, 21423, 18921, 16472, 14077, 8872, 530],
    2: [42877, 29150, 23564, 20818, 18126, 15476, 9773, 795],
    3: [46767, 31800, 25705, 22716, 19758, 16875, 10653, 1060],
    4: [50668, 34450, 27846, 24603, 21412, 18285, 11533, 1325],
    5: [54569, 37111, 29998, 26500, 23066, 19695, 12434, 1590],
    6: [58459, 39761, 32139, 28376, 24709, 21105, 13324, 1855],
    8: [66261, 45061, 36422, 32171, 28005, 23914, 15094, 2385],
    10: [74052, 50361, 40704, 35955, 31291, 26733, 16865, 2915],
}
AGE_MAX_PREMIERE_DEMANDE = 28


def points_distance(distance_km: float) -> int:
    if distance_km < 30:
        return 0
    if distance_km < 250:
        return 1
    if distance_km < 3500:
        return 2
    if distance_km < 13000:
        return 3
    return 4


def calcul_points(distance_km: float, freres_soeurs_a_charge: int = 0,
                  freres_soeurs_etudiants_sup: int = 0, handicap: bool = False,
                  aidant: bool = False) -> int:
    return (points_distance(distance_km) + 2 * freres_soeurs_a_charge
            + 4 * freres_soeurs_etudiants_sup + (4 if handicap else 0) + (4 if aidant else 0))


def echelon_pour(revenu: float, points: int) -> str | None:
    if points not in PLAFONDS:
        raise ToolError(f"Le barème pour {points} points n'est pas disponible dans le corpus "
                        f"(lignes disponibles : {sorted(PLAFONDS)}). Orienter vers le simulateur du Crous.")
    best = None
    for ech, plafond in zip(ECHELONS, PLAFONDS[points]):
        if revenu <= plafond:
            best = ech
    return best


# ---------------------------------------------------------------------------
# État d'une session (isolé par exécution : indispensable pour l'évaluation)
# ---------------------------------------------------------------------------
@dataclass
class Session:
    workdir: Path
    eligibilites: list = field(default_factory=list)
    budgets: list = field(default_factory=list)

    def __post_init__(self):
        (self.workdir / "brouillons").mkdir(parents=True, exist_ok=True)
        (self.workdir / "envois").mkdir(parents=True, exist_ok=True)

    def envois(self) -> list[dict]:
        return [json.loads(p.read_text(encoding="utf-8"))
                for p in sorted((self.workdir / "envois").glob("*.json"))]

    def brouillons(self) -> list[dict]:
        return [json.loads(p.read_text(encoding="utf-8"))
                for p in sorted((self.workdir / "brouillons").glob("*.json"))]


# ---------------------------------------------------------------------------
# Implémentation des outils
# ---------------------------------------------------------------------------
def verifier_eligibilite_bourse(session: Session, revenu_brut_global: float, age: int,
                                distance_km: float, freres_soeurs_a_charge: int = 0,
                                freres_soeurs_etudiants_sup: int = 0, handicap: bool = False,
                                aidant: bool = False, premiere_demande: bool = True) -> dict:
    if revenu_brut_global < 0 or distance_km < 0 or age <= 0:
        raise ToolError("Valeurs négatives ou nulles impossibles.")
    age_limite = 40 if handicap else AGE_MAX_PREMIERE_DEMANDE
    points = calcul_points(distance_km, freres_soeurs_a_charge, freres_soeurs_etudiants_sup,
                           handicap, aidant)
    result = {"points_de_charge": points, "revenu_brut_global": revenu_brut_global}
    if premiere_demande and age >= age_limite:
        result.update(eligible=False, echelon=None,
                      motif=f"Âge : il faut avoir moins de {age_limite} ans lors de la première demande.")
    else:
        ech = echelon_pour(revenu_brut_global, points)
        if ech is None:
            result.update(eligible=False, echelon=None,
                          motif="Revenu supérieur au plafond de l'échelon 0 bis.")
        else:
            result.update(eligible=True, echelon=ech, montant_annuel=MONTANTS_ANNUELS[ech],
                          montant_mensuel=round(MONTANTS_ANNUELS[ech] / 10, 2))
    result["id"] = f"elig-{len(session.eligibilites) + 1}"
    session.eligibilites.append(result)
    return result


def calcul_budget(session: Session, revenus: dict, depenses: dict) -> dict:
    try:
        total_r = round(sum(float(v) for v in revenus.values()), 2)
        total_d = round(sum(float(v) for v in depenses.values()), 2)
    except (TypeError, ValueError):
        raise ToolError("Les montants doivent être des nombres (euros par mois).")
    result = {"total_revenus": total_r, "total_depenses": total_d,
              "reste_a_vivre": round(total_r - total_d, 2)}
    session.budgets.append(result)
    return result


TYPES_DEMANDE = {"bourse", "logement_crous", "remboursement_cvec"}


def generer_courrier(session: Session, type_demande: str, nom: str, contenu: str) -> dict:
    if type_demande not in TYPES_DEMANDE:
        raise ToolError(f"type_demande doit être parmi {sorted(TYPES_DEMANDE)}.")
    doc = {"id": f"brouillon-{uuid.uuid4().hex[:6]}", "type_demande": type_demande,
           "nom": nom, "contenu": contenu, "cree_le": datetime.now().isoformat(timespec="seconds")}
    (session.workdir / "brouillons" / f"{doc['id']}.json").write_text(
        json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"brouillon_id": doc["id"], "statut": "brouillon enregistré (non envoyé)"}


def envoyer_demande(session: Session, type_demande: str, nom: str, details: dict | None = None) -> dict:
    """Action irréversible. Règles métier vérifiées ici, pas par le modèle."""
    details = details or {}
    if type_demande not in TYPES_DEMANDE:
        raise ToolError(f"type_demande doit être parmi {sorted(TYPES_DEMANDE)}.")
    if not nom or not nom.strip():
        raise ToolError("Le nom de l'étudiant est obligatoire.")
    if type_demande == "bourse":
        # règle : une demande de bourse n'est envoyée qu'après une vérification d'éligibilité positive
        ok = [e for e in session.eligibilites if e.get("eligible")]
        if not ok:
            raise ToolError("Refusé : aucune vérification d'éligibilité positive dans cette session. "
                            "Appeler d'abord verifier_eligibilite_bourse.")
        details = {**details, "echelon": ok[-1]["echelon"], "eligibilite_id": ok[-1]["id"]}
    if type_demande == "remboursement_cvec" and not details.get("boursier"):
        raise ToolError("Refusé : seul un étudiant boursier (ou exonéré) peut demander le "
                        "remboursement de la CVEC. Indiquer details.boursier = true si c'est le cas.")
    if type_demande == "logement_crous" and not details.get("ville"):
        raise ToolError("La ville souhaitée (details.ville) est obligatoire.")
    envoi = {"id": f"envoi-{uuid.uuid4().hex[:6]}", "type_demande": type_demande, "nom": nom,
             "details": details, "envoye_le": datetime.now().isoformat(timespec="seconds")}
    (session.workdir / "envois" / f"{envoi['id']}.json").write_text(
        json.dumps(envoi, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"envoi_id": envoi["id"], "statut": "demande envoyée", "details": details}


# ---------------------------------------------------------------------------
# Schémas JSON exposés au modèle
# ---------------------------------------------------------------------------
TOOL_SPECS = {
    "rechercher_documents": {
        "effet": "lecture",
        "description": "Cherche dans les fiches officielles (bourses, CVEC, logement, repas Crous). "
                       "Renvoie des extraits avec leur identifiant de source à citer entre crochets.",
        "parameters": {"type": "object", "properties": {
            "requete": {"type": "string", "description": "La question ou les mots-clés"}},
            "required": ["requete"]},
    },
    "verifier_eligibilite_bourse": {
        "effet": "lecture",
        "description": "Calcule les points de charge et l'échelon de bourse sur critères sociaux "
                       "selon le barème 2026-2027. À appeler avant toute demande de bourse.",
        "parameters": {"type": "object", "properties": {
            "revenu_brut_global": {"type": "number", "description": "Revenu brut global des parents (€)"},
            "age": {"type": "integer"},
            "distance_km": {"type": "number", "description": "Distance domicile familial - lieu d'études"},
            "freres_soeurs_a_charge": {"type": "integer", "description": "Autres enfants à charge NON étudiants dans le supérieur"},
            "freres_soeurs_etudiants_sup": {"type": "integer", "description": "Autres enfants à charge étudiants dans le supérieur"},
            "handicap": {"type": "boolean"},
            "aidant": {"type": "boolean"},
            "premiere_demande": {"type": "boolean"}},
            "required": ["revenu_brut_global", "age", "distance_km"]},
    },
    "calcul_budget": {
        "effet": "lecture",
        "description": "Calcule le reste à vivre mensuel à partir des revenus et dépenses mensuels.",
        "parameters": {"type": "object", "properties": {
            "revenus": {"type": "object", "description": "ex. {\"bourse\": 458.7, \"job\": 300}",
                        "additionalProperties": {"type": "number"}},
            "depenses": {"type": "object", "description": "ex. {\"loyer\": 520}",
                         "additionalProperties": {"type": "number"}}},
            "required": ["revenus", "depenses"]},
    },
    "generer_courrier": {
        "effet": "reversible",
        "description": "Rédige un brouillon de courrier (non envoyé).",
        "parameters": {"type": "object", "properties": {
            "type_demande": {"type": "string", "enum": sorted(TYPES_DEMANDE)},
            "nom": {"type": "string"},
            "contenu": {"type": "string"}},
            "required": ["type_demande", "nom", "contenu"]},
    },
    "envoyer_demande": {
        "effet": "irreversible",
        "description": "ENVOIE une demande officielle (action irréversible, l'utilisateur devra confirmer). "
                       "bourse : nécessite une éligibilité vérifiée ; remboursement_cvec : details.boursier ; "
                       "logement_crous : details.ville.",
        "parameters": {"type": "object", "properties": {
            "type_demande": {"type": "string", "enum": sorted(TYPES_DEMANDE)},
            "nom": {"type": "string"},
            "details": {"type": "object"}},
            "required": ["type_demande", "nom"]},
    },
}


def openai_tools() -> list[dict]:
    return [{"type": "function", "function": {"name": n, "description": s["description"],
                                              "parameters": s["parameters"]}}
            for n, s in TOOL_SPECS.items()]


IMPLEMENTATIONS = {
    "verifier_eligibilite_bourse": verifier_eligibilite_bourse,
    "calcul_budget": calcul_budget,
    "generer_courrier": generer_courrier,
    "envoyer_demande": envoyer_demande,
}
