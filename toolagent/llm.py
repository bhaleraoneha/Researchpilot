"""One place that builds the chat model. Works with any OpenAI-compatible provider."""
import os

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass


def get_llm(temperature: float = 0, model: str = None):
    from langchain_openai import ChatOpenAI
    key, model = os.getenv("LLM_API_KEY"), (model or os.getenv("LLM_MODEL"))
    if not key or not model:
        raise SystemExit("Set LLM_API_KEY and LLM_MODEL in .env (copy .env.example to .env).")
    return ChatOpenAI(model=model, api_key=key, base_url=os.getenv("LLM_BASE_URL") or None,
                      temperature=temperature, timeout=20, max_retries=1)
