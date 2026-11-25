"""Interface Streamlit : `streamlit run app.py`.

Affiche la réponse, les sources citées, le niveau choisi, le coût (tokens, durée)
et la trace complète. Les actions irréversibles attendent un clic de confirmation.
"""
import time

import streamlit as st

from src.levels import LEVELS, cited_sources
from src.tracing import log_trace

st.set_page_config(page_title="Assistant Aides étudiantes", page_icon="🎓", layout="wide")
st.title("🎓 Assistant Aides étudiantes")
st.caption("Bourses Crous, CVEC, logement, repas : niveaux 0 à 3 comparables sur la même question.")

level = st.sidebar.radio("Niveau", options=list(LEVELS), format_func=lambda n: LEVELS[n].name)
if st.sidebar.button("Nouvelle conversation"):
    st.session_state.clear()


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


question = st.chat_input("Posez votre question (ex. « Combien coûte la CVEC ? »)")
if question:
    st.session_state.pop("pending", None)
    with st.chat_message("user"):
        st.write(question)
    with st.spinner("Réflexion…"):
        res = get_level(level).answer(question, confirm=None)
    log_trace(level, question, res)
    st.session_state["last"] = res
    st.session_state["question"] = question
    if res["status"] == "pending_confirmation":
        st.session_state["pending"] = res

res = st.session_state.get("last")
if res:
    with st.chat_message("assistant"):
        show_result(res)

pending = st.session_state.get("pending")
if pending:
    call = pending["run"].pending_call
    st.warning(f"⚠️ Action irréversible demandée : **{call['name']}**\n\n`{call['arguments']}`")
    c1, c2 = st.columns(2)
    decision = None
    if c1.button("✅ Confirmer"):
        decision = True
    if c2.button("❌ Refuser"):
        decision = False
    if decision is not None:
        t0 = time.perf_counter()
        run = pending["agent"].resume(pending["run"], decision)
        new = {**pending, "answer": run.answer, "status": run.status, "steps": run.steps,
               "tokens": run.tokens, "llm_calls": run.llm_calls, "run": run,
               "sources": cited_sources(run.answer),
               "latency_s": pending["latency_s"] + time.perf_counter() - t0}
        log_trace(level, st.session_state["question"], new)
        st.session_state["last"] = new
        st.session_state["pending"] = new if run.status == "pending_confirmation" else None
        st.rerun()
