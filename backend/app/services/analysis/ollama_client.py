"""
app/services/analysis/ollama_client.py
Local Ollama LLM integration for contextual brand analysis.
Zero-budget, strictly local, graceful degradation when offline.
Never fakes AI results or makes external API calls.
"""
import logging
from typing import Optional, Dict, Any
import httpx

logger = logging.getLogger(__name__)

DEFAULT_OLLAMA_URL = "http://localhost:11434"
DEFAULT_MODEL = "llama3:latest"
CONNECT_TIMEOUT = 1.5  # seconds
READ_TIMEOUT = 10.0    # seconds


class LocalOllamaClient:
    """Client for local Ollama instance with fast timeout and zero-cost local execution."""

    def __init__(self, base_url: str = DEFAULT_OLLAMA_URL, model: str = DEFAULT_MODEL):
        self.base_url = base_url.rstrip("/")
        self.model = model

    def check_health(self) -> Dict[str, Any]:
        """Check if local Ollama daemon is running and which models are available."""
        try:
            with httpx.Client(timeout=CONNECT_TIMEOUT) as client:
                res = client.get(f"{self.base_url}/api/tags")
                if res.status_code == 200:
                    data = res.json()
                    models = [m.get("name") for m in data.get("models", [])]
                    has_model = any(self.model in m for m in models) if models else False
                    return {
                        "available": True,
                        "base_url": self.base_url,
                        "configured_model": self.model,
                        "model_ready": has_model,
                        "available_models": models,
                    }
        except Exception as exc:
            logger.debug("Local Ollama not reachable at %s: %s", self.base_url, exc)

        return {
            "available": False,
            "base_url": self.base_url,
            "configured_model": self.model,
            "model_ready": False,
            "available_models": [],
            "note": "Local Ollama daemon not detected. Deterministic engine running in standalone mode."
        }

    def generate_completion(self, prompt: str, system_prompt: Optional[str] = None) -> Optional[str]:
        """Run inference on the local model if available. Returns None if offline or error."""
        try:
            payload: Dict[str, Any] = {
                "model": self.model,
                "prompt": prompt,
                "stream": False,
                "options": {
                    "temperature": 0.0,
                    "num_predict": 512,
                }
            }
            if system_prompt:
                payload["system"] = system_prompt

            with httpx.Client(timeout=httpx.Timeout(connect=CONNECT_TIMEOUT, read=READ_TIMEOUT, write=5.0, pool=5.0)) as client:
                res = client.post(f"{self.base_url}/api/generate", json=payload)
                if res.status_code == 200:
                    return res.json().get("response", "").strip()
        except Exception as exc:
            logger.warning("Local Ollama contextual inference failed: %s", exc)

        return None

