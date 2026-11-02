import pytest


@pytest.fixture(autouse=True)
def file_env_isolato(request, tmp_path, monkeypatch):
    """I test automatici non leggono il .env reale del progetto; le prove reali sì."""
    if request.node.get_closest_marker("reale"):
        return
    monkeypatch.setattr("assistente.config.PERCORSO_ENV", tmp_path / "assente.env")
