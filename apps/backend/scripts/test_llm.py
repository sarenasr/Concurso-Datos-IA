from app.agents.graph import llm_complete_small
from app.config import settings

print(f"LITELLM_MODEL: {settings.litellm_model}")
print(f"LITELLM_SMALL_MODEL: {settings.litellm_small_model}")
print(f"LITELLM_API_BASE: {settings.litellm_api_base}")
print(f"LITELLM_API_KEY: {settings.litellm_api_key[:20]}...")
print(f"OPENROUTER_API_KEY: {settings.openrouter_api_key[:20]}...")
print(f"LITELLM_API_KEY_RESOLVED: {settings.litellm_api_key_resolved[:20]}...")

try:
    r = llm_complete_small(
        [
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": "Say hello in Spanish."},
        ]
    )
    print(f"LLM response: {r[:100]}")
except Exception as e:
    print(f"LLM ERROR: {e}")
