"""Эмбеддеры. Основной — intfloat/multilingual-e5-small через fastembed (ONNX, локально, без ключей).
Запасной HashEmbedder — детерминированный мешок символьных триграмм: для тестов и для машин
без доступа к Hugging Face. Его качество ниже, в eval он не участвует."""

import hashlib
import math
import os
import re
from typing import Protocol

DIM = 384
E5_MODEL = "intfloat/multilingual-e5-small"


class Embedder(Protocol):
    name: str
    dim: int

    def embed_documents(self, texts: list[str]) -> list[list[float]]: ...

    def embed_query(self, text: str) -> list[float]: ...


class E5Embedder:
    """e5 обучена с префиксами: «passage: » для документов, «query: » для вопросов."""

    name = E5_MODEL
    dim = DIM

    def __init__(self, cache_dir: str | None = None) -> None:
        from fastembed import TextEmbedding
        from fastembed.common.model_description import ModelSource, PoolingType

        # В списке fastembed этой модели нет — регистрируем ONNX-файл из её репозитория на HF.
        if E5_MODEL not in {m["model"] for m in TextEmbedding.list_supported_models()}:
            TextEmbedding.add_custom_model(
                model=E5_MODEL,
                pooling=PoolingType.MEAN,
                normalization=True,
                sources=ModelSource(hf=E5_MODEL),
                dim=DIM,
                model_file="onnx/model.onnx",
            )
        self._model = TextEmbedding(E5_MODEL, cache_dir=cache_dir or os.environ.get("FASTEMBED_CACHE"))

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [v.tolist() for v in self._model.embed([f"passage: {t}" for t in texts], batch_size=32)]

    def embed_query(self, text: str) -> list[float]:
        return next(iter(self._model.embed([f"query: {text}"]))).tolist()


class HashEmbedder:
    name = "hash-trigram"
    dim = DIM

    def _vec(self, text: str) -> list[float]:
        v = [0.0] * self.dim
        for word in re.findall(r"\w+", text.lower()):
            w = f"#{word}#"
            for i in range(len(w) - 2):
                h = int.from_bytes(hashlib.blake2b(w[i : i + 3].encode(), digest_size=8).digest(), "big")
                v[h % self.dim] += 1.0 if (h >> 63) else -1.0
        n = math.sqrt(sum(x * x for x in v)) or 1.0
        return [x / n for x in v]

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [self._vec(t) for t in texts]

    def embed_query(self, text: str) -> list[float]:
        return self._vec(text)


def make_embedder(kind: str | None = None) -> Embedder:
    """kind: e5 | hash или имя модели из kb_meta (индекс и вопрос кодируются одной моделью)."""
    kind = kind or os.environ.get("RAG_EMBEDDER", "e5")
    return HashEmbedder() if kind in ("hash", HashEmbedder.name) else E5Embedder()
