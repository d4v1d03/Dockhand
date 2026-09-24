import fakeredis
import pytest

from dockhand.config import get_settings
from dockhand.db import engine as engine_mod
from dockhand.events import bus as bus_mod


@pytest.fixture
def db(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path}/test.db")
    get_settings.cache_clear()
    engine_mod.reset_engine()
    engine_mod.init_db()
    yield
    engine_mod.reset_engine()
    get_settings.cache_clear()


@pytest.fixture
def bus(db):
    b = bus_mod.EventBus(fakeredis.FakeRedis())
    bus_mod.set_bus(b)
    yield b
    bus_mod.set_bus(None)
