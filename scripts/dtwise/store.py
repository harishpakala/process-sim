"""Local Qdrant vector store using embeddings from a local Ollama server."""

from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any, Iterable

from ollama import Client
from qdrant_client import QdrantClient, models


class VectorStore:
    """Index and search DTwise ontology records in persistent local Qdrant."""

    def __init__(
        self,
        path: str | Path,
        model_name: str = "nomic-embed-text:latest",
        collection: str = "dtwise_ontology",
        ollama_host: str = "http://localhost:11434",
    ) -> None:
        self.client = QdrantClient(path=str(Path(path).resolve()))
        self.ollama = Client(host=ollama_host)
        self.model_name = model_name
        self.collection = collection

    def _embed(self, texts: list[str]) -> list[list[float]]:
        """Embed texts with Ollama, preserving input order."""
        if not texts:
            return []
        response = self.ollama.embed(model=self.model_name, input=texts)
        vectors = response.embeddings
        if len(vectors) != len(texts):
            raise RuntimeError("Ollama returned an unexpected number of embeddings")
        result = [list(map(float, vector)) for vector in vectors]
        if any(not vector for vector in result):
            raise RuntimeError("Ollama returned an empty embedding")
        return result

    def build(
        self,
        records: Iterable[dict[str, Any]],
        batch_size: int = 32,
        reset: bool = False,
    ) -> int:
        """Create or update the collection with ontology records.

        Use reset=True when changing embedding models. Existing points with
        the same record IDs are updated deterministically.
        """
        if batch_size < 1:
            raise ValueError("batch_size must be at least 1")

        records = list(records)
        if not records:
            raise ValueError("Schema contains no indexable records")
        for record in records:
            if not isinstance(record.get("id"), str) or not record["id"]:
                raise ValueError("Every record must have a nonempty string 'id'")
            if not isinstance(record.get("text"), str) or not record["text"].strip():
                raise ValueError(f"Record {record['id']!r} needs nonempty 'text'")

        first_batch = records[:batch_size]
        first_vectors = self._embed([record["text"] for record in first_batch])
        dimension = len(first_vectors[0])
        if any(len(vector) != dimension for vector in first_vectors):
            raise RuntimeError("Ollama returned embeddings with inconsistent dimensions")

        if reset and self.client.collection_exists(self.collection):
            self.client.delete_collection(self.collection)

        if self.client.collection_exists(self.collection):
            info = self.client.get_collection(self.collection)
            existing = info.config.params.vectors
            # This store uses one unnamed dense vector per point.
            existing_size = existing.size if isinstance(existing, models.VectorParams) else None
            if existing_size != dimension:
                raise RuntimeError(
                    f"Collection '{self.collection}' expects {existing_size} dimensions, "
                    f"but Ollama model '{self.model_name}' returned {dimension}. "
                    "Reindex with: python main.py index --reset"
                )
        else:
            self.client.create_collection(
                collection_name=self.collection,
                vectors_config=models.VectorParams(
                    size=dimension,
                    distance=models.Distance.COSINE,
                ),
            )

        for start in range(0, len(records), batch_size):
            batch = records[start : start + batch_size]
            vectors = (
                first_vectors
                if start == 0
                else self._embed([record["text"] for record in batch])
            )
            if any(len(vector) != dimension for vector in vectors):
                raise RuntimeError("Embedding dimension changed during indexing")
            points = [
                models.PointStruct(
                    id=str(uuid.uuid5(uuid.NAMESPACE_URL, record["id"])),
                    vector=vector,
                    payload=record,
                )
                for record, vector in zip(batch, vectors)
            ]
            self.client.upsert(collection_name=self.collection, points=points)

        return len(records)

    def search(
        self,
        query: str,
        k: int = 20,
        domain: str | None = None,
    ) -> list[dict[str, Any]]:
        """Return the top-k matching records with their cosine scores."""
        if k < 1:
            raise ValueError("k must be at least 1")
        if not self.client.collection_exists(self.collection):
            raise RuntimeError(
                f"Collection '{self.collection}' not found in local Qdrant storage. "
                "Run 'python main.py index --reset' first."
            )

        vector = self._embed([query])[0]
        info = self.client.get_collection(self.collection)
        config = info.config.params.vectors
        expected_size = config.size if isinstance(config, models.VectorParams) else None
        if expected_size != len(vector):
            raise RuntimeError(
                f"Query embedding has {len(vector)} dimensions, but collection "
                f"'{self.collection}' expects {expected_size}. "
                "Run 'python main.py index --reset' to rebuild it."
            )

        query_filter = (
            models.Filter(
                must=[
                    models.FieldCondition(
                        key="domain",
                        match=models.MatchValue(value=domain),
                    )
                ]
            )
            if domain
            else None
        )
        hits = self.client.query_points(
            collection_name=self.collection,
            query=vector,
            limit=k,
            query_filter=query_filter,
            with_payload=True,
        ).points
        return [{**(hit.payload or {}), "score": float(hit.score)} for hit in hits]
