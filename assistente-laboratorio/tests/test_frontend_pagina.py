"""Controlli statici sui file della pagina (il comportamento si prova a mano nel browser)."""

import re

import pytest

from frontend.app import STATICO

INDEX = (STATICO / "index.html").read_text(encoding="utf-8")
APP_JS = (STATICO / "app.js").read_text(encoding="utf-8")


def test_index_referenzia_i_file():
    assert 'href="stile.css"' in INDEX
    assert 'src="app.js"' in INDEX
    assert "<title>Assistente del laboratorio</title>" in INDEX
    assert '<meta charset="utf-8">' in INDEX
    assert "http://" not in INDEX
    assert "https://" not in INDEX


@pytest.mark.parametrize("vietato", ["innerHTML", "outerHTML", "insertAdjacentHTML", "document.write"])
def test_app_js_non_usa_innerhtml(vietato):
    assert vietato not in APP_JS


def test_app_js_usa_solo_api_relative():
    chiamate = re.findall(r"fetch\(\s*(\S+)", APP_JS)
    assert chiamate, "app.js deve chiamare fetch"
    for argomento in chiamate:
        assert re.match(r"""["'`]/api/""", argomento), argomento
    assert "http" not in APP_JS


@pytest.mark.parametrize(
    "testo",
    [
        "prompt sconosciuto '/",
        "Scrivere /prompt per l'elenco.",
        " non ha argomenti.",
        " richiede: ",
        "Il messaggio non è stato salvato.",
        "Il messaggio potrebbe non essere stato salvato: riapri la conversazione per controllare.",
        "L'assistente sta rispondendo… (",
        "Comandi non disponibili: ",
        "Eliminare la conversazione «",
        "back-end non disponibile:",
        "errore di rete: ",
    ],
)
def test_testi_della_spec(testo):
    assert testo in APP_JS
