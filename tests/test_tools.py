"""Tests unitaires des règles métier (sans LLM) : `pytest`."""
import pytest

from src.tools import (Session, ToolError, calcul_budget, calcul_points, echelon_pour,
                       envoyer_demande, verifier_eligibilite_bourse)


@pytest.fixture
def session(tmp_path):
    return Session(tmp_path)


def test_points():
    assert calcul_points(10) == 0
    assert calcul_points(300, freres_soeurs_a_charge=1) == 4
    assert calcul_points(260, 1, 1) == 8


def test_echelons():
    assert echelon_pour(20000, 0) == "1"       # exemple de la fiche
    assert echelon_pour(40000, 0) is None      # au-dessus du 0 bis
    assert echelon_pour(200, 0) == "7"
    with pytest.raises(ToolError):
        echelon_pour(10000, 7)                 # ligne absente du corpus


def test_age(session):
    r = verifier_eligibilite_bourse(session, 10000, 29, 50)
    assert r["eligible"] is False


def test_bourse_sans_eligibilite_refusee(session):
    with pytest.raises(ToolError):
        envoyer_demande(session, "bourse", "Camille")
    assert session.envois() == []


def test_bourse_apres_eligibilite(session):
    verifier_eligibilite_bourse(session, 18000, 20, 300, freres_soeurs_a_charge=1)
    envoyer_demande(session, "bourse", "Camille")
    assert session.envois()[0]["details"]["echelon"] == "5"


def test_cvec_non_boursier_refuse(session):
    with pytest.raises(ToolError):
        envoyer_demande(session, "remboursement_cvec", "Camille", {"boursier": False})


def test_budget(session):
    r = calcul_budget(session, {"bourse": 458.7, "job": 300, "apl": 180}, {"loyer": 520, "courses": 200})
    assert r["reste_a_vivre"] == 218.7


def test_budget_format_liste(session):
    r = calcul_budget(session, [{"libelle": "bourse", "montant": 458.7}, {"libelle": "job", "montant": 300},
                                {"libelle": "apl", "montant": 180}],
                      [{"libelle": "loyer", "montant": 520}, {"libelle": "courses", "montant": 200}])
    assert r["reste_a_vivre"] == 218.7


def test_schemas_sans_objet_libre():
    """Gemini refuse les objets sans 'properties' et les 'additionalProperties'."""
    import json
    from src.tools import openai_tools
    txt = json.dumps(openai_tools())
    assert "additionalProperties" not in txt
    def walk(s):
        if isinstance(s, dict):
            if s.get("type") == "object":
                assert s.get("properties"), s
            for v in s.values():
                walk(v)
        elif isinstance(s, list):
            for v in s:
                walk(v)
    for t in openai_tools():
        walk(t["function"]["parameters"])
