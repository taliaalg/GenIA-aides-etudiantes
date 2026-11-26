"""Interface Streamlit : `streamlit run app.py`.

Affiche l'historique des échanges, et pour chaque réponse : le niveau utilisé, les sources citées,
le coût (tokens, durée, appels au LLM) et la trace complète. Les actions irréversibles attendent
un clic de confirmation. Chaque question est traitée indépendamment (comme dans l'évaluation).
"""
import html
import time

import streamlit as st

from src.levels import LEVELS, cited_sources
from src.tracing import log_trace

st.set_page_config(page_title="Assistant Aides étudiantes", layout="wide")

# ---------------------------------------------------------------------------
# Style
# ---------------------------------------------------------------------------
LEVEL_COLORS = {0: "#64748B", 1: "#0F766E", 2: "#1D4ED8", 3: "#7C3AED"}

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');
html, body, [class*="css"], .stMarkdown, button, input, textarea { font-family: 'Inter', sans-serif; }
header[data-testid="stHeader"] { display: none; }
#MainMenu, footer, [data-testid="stToolbar"] { visibility: hidden; }
.block-container, [data-testid="stBottomBlockContainer"] { max-width: 1150px; padding-left: 3rem;
         padding-right: 3rem; }
.block-container { padding-top: 1.5rem; }

.hero { padding: 1.6rem 1.8rem; border-radius: 14px; margin-bottom: 1.6rem;
        background: #0C447C; color: #fff; display: flex; justify-content: space-between;
        align-items: flex-end; gap: 1rem; flex-wrap: wrap; }
