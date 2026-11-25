"""Boucle d'agent écrite SANS framework (exigence du sujet).

- boucle bornée : nombre d'étapes et budget de tokens
- erreurs d'outils renvoyées au modèle (il peut se corriger)
- action irréversible -> l'agent s'arrête et attend la confirmation de l'utilisateur
"""
import json
import time
from dataclasses import dataclass, field

from . import config
from .llm import LLM
from .rag import Retriever
from .tools import IMPLEMENTATIONS, TOOL_SPECS, Session, ToolError, openai_tools

SYSTEM_AGENT = """Tu es l'assistant « Aides étudiantes » (bourses Crous, CVEC, logement, repas).
Règles :
- Pour toute question factuelle, appelle rechercher_documents et cite les sources entre crochets, ex. [cvec].
- Si les documents ne contiennent pas la réponse, réponds en commençant par « Je ne sais pas » et n'invente rien.
- Si la demande est ambiguë ou qu'il manque une information pour agir, pose UNE question de précision.
- Si la demande est hors sujet, refuse poliment en commençant par « Hors sujet ».
- Avant une demande de bourse, appelle verifier_eligibilite_bourse. Ne fais jamais le calcul toi-même.
- N'envoie une demande (envoyer_demande) que si l'utilisateur le demande ; il devra confirmer.
- Réponds en français, de façon concise."""


@dataclass
class AgentRun:
    messages: list
    status: str = "running"            # running | pending_confirmation | done | stopped
    answer: str = ""
    pending_call: dict | None = None
    steps: list = field(default_factory=list)   # trace : une entrée par appel LLM / outil
    prompt_tokens: int = 0
    completion_tokens: int = 0
    llm_calls: int = 0
    sources: list = field(default_factory=list)
    started: float = field(default_factory=time.perf_counter)

    @property
    def tokens(self) -> int:
        return self.prompt_tokens + self.completion_tokens


class Agent:
    def __init__(self, retriever: Retriever, session: Session, llm: LLM | None = None):
        self.retriever = retriever
        self.session = session
        self.llm = llm or LLM()
        self.tools = openai_tools()

    # -- exécution d'un outil -------------------------------------------------
    def _execute(self, run: AgentRun, call: dict) -> str:
        name = call["name"]
        t0 = time.perf_counter()
        try:
            args = json.loads(call["arguments"] or "{}")
            if name == "rechercher_documents":
                chunks = self.retriever.search(args["requete"])
                run.sources.extend(c.doc_id for c in chunks)
                result = "\n\n".join(c.as_context() for c in chunks)
            elif name in IMPLEMENTATIONS:
                result = json.dumps(IMPLEMENTATIONS[name](self.session, **args), ensure_ascii=False)
            else:
                raise ToolError(f"Outil inconnu : {name}")
            ok = True
        except (ToolError, TypeError, KeyError, json.JSONDecodeError) as e:
            result, ok = f"ERREUR: {e}", False
        run.steps.append({"type": "tool", "name": name, "arguments": call["arguments"],
                          "ok": ok, "result": result[:500],
                          "duree_s": round(time.perf_counter() - t0, 3)})
        return result

    def _tool_message(self, call: dict, content: str) -> dict:
        return {"role": "tool", "tool_call_id": call["id"], "content": content}

    # -- boucle principale ----------------------------------------------------
    def start(self, question: str, history: list | None = None) -> AgentRun:
        messages = [{"role": "system", "content": SYSTEM_AGENT}] + (history or []) + \
                   [{"role": "user", "content": question}]
        return self._loop(AgentRun(messages=messages))

    def resume(self, run: AgentRun, approved: bool) -> AgentRun:
        """Reprend après la demande de confirmation d'une action irréversible."""
        call = run.pending_call
        run.pending_call = None
        run.steps.append({"type": "confirmation", "name": call["name"], "approuve": approved})
        if approved:
            content = self._execute(run, call)
        else:
            content = "ANNULÉ : l'utilisateur a refusé cette action. Ne pas la refaire."
        run.messages.append(self._tool_message(call, content))
        run.status = "running"
        return self._loop(run)

    def _loop(self, run: AgentRun) -> AgentRun:
        while run.llm_calls < config.AGENT_MAX_STEPS:
            if run.tokens > config.AGENT_MAX_TOKENS:
                run.status, run.answer = "stopped", "Arrêt : budget de tokens dépassé."
                return run
            resp = self.llm.chat(run.messages, tools=self.tools)
            run.llm_calls += 1
            run.prompt_tokens += resp.prompt_tokens
            run.completion_tokens += resp.completion_tokens
            run.steps.append({"type": "llm", "tokens": resp.prompt_tokens + resp.completion_tokens,
                              "duree_s": round(resp.latency_s, 3),
                              "tool_calls": [c["name"] for c in resp.tool_calls]})
            run.messages.append(resp.raw_message)
            if not resp.tool_calls:
                run.status, run.answer = "done", resp.content
                return run
            for i, call in enumerate(resp.tool_calls):
                if TOOL_SPECS.get(call["name"], {}).get("effet") == "irreversible":
                    # on répond « reporté » aux appels suivants éventuels du même tour
                    for later in resp.tool_calls[i + 1:]:
                        run.messages.append(self._tool_message(later, "REPORTÉ : en attente de confirmation."))
                    run.status, run.pending_call = "pending_confirmation", call
                    run.answer = f"Confirmez-vous l'action « {call['name']} » avec {call['arguments']} ?"
                    return run
                run.messages.append(self._tool_message(call, self._execute(run, call)))
        run.status, run.answer = "stopped", "Arrêt : nombre maximal d'étapes atteint."
        return run
