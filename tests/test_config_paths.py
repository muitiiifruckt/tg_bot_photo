import os


def test_config_uses_env_paths(tmp_paths, reload_module):
    cfg = reload_module("tg_bot.core.config")
    assert cfg.DATABASE_PATH == os.environ["DATABASE_PATH"]
    assert cfg.FEEDBACK_PATH == os.environ["FEEDBACK_PATH"]


def test_config_defaults_are_under_data(monkeypatch, reload_module):
    monkeypatch.delenv("DATABASE_PATH", raising=False)
    monkeypatch.delenv("FEEDBACK_PATH", raising=False)
    cfg = reload_module("tg_bot.core.config")
    assert cfg.DATABASE_PATH.endswith("data/bot_database.db") or cfg.DATABASE_PATH.endswith("data\\bot_database.db")
    assert cfg.FEEDBACK_PATH.endswith("data/feedback.jsonl") or cfg.FEEDBACK_PATH.endswith("data\\feedback.jsonl")

