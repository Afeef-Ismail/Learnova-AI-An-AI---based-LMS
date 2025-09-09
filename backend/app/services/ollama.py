import os
from typing import List, Dict, Any, AsyncGenerator
import httpx

OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://localhost:11434")
OLLAMA_TIMEOUT = int(os.getenv("OLLAMA_TIMEOUT", "600"))

class OllamaError(RuntimeError):
    pass

async def list_models() -> List[Dict[str, Any]]:
    try:
        async with httpx.AsyncClient(timeout=min(60, OLLAMA_TIMEOUT)) as client:
            r = await client.get(f"{OLLAMA_HOST}/api/tags")
            r.raise_for_status()
            return r.json().get("models", [])
    except Exception as e:
        raise OllamaError(f"Cannot reach Ollama at {OLLAMA_HOST}: {e}")

async def pull_model(name: str) -> Dict[str, Any]:
    try:
        async with httpx.AsyncClient(timeout=None) as client:
            r = await client.post(f"{OLLAMA_HOST}/api/pull", json={"name": name}, timeout=None)
            r.raise_for_status()
            return r.json()
    except Exception as e:
        raise OllamaError(f"Failed to pull model {name}: {e}")

async def generate(prompt: str, model: str, temperature: float = 0.2) -> str:
    """Call Ollama generate with richer error reporting (status code + body snippet)."""
    payload = {
        "model": model,
        "prompt": prompt,
        "stream": False,
        "options": {"temperature": temperature},
    }
    try:
        attempts = 2
        for i in range(attempts):
            async with httpx.AsyncClient(timeout=OLLAMA_TIMEOUT) as client:
                try:
                    r = await client.post(f"{OLLAMA_HOST}/api/generate", json=payload)
                except httpx.ReadTimeout:
                    if i < attempts - 1:
                        continue
                    raise
            try:
                r.raise_for_status()
            except httpx.HTTPStatusError as he:
                text_snip = (r.text or "")[:400]
                raise OllamaError(f"Generate HTTP {r.status_code}: {text_snip}") from he
            try:
                data = r.json()
            except Exception as je:
                raise OllamaError(f"Generate parse error (non-JSON response): {(r.text or '')[:400]}") from je
            return data.get("response", "")
    except OllamaError:
        raise
    except Exception as e:
        raise OllamaError(f"Generate failed: {type(e).__name__}: {e}") from e

async def stream_generate(prompt: str, model: str, temperature: float = 0.2) -> AsyncGenerator[str, None]:
    """Stream tokens from Ollama generate endpoint.
    Yields incremental text chunks from the "response" field of each streamed JSON line.
    """
    payload = {
        "model": model,
        "prompt": prompt,
        "stream": True,
        "options": {"temperature": temperature},
    }
    try:
        async with httpx.AsyncClient(timeout=OLLAMA_TIMEOUT) as client:
            async with client.stream("POST", f"{OLLAMA_HOST}/api/generate", json=payload) as r:
                try:
                    r.raise_for_status()
                except httpx.HTTPStatusError as he:
                    text_snip = (await r.aread())[:400].decode(errors="ignore") if not r.is_closed else ""
                    raise OllamaError(f"Generate HTTP {r.status_code}: {text_snip}") from he
                async for line in r.aiter_lines():
                    if not line:
                        continue
                    # Ollama streams JSON per line
                    try:
                        data = httpx.Response(200, text=line).json()
                    except Exception:
                        # Best-effort parse: ignore malformed lines
                        continue
                    if isinstance(data, dict):
                        if data.get("error"):
                            raise OllamaError(str(data.get("error")))
                        chunk = data.get("response")
                        if isinstance(chunk, str) and chunk:
                            yield chunk
                        if data.get("done") is True:
                            break
    except OllamaError:
        raise
    except Exception as e:
        raise OllamaError(f"Stream failed: {type(e).__name__}: {e}") from e

async def embed(input_texts: List[str], model: str) -> List[List[float]]:
    """Return embeddings for each text with improved error diagnostics."""
    try:
        out: List[List[float]] = []
        async with httpx.AsyncClient(timeout=OLLAMA_TIMEOUT) as client:
            for text in input_texts:
                try:
                    resp = await client.post(
                        f"{OLLAMA_HOST}/api/embeddings",
                        json={"model": model, "input": text},
                    )
                except httpx.ReadTimeout:
                    resp = await client.post(
                        f"{OLLAMA_HOST}/api/embeddings",
                        json={"model": model, "input": text},
                    )
                try:
                    resp.raise_for_status()
                except httpx.HTTPStatusError as he:
                    snippet = (resp.text or "")[:400]
                    raise OllamaError(f"Embeddings HTTP {resp.status_code}: {snippet}") from he
                try:
                    data = resp.json()
                except Exception as je:
                    raise OllamaError(f"Embeddings parse error: {(resp.text or '')[:200]}") from je
                if "embedding" in data and isinstance(data["embedding"], list):
                    out.append(data["embedding"])  # type: ignore
                elif "embeddings" in data and isinstance(data["embeddings"], list) and data["embeddings"]:
                    out.append(data["embeddings"][0])  # type: ignore
                else:
                    raise OllamaError(f"Unexpected embeddings response keys: {list(data.keys())[:5]}")
        return out
    except OllamaError:
        raise
    except Exception as e:
        raise OllamaError(f"Embeddings failed: {type(e).__name__}: {e}") from e
