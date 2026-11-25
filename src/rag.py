"""RAG : découpage, index BM25 + dense, fusion RRF, reranking optionnel (niveau 3).

Choix de découpage : les fiches sont courtes et structurées par sections « ## ».
On découpe donc par section (une idée = un morceau, 50 à 250 mots), en préfixant
chaque morceau par le titre de la fiche pour garder le contexte.
"""
import re
import unicodedata
from dataclasses import dataclass

from rank_bm25 import BM25Okapi

from . import config


@dataclass
class Chunk:
    doc_id: str      # nom du fichier sans extension, sert de référence de citation
    title: str       # titre de la fiche
    section: str     # titre de la section
    text: str

    def as_context(self) -> str:
        return f"[{self.doc_id}] {self.title} — {self.section}\n{self.text}"


def load_chunks(corpus_dir=config.CORPUS_DIR) -> list[Chunk]:
    chunks = []
    for path in sorted(corpus_dir.glob("*.md")):
        raw = path.read_text(encoding="utf-8")
        title_match = re.search(r"^# (.+)$", raw, flags=re.M)
        title = title_match.group(1).strip() if title_match else path.stem
        parts = re.split(r"^## ", raw, flags=re.M)
        intro = parts[0]
        # l'intro (titre + source) est rattachée comme section « Présentation »
        intro_text = re.sub(r"^# .+$", "", intro, flags=re.M).strip()
        if intro_text:
            chunks.append(Chunk(path.stem, title, "Présentation", intro_text))
        for part in parts[1:]:
            lines = part.strip().split("\n", 1)
            section = lines[0].strip()
            body = lines[1].strip() if len(lines) > 1 else ""
            chunks.append(Chunk(path.stem, title, section, body))
    return chunks


_STOP = set("le la les de des du un une et en à au aux pour par sur est sont ce qui que quoi "
            "je j mon ma mes il elle on d l a y ne pas se sa son ses dans avec ou".split())


def tokenize(text: str) -> list[str]:
    text = unicodedata.normalize("NFD", text.lower())
    text = "".join(c for c in text if unicodedata.category(c) != "Mn")
    return [t for t in re.findall(r"[a-z0-9]+", text) if t not in _STOP]


class Retriever:
    """Recherche hybride : BM25 + embeddings denses, fusion par Reciprocal Rank Fusion."""

    def __init__(self, mode: str = config.RETRIEVER, rerank: bool = False):
        self.chunks = load_chunks()
        self.docs_for_index = [f"{c.title} {c.section} {c.text}" for c in self.chunks]
        self.bm25 = BM25Okapi([tokenize(d) for d in self.docs_for_index])
        self.mode = mode
        self.encoder = None
        self.embeddings = None
        if mode == "hybrid":
            from sentence_transformers import SentenceTransformer
            self.encoder = SentenceTransformer(config.EMBEDDING_MODEL)
            # le modèle e5 attend les préfixes « passage: » et « query: »
            self.embeddings = self.encoder.encode(
                [f"passage: {d}" for d in self.docs_for_index], normalize_embeddings=True
            )
        self.reranker = None
        if rerank:
            from sentence_transformers import CrossEncoder
            self.reranker = CrossEncoder(config.RERANKER_MODEL)

    def _bm25_ranking(self, query: str) -> list[int]:
        scores = self.bm25.get_scores(tokenize(query))
        return sorted(range(len(scores)), key=lambda i: -scores[i])

    def _dense_ranking(self, query: str) -> list[int]:
        q = self.encoder.encode([f"query: {query}"], normalize_embeddings=True)[0]
        scores = self.embeddings @ q
        return sorted(range(len(scores)), key=lambda i: -scores[i])

    def search(self, query: str, k: int = config.TOP_K) -> list[Chunk]:
        rankings = [self._bm25_ranking(query)]
        if self.mode == "hybrid":
            rankings.append(self._dense_ranking(query))
        # Reciprocal Rank Fusion (k=60)
        fused: dict[int, float] = {}
        for ranking in rankings:
            for rank, idx in enumerate(ranking):
                fused[idx] = fused.get(idx, 0.0) + 1.0 / (60 + rank + 1)
        candidates = sorted(fused, key=lambda i: -fused[i])
        if self.reranker is not None:
            pool = candidates[:20]
            scores = self.reranker.predict([(query, self.docs_for_index[i]) for i in pool])
            candidates = [i for _, i in sorted(zip(scores, pool), key=lambda x: -x[0])]
        return [self.chunks[i] for i in candidates[:k]]

    def search_doc_ids(self, query: str, k: int = config.TOP_K) -> list[str]:
        """Identifiants de fiches dédoublonnés, dans l'ordre (pour Recall@k et MRR)."""
        seen, out = set(), []
        for c in self.search(query, k=k * 3):
            if c.doc_id not in seen:
                seen.add(c.doc_id)
                out.append(c.doc_id)
        return out[:k]
