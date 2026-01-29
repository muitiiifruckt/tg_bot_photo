import os

import pytest
from openai import OpenAI


@pytest.mark.integration
def test_openrouter_models_list():
    """
    Real API smoke test: verifies OPENROUTER_API_KEY works and endpoint reachable.
    This should not spend money.
    """
    api_key = os.getenv("OPENROUTER_API_KEY")
    assert api_key, "Set OPENROUTER_API_KEY to run integration tests"

    client = OpenAI(base_url="https://openrouter.ai/api/v1", api_key=api_key)
    models = client.models.list()
    assert models is not None
    assert hasattr(models, "data")
    assert len(models.data) > 0


@pytest.mark.integration
@pytest.mark.expensive
@pytest.mark.asyncio
async def test_openrouter_generate_image_real():
    """
    Real API test through our client. MAY COST MONEY depending on your OpenRouter plan/model.
    Enable with RUN_EXPENSIVE=1.
    """
    api_key = os.getenv("OPENROUTER_API_KEY")
    assert api_key, "Set OPENROUTER_API_KEY to run integration tests"

    # Import inside test so env vars are already set for config.
    from tg_bot.clients.openrouter_client import OpenRouterClient
    from tg_bot.core.config import OPENROUTER_MODEL

    c = OpenRouterClient()
    result = await c.generate_image("A simple red circle on white background, minimal.", model=OPENROUTER_MODEL)
    assert result is not None
    assert isinstance(result, str)
    assert result.startswith("data:image") or result.startswith("http")

