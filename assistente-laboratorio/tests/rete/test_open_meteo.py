import pytest

from assistente.strumenti.meteo import esegui_meteo
from assistente.strumenti.rete import scarica_json

pytestmark = pytest.mark.rete


def test_pordenone():
    risultato = esegui_meteo({"localita": "Pordenone"}, scarica_json)
    righe = risultato.splitlines()
    assert len(righe) == 7
    assert "Italia" in righe[0]
    assert "Errore:" not in risultato
    riga = next(r for r in righe if r.startswith("Temperatura:"))
    temperatura = float(riga.split(":", 1)[1].split()[0].replace(",", "."))
    assert -50 < temperatura < 60


def test_localita_inesistente():
    risultato = esegui_meteo({"localita": "Xqzwvtplk"}, scarica_json)
    assert risultato == "Errore: località non trovata: 'Xqzwvtplk'."
