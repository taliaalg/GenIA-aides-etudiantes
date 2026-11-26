"""Interface Streamlit : `streamlit run app.py`.

Affiche l'historique des échanges, et pour chaque réponse : le niveau utilisé, les sources citées,
le coût (tokens, durée) et la trace complète. Les actions irréversibles attendent un clic de
confirmation. Chaque question est traitée indépendamment (comme dans l'évaluation).
"""
import time

import streamlit as st

from src.levels import LEVELS, cited_sources
from src.tracing import log_trace

st.set_page_config(page_title="Assistant Aides étudiantes", page_icon="🎓", layout="wide")
st.title("🎓 Assistant Aides étudiantes")
st.caption("Bourses Crous, CVEC, logement, repas : niveaux 0 à 3 comparables sur la même question.")

DESCRIPTIONS = {
    0: "Le modèle répond seul, de mémoire, sans documents ni outils.",
    1: "Le modèle répond à partir des fiches officielles et cite ses sources.",
    2: "Le modèle cherche, calcule et agit avec des outils (confirmation avant tout envoi).",
    3: "Comme le niveau 2, avec une recherche affinée par reranking.",
}
EXEMPLES = {
    "💶 Prix de la CVEC": "Combien coûte la CVEC pour l'année 2026-2027 ?",
    "🏠 Chambre Crous à Nantes": "Combien coûte une chambre en résidence Crous à Nantes ?",
    "🌴 Bourse en Guadeloupe": "J'étudie en Guadeloupe, ma bourse est-elle plus élevée ?",
    "📨 Demande de bourse": ("Je m'appelle Camille Martin, j'ai 20 ans. Mes parents ont un revenu brut "
                             "global de 18 000 €, j'ai un petit frère au lycée et j'étudie à 300 km. "
                             "Vérifie mon échelon de bourse puis envoie ma demande."),
    "⛔ CVEC non boursier": ("Je suis Camille Martin, je ne suis pas boursier mais j'ai payé la CVEC. "
                            "Envoie une demande de remboursement de la CVEC."),
}

with st.sidebar:
    st.header("⚙️ Réglages")
    level = st.radio("Niveau", options=list(LEVELS), format_func=lambda n: LEVELS[n].name)
    st.info(DESCRIPTIONS[level])
    st.subheader("💡 Exemples")
    for label, texte in EXEMPLES.items():
        if st.button(label, use_container_width=True):
            st.session_state["preset"] = texte
    st.divider()
    if st.button("🗑️ Nouvelle conversation", use_container_width=True):
        st.session_state.clear()
        st.rerun()
    st.caption("Chaque question est traitée indépendamment : l'historique sert à comparer "
               "les réponses des différents niveaux.")

history = st.session_state.setdefault("history", [])  # [{"question", "level", "res"}]


@st.cache_resource(show_spinner="Chargement du modèle et de l'index…")
def get_level(n: int):
    return LEVELS[n]()


def show_result(res: dict):
    st.markdown(res["answer"])
    cols = st.columns(4)
    cols[0].metric("Tokens", res["tokens"])
    cols[1].metric("Durée (s)", f"{res['latency_s']:.2f}")
    cols[2].metric("Appels LLM", res["llm_calls"])
    cols[3].metric("Sources citées", len(res["sources"]))
    if res["sources"]:
        st.write("**Sources :** " + ", ".join(f"`{s}`" for s in res["sources"]))
    with st.expander("Trace de l'exécution"):
        st.json(res["steps"])
    if res.get("session") is not None:
        envois = res["session"].envois()
        if envois:
            with st.expander(f"Demandes envoyées ({len(envois)})"):
                st.json(envois)


# --- historique des échanges -------------------------------------------------
for item in history:
    with st.chat_message("user"):
        st.write(item["question"])
    with st.chat_message("assistant"):
        st.caption(f"Niveau {LEVELS[item['level']].name}")
        show_result(item["res"])

# --- nouvelle question -------------------------------------------------------
question = st.chat_input("Posez votre question (ex. « Combien coûte la CVEC ? »)")
question = question or st.session_state.pop("preset", None)
if question:
    with st.chat_message("user"):
        st.write(question)
    with st.spinner("Réflexion…"):
        res = get_level(level).answer(question, confirm=None)
    log_trace(level, question, res)
    history.append({"question": question, "level": level, "res": res})
    st.rerun()

# --- confirmation d'une action irréversible (dernier échange uniquement) -------
if history and history[-1]["res"]["status"] == "pending_confirmation":
    last = history[-1]
    pending = last["res"]
    call = pending["run"].pending_call
    st.warning(f"⚠️ Action irréversible demandée : **{call['name']}**\n\n`{call['arguments']}`")
    c1, c2 = st.columns(2)
    decision = None
    if c1.button("✅ Confirmer", key=f"ok-{len(history)}"):
        decision = True
    if c2.button("❌ Refuser", key=f"no-{len(history)}"):
        decision = False
    if decision is not None:
        t0 = time.perf_counter()
        run = pending["agent"].resume(pending["run"], decision)
        last["res"] = {**pending, "answer": run.answer, "status": run.status, "steps": run.steps,
                       "tokens": run.tokens, "llm_calls": run.llm_calls, "run": run,
                       "sources": cited_sources(run.answer),
                       "latency_s": pending["latency_s"] + time.perf_counter() - t0}
        log_trace(last["level"], last["question"], last["res"])
        st.rerun()
