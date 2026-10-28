"""Thin client for the local Ollama API: schema-constrained chat and embeddings."""

import json

import httpx

from . import config


class LLMError(RuntimeError):
    pass


class OllamaClient:
    def __init__(self, base_url=config.OLLAMA_URL, model=config.STORY_MODEL,
                 embed_model=config.EMBED_MODEL, timeout=600.0):
        self.base_url = base_url
        self.model = model
        self.embed_model = embed_model
        self._http = httpx.Client(base_url=base_url, timeout=timeout)

    def chat_json(self, system, user, schema, temperature):
        """Ask the story model for JSON that must match `schema` (Ollama enforces it with a grammar)."""
        body = {
            "model": self.model,
            "messages": [{"role": "system", "content": system},
                         {"role": "user", "content": user}],
            "format": schema,
            "stream": False,
            "think": False,
            "options": {"temperature": temperature, "num_ctx": config.NUM_CTX},
        }
        try:
            r = self._http.post("/api/chat", json=body)
            if r.status_code == 400 and "think" in r.text:
                # Models without a thinking mode reject the flag on some Ollama versions.
                body.pop("think")
                r = self._http.post("/api/chat", json=body)
            r.raise_for_status()
        except httpx.HTTPError as e:
            raise LLMError(f"Ollama chat failed: {e}") from e
        content = r.json()["message"]["content"]
        try:
            return json.loads(content)
        except json.JSONDecodeError as e:
            raise LLMError(f"Model returned invalid JSON: {content[:200]}") from e

    def embed(self, text):
        """Return an embedding vector, or None if the embedding model is unavailable."""
        try:
            r = self._http.post("/api/embed", json={"model": self.embed_model, "input": text})
            r.raise_for_status()
            return r.json()["embeddings"][0]
        except (httpx.HTTPError, KeyError, IndexError):
            return None

    def status(self):
        """Report whether Ollama is up and which of the configured models are pulled."""
        try:
            r = self._http.get("/api/tags", timeout=3.0)
            r.raise_for_status()
        except httpx.HTTPError:
            return {"ollama": False, "model": self.model, "model_ready": False, "embed_ready": False}
        names = {m["name"] for m in r.json().get("models", [])}

        def has(name):
            return name in names or f"{name}:latest" in names

        return {"ollama": True, "model": self.model,
                "model_ready": has(self.model), "embed_ready": has(self.embed_model)}
