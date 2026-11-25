"""Les 4 niveaux, avec la même interface : answer(question, confirm=None) -> dict.

0 : LLM seul          1 : RAG          2 : agent outillé
3 : extension = agent + RAG avancé (reranking par cross-encoder), mesurée contre le niveau 2
"""
import re
import tempfile
import time
from pathlib import Path

from .agent import Agent
from .llm import LLM
from .rag import Retriever
from .tools import Session

SYSTEM_L0 = """Tu es un assistant qui répond aux questions des étudiants sur les aides (bourses Crous,
CVEC, logement, repas). Réponds en français, de façon concise et précise.
Si tu n'es pas sûr de la réponse, commence par « Je ne sais pas ».
Si la question est hors sujet, commence par « Hors sujet ».
Si la question est ambiguë, pose une question de précision."""

SYSTEM_L1 = """Tu es l'assistant « Aides étudiantes ». Réponds UNIQUEMENT à partir des extraits fournis.
- Chaque affirmation cite sa source entre crochets, ex. [bourse_criteres_sociaux].
- Si les extraits ne contiennent pas la réponse, réponds exactement en commençant par « Je ne sais pas ».
- Si la question est hors sujet, commence par « Hors sujet ».
- Si la question est ambiguë, pose une question de précision.
Réponds en français, de façon concise."""

CITATION_RE = re.compile(r"\[([a-z0-9_]+)\]")


def cited_sources(text: str) -> list[str]:
    return sorted(set(CITATION_RE.findall(text)))


class Level0:
    name = "0 · LLM seul"

    def __init__(self, llm=None):
        self.llm = llm or LLM()

    def answer(self, question, confirm=None, workdir=None):
        r = self.llm.chat([{"role": "system", "content": SYSTEM_L0},
                           {"role": "user", "content": question}])
        return {"answer": r.content, "sources": [], "retrieved": [],
                "tokens": r.prompt_tokens + r.completion_tokens, "latency_s": r.latency_s,
                "llm_calls": 1, "steps": [{"type": "llm", "tokens": r.prompt_tokens + r.completion_tokens}],
                "status": "done", "session": None}


class Level1:
    name = "1 · RAG"

    def __init__(self, retriever=None, llm=None):
        self.retriever = retriever or Retriever()
        self.llm = llm or LLM()

    def answer(self, question, confirm=None, workdir=None):
        t0 = time.perf_counter()
        chunks = self.retriever.search(question)
        context = "\n\n".join(c.as_context() for c in chunks)
        r = self.llm.chat([{"role": "system", "content": SYSTEM_L1},
                           {"role": "user", "content": f"Extraits :\n{context}\n\nQuestion : {question}"}])
        return {"answer": r.content, "sources": cited_sources(r.content),
                "retrieved": [c.doc_id for c in chunks],
                "tokens": r.prompt_tokens + r.completion_tokens,
                "latency_s": time.perf_counter() - t0, "llm_calls": 1,
                "steps": [{"type": "retrieval", "docs": [c.doc_id for c in chunks]},
                          {"type": "llm", "tokens": r.prompt_tokens + r.completion_tokens}],
                "status": "done", "session": None}


class Level2:
    name = "2 · Agent"

    def __init__(self, retriever=None, llm=None):
        self.retriever = retriever or Retriever()
        self.llm = llm or LLM()

    def answer(self, question, confirm=None, workdir=None):
        """confirm(call) -> bool : appelé si l'agent veut faire une action irréversible.
        Si confirm est None, on renvoie l'état « pending_confirmation » (cas de l'interface)."""
        t0 = time.perf_counter()
        session = Session(Path(workdir or tempfile.mkdtemp(prefix="session-")))
        agent = Agent(self.retriever, session, self.llm)
        run = agent.start(question)
        while run.status == "pending_confirmation" and confirm is not None:
            run = agent.resume(run, bool(confirm(run.pending_call)))
        return {"answer": run.answer, "sources": cited_sources(run.answer),
                "retrieved": list(dict.fromkeys(run.sources)), "tokens": run.tokens,
                "latency_s": time.perf_counter() - t0, "llm_calls": run.llm_calls,
                "steps": run.steps, "status": run.status, "session": session,
                "agent": agent, "run": run}


class Level3(Level2):
    name = "3 · Agent + reranking"

    def __init__(self, retriever=None, llm=None):
        super().__init__(retriever or Retriever(rerank=True), llm)


LEVELS = {0: Level0, 1: Level1, 2: Level2, 3: Level3}