.hero .over { font-size: .75rem; letter-spacing: .14em; text-transform: uppercase; opacity: .75; }
.hero h1 { font-size: 2rem; font-weight: 700; margin: .3rem 0 .4rem; color: #fff; padding: 0; }
.hero p { margin: 0; opacity: .85; font-size: .95rem; }
.hero .team { text-align: right; font-size: .85rem; line-height: 1.5; }
.hero .team .l { font-size: .68rem; letter-spacing: .14em; text-transform: uppercase; opacity: .7; }
.hero .team .n { font-weight: 600; }

.badge { display: inline-block; padding: .18rem .65rem; border-radius: 999px; font-size: .72rem;
         font-weight: 600; letter-spacing: .03em; color: #fff; margin-bottom: .5rem; }
.chips { margin: .6rem 0 .2rem; }
.chip { display: inline-block; padding: .15rem .6rem; margin: 0 .35rem .35rem 0; border-radius: 6px;
        background: #EEF2FF; color: #3730A3; font-size: .78rem; font-family: ui-monospace, monospace; }
.stats { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: .6rem; margin: .8rem 0 .6rem; }
.stat { background: #F1F5F9; border-radius: 10px; padding: .55rem .8rem; }
.stat .v { font-size: 1.1rem; font-weight: 600; color: #0F172A; }
.stat .l { font-size: .7rem; text-transform: uppercase; letter-spacing: .08em; color: #64748B; }
[data-testid="stChatMessage"] [data-testid="stVerticalBlockBorderWrapper"] { border-radius: 14px;
         border-color: #E2E8F0; background: #fff; }

.confirm { border: 1px solid #F59E0B; background: #FFFBEB; border-radius: 12px;
           padding: 1rem 1.2rem; margin: .4rem 0 .8rem; }
.confirm .t { font-weight: 600; color: #92400E; margin-bottom: .35rem; }
.confirm code { background: #FEF3C7; color: #78350F; }

section[data-testid="stSidebar"] { background: #F8FAFC; border-right: 1px solid #E5E7EB; }
.side-title { font-size: .72rem; font-weight: 600; letter-spacing: .12em; text-transform: uppercase;
              color: #64748B; margin: 1.2rem 0 .5rem; }
.side-desc { font-size: .85rem; color: #334155; background: #fff; border: 1px solid #E5E7EB;
             border-left: 3px solid var(--c); border-radius: 8px; padding: .6rem .75rem; }
section[data-testid="stSidebar"] .stButton button { justify-content: flex-start; text-align: left;
             border-radius: 8px; border: 1px solid #E5E7EB; background: #fff; font-size: .85rem; }
section[data-testid="stSidebar"] .stButton button > div,
section[data-testid="stSidebar"] .stButton button p { justify-content: flex-start; text-align: left;
             width: 100%; margin: 0; }
section[data-testid="stSidebar"] .block-container,
section[data-testid="stSidebarContent"] { padding-top: 1rem; }
section[data-testid="stSidebar"] .stButton button:hover { border-color: #1D4ED8; color: #1D4ED8; }
</style>
""", unsafe_allow_html=True)

st.markdown("""
<div class="hero">
  <div>
    <div class="over">Projet GenIA · ECE Paris · 2026</div>
    <h1>Assistant Aides étudiantes</h1>
    <p>Bourses Crous, CVEC, logement, restauration : quatre niveaux comparables sur la même question.</p>
  </div>
  <div class="team">
    <div class="l">Réalisé par</div>
    <div class="n">Julia Ezzedine</div>
    <div class="n">Talia Toutah</div>
  </div>
</div>
""", unsafe_allow_html=True)

# ---------------------------------------------------------------------------
# Barre latérale
# ---------------------------------------------------------------------------
DESCRIPTIONS = {
    0: "Le modèle répond seul, de mémoire, sans documents ni outils.",
    1: "Le modèle répond à partir des fiches officielles et cite ses sources.",
    2: "Le modèle cherche, calcule et agit avec des outils. Tout envoi est soumis à confirmation.",
    3: "Comme le niveau 2, avec une recherche affinée par reranking.",
}
EXEMPLES = {
    "Prix de la CVEC": "Combien coûte la CVEC pour l'année 2026-2027 ?",
    "Chambre Crous à Nantes": "Combien coûte une chambre en résidence Crous à Nantes ?",
    "Bourse en Guadeloupe": "J'étudie en Guadeloupe, ma bourse est-elle plus élevée ?",
    "Demande de bourse": ("Je m'appelle Camille Martin, j'ai 20 ans. Mes parents ont un revenu brut "
                          "global de 18 000 €, j'ai un petit frère au lycée et j'étudie à 300 km. "
                          "Vérifie mon échelon de bourse puis envoie ma demande."),
    "CVEC, non boursier": ("Je suis Camille Martin, je ne suis pas boursier mais j'ai payé la CVEC. "
                           "Envoie une demande de remboursement de la CVEC."),
}

with st.sidebar:
    st.markdown('<div class="side-title">Niveau</div>', unsafe_allow_html=True)
    level = st.radio("Niveau", options=list(LEVELS), format_func=lambda n: LEVELS[n].name,
                     label_visibility="collapsed")
    st.markdown(f'<div class="side-desc" style="--c:{LEVEL_COLORS[level]}">{DESCRIPTIONS[level]}</div>',
                unsafe_allow_html=True)
    st.markdown('<div class="side-title">Exemples</div>', unsafe_allow_html=True)
    for label, texte in EXEMPLES.items():
        if st.button(label, use_container_width=True, icon=":material/chevron_right:"):
            st.session_state["preset"] = texte
    st.markdown('<div class="side-title">Session</div>', unsafe_allow_html=True)
    if st.button("Nouvelle conversation", use_container_width=True, icon=":material/refresh:"):
        st.session_state.clear()
        st.rerun()
    st.caption("Chaque question est traitée indépendamment : l'historique sert à comparer "
               "les réponses des différents niveaux.")

history = st.session_state.setdefault("history", [])  # [{"question", "level", "res"}]


@st.cache_resource(show_spinner="Chargement du modèle et de l'index…")
def get_level(n: int):
    return LEVELS[n]()


# ---------------------------------------------------------------------------
# Affichage d'une réponse
# ---------------------------------------------------------------------------
USER_AVATAR, BOT_AVATAR = ":material/person:", ":material/school:"


def show_result(res: dict, lvl: int):
    with st.container(border=True):
        _show_result_body(res, lvl)


def _show_result_body(res: dict, lvl: int):
    st.markdown(f'<span class="badge" style="background:{LEVEL_COLORS[lvl]}">'
                f'{html.escape(LEVELS[lvl].name)}</span>', unsafe_allow_html=True)
    st.markdown(res["answer"])
    if res["sources"]:
        chips = "".join(f'<span class="chip">{html.escape(s)}</span>' for s in res["sources"])
        st.markdown(f'<div class="chips">{chips}</div>', unsafe_allow_html=True)
    stats = [("Tokens", f"{res['tokens']:,}".replace(",", " ")), ("Durée", f"{res['latency_s']:.1f} s"),
             ("Appels LLM", res["llm_calls"]), ("Sources", len(res["sources"]))]
    st.markdown('<div class="stats">' + "".join(
        f'<div class="stat"><div class="v">{v}</div><div class="l">{l}</div></div>' for l, v in stats)
        + "</div>", unsafe_allow_html=True)
    with st.expander("Trace de l'exécution", icon=":material/timeline:"):
        st.json(res["steps"])
    if res.get("session") is not None:
        envois = res["session"].envois()
        if envois:
            with st.expander(f"Demandes envoyées ({len(envois)})", icon=":material/send:"):
                st.json(envois)


# --- historique des échanges -------------------------------------------------
for item in history:
    with st.chat_message("user", avatar=USER_AVATAR):
        st.write(item["question"])
    with st.chat_message("assistant", avatar=BOT_AVATAR):
        show_result(item["res"], item["level"])

# --- nouvelle question -------------------------------------------------------
question = st.chat_input("Posez votre question, par exemple : combien coûte la CVEC ?")
question = question or st.session_state.pop("preset", None)
if question:
    with st.chat_message("user", avatar=USER_AVATAR):
        st.write(question)
    with st.spinner("Analyse en cours…"):
        res = get_level(level).answer(question, confirm=None)
    log_trace(level, question, res)
    history.append({"question": question, "level": level, "res": res})
    st.rerun()

# --- confirmation d'une action irréversible (dernier échange uniquement) -------
if history and history[-1]["res"]["status"] == "pending_confirmation":
    last = history[-1]
    pending = last["res"]
    call = pending["run"].pending_call
    st.markdown(f'<div class="confirm"><div class="t">Action irréversible : {html.escape(call["name"])}</div>'
                f'<code>{html.escape(call["arguments"])}</code></div>', unsafe_allow_html=True)
    c1, c2, _ = st.columns([1, 1, 3])
    decision = None
    if c1.button("Confirmer", key=f"ok-{len(history)}", type="primary", icon=":material/check:",
                 use_container_width=True):
        decision = True
    if c2.button("Refuser", key=f"no-{len(history)}", icon=":material/close:", use_container_width=True):
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
