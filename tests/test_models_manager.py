from tg_bot.models.models_manager import ModelsManager


def test_models_manager_loads_default_config():
    mm = ModelsManager()
    default = mm.get_default_model()
    assert default is not None
    assert "openrouter_name" in default


def test_models_manager_enabled_models_nonempty():
    mm = ModelsManager()
    enabled = mm.get_enabled_models()
    assert isinstance(enabled, list)
    assert len(enabled) >= 1

