import pytest


@pytest.mark.asyncio
async def test_new_user_starts_with_20_rubies(tmp_paths, reload_module):
    # reload config+db after env vars set by fixture
    reload_module("tg_bot.core.config")
    db_mod = reload_module("tg_bot.db.database")
    Database = db_mod.Database

    db = Database()
    await db.init_db()

    user = await db.get_or_create_user(user_id=1, username="u1", first_name="User")
    assert user["rubies"] == 20
    assert await db.get_user_rubies(1) == 20


@pytest.mark.asyncio
async def test_get_or_create_user_does_not_reset_existing_balance(tmp_paths, reload_module):
    reload_module("tg_bot.core.config")
    db_mod = reload_module("tg_bot.db.database")
    Database = db_mod.Database

    db = Database()
    await db.init_db()

    await db.get_or_create_user(user_id=1, username="u1", first_name="User")
    await db.add_rubies(1, 5)
    assert await db.get_user_rubies(1) == 25

    user2 = await db.get_or_create_user(user_id=1, username="u1", first_name="User")
    assert user2["rubies"] == 25


@pytest.mark.asyncio
async def test_transfer_rubies_updates_balances(tmp_paths, reload_module):
    reload_module("tg_bot.core.config")
    db_mod = reload_module("tg_bot.db.database")
    Database = db_mod.Database

    db = Database()
    await db.init_db()

    await db.get_or_create_user(user_id=1, username="from", first_name="From")
    await db.get_or_create_user(user_id=2, username="to", first_name="To")

    ok = await db.transfer_rubies(1, 2, 7)
    assert ok is True
    assert await db.get_user_rubies(1) == 13
    assert await db.get_user_rubies(2) == 27

