"""Client LLM minimal, compatible avec toute API au format OpenAI."""
import time
from dataclasses import dataclass, field

from openai import (APIConnectionError, BadRequestError, InternalServerError, OpenAI,
                    RateLimitError)

from . import config


@dataclass
class LLMResponse:
    content: str
    tool_calls: list = field(default_factory=list)  # [{"id", "name", "arguments"(str)}]
    prompt_tokens: int = 0
    completion_tokens: int = 0
    latency_s: float = 0.0
    raw_message: dict | None = None


class LLM:
    def __init__(self, model: str | None = None):
        self.client = OpenAI(base_url=config.LLM_BASE_URL, api_key=config.LLM_API_KEY)
        self.model = model or config.LLM_MODEL

    def _create(self, kwargs: dict):
        """Appel avec reprise automatique si l'API répond « trop de requêtes » (429)."""
        for attempt in range(6):
            try:
                return self.client.chat.completions.create(**kwargs)
            except BadRequestError as e:
                # affiche le message exact renvoyé par l'API (aide au diagnostic)
                body = getattr(e, "response", None)
                print(f"[LLM] requête refusée (400) : {body.text if body is not None else e}")
                raise
            except (RateLimitError, InternalServerError, APIConnectionError):
                if attempt == 5:
                    raise
                wait = 10 * (attempt + 1)
                print(f"[LLM] limite atteinte ou erreur serveur, nouvel essai dans {wait} s…")
                time.sleep(wait)

    def chat(self, messages: list[dict], tools: list[dict] | None = None) -> LLMResponse:
        kwargs = {"model": self.model, "messages": messages, "temperature": config.LLM_TEMPERATURE}
        if config.LLM_REASONING_EFFORT:
            # réduit le temps de « réflexion » des modèles qui raisonnent (Gemini, o-series…)
            kwargs["reasoning_effort"] = config.LLM_REASONING_EFFORT
        if tools:
            kwargs["tools"] = tools
        t0 = time.perf_counter()
        resp = self._create(kwargs)
        latency = time.perf_counter() - t0
        msg = resp.choices[0].message
        calls = [
            {"id": c.id, "name": c.function.name, "arguments": c.function.arguments or "{}"}
            for c in (msg.tool_calls or [])
        ]
        usage = resp.usage
        # On renvoie le message du modèle TEL QUEL (y compris les champs propres au fournisseur,
        # ex. la « thought signature » de Gemini 3, indispensable pour enchaîner les appels d'outils).
        raw = msg.model_dump(exclude_none=True)
        for key in ("refusal", "annotations", "audio", "function_call"):
            raw.pop(key, None)  # champs de réponse que certaines API refusent en entrée
        raw["role"] = "assistant"
        raw.setdefault("content", "")
        return LLMResponse(
            content=msg.content or "",
            tool_calls=calls,
            prompt_tokens=getattr(usage, "prompt_tokens", 0) or 0,
            completion_tokens=getattr(usage, "completion_tokens", 0) or 0,
            latency_s=latency,
            raw_message=raw,
        )
