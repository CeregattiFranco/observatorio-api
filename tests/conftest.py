import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

FIXTURE = Path(__file__).parent / "fixtures" / "acervo"


@pytest.fixture()
def client(monkeypatch):
    monkeypatch.setenv("ACERVO_ROOT", str(FIXTURE.resolve()))
    # reload modules with new root
    import app.config as config
    import app.acervo as acervo
    import app.main as main

    config.ACERVO_ROOT = FIXTURE.resolve()
    acervo.reset_acervo_for_tests(FIXTURE.resolve())
    with TestClient(main.app) as c:
        yield c
