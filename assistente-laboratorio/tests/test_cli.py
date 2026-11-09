from datetime import datetime, timezone

import pytest
from langchain_core.messages import AIMessage

from assistente.cli import ciclo, esegui_turno, main
from assistente.grafo import MESSAGGIO_LIMITE, build_graph
from assistente.mcp_client import ErroreArchivio
from assistente.strumenti import Strumento, crea_strumenti
from finti import LlmFinto, richiesta_ora

ADESSO = lambda: datetime(2026, 1, 15, 12, 0, tzinfo=timezone.utc)  # noqa: E731


def unisci_testo(messaggi):
    return " ".join(str(m.content) for m in messaggi)


def tool_calls_orfani(messaggi):
    """Tool call senza il relativo ToolMessage di risposta."""
    risposti = {m.tool_call_id for m in messaggi if m.type == "tool"}
    return [
        c["id"]
        for m in messaggi
        if m.type == "ai"
        for c in (m.tool_calls or [])
        if c["id"] not in risposti
    ]


def leggi_da(righe):
    it = iter(righe)

    def leggi():
        voce = next(it)
        if isinstance(voce, BaseException):
            raise voce
        return voce

    return leggi


def test_la_seconda_domanda_vede_la_prima():
    llm = LlmFinto([AIMessage("Risposta uno"), AIMessage("Risposta due")])
    grafo = build_graph(llm, crea_strumenti(ADESSO, "Europe/Rome"), 5)
    esito1 = esegui_turno(grafo, [], "Prima domanda")
    esito2 = esegui_turno(grafo, esito1.cronologia, "Seconda domanda")
    visto = unisci_testo(llm.chiamate[1])
    assert "Prima domanda" in visto
    assert "Risposta uno" in visto
    assert esito2.testo == "Risposta due"
    assert esito2.interrotto is False


def test_turno_interrotto_non_entra_in_cronologia():
    llm = LlmFinto([richiesta_ora("Europe/Rome")], ripeti_ultima=True)
    grafo = build_graph(llm, crea_strumenti(ADESSO, "Europe/Rome"), 1)
    esito = esegui_turno(grafo, [], "Che ore sono?")
    assert esito.interrotto is True
    assert esito.testo == MESSAGGIO_LIMITE
    assert esito.cronologia == []

    llm2 = LlmFinto([AIMessage("Ok")])
    grafo2 = build_graph(llm2, crea_strumenti(ADESSO, "Europe/Rome"), 1)
    esito2 = esegui_turno(grafo2, esito.cronologia, "Ciao")
    assert esito2.testo == "Ok"
    assert tool_calls_orfani(llm2.chiamate[0]) == []
    assert "Che ore sono?" not in unisci_testo(llm2.chiamate[0])


class LlmErroreIniziale(LlmFinto):
    def _rispondi(self, messaggi, con_strumenti):
        if not self.chiamate:
            self.chiamate.append(list(messaggi))
            raise RuntimeError("connessione")
        return super()._rispondi(messaggi, con_strumenti)


def test_errore_del_modello_non_chiude_la_sessione():
    llm = LlmErroreIniziale([AIMessage("Risposta valida")])
    grafo = build_graph(llm, crea_strumenti(ADESSO, "Europe/Rome"), 5)
    uscite = []
    ciclo(grafo, leggi_da(["Prima", "Seconda", "esci"]), uscite.append)
    assert any(u.startswith("Errore:") for u in uscite)
    assert "Risposta valida" in uscite
    assert "Prima" not in unisci_testo(llm.chiamate[-1])


def test_ciclo_segnala_turno_interrotto():
    llm = LlmFinto([richiesta_ora("Europe/Rome")], ripeti_ultima=True)
    grafo = build_graph(llm, crea_strumenti(ADESSO, "Europe/Rome"), 1)
    uscite = []
    ciclo(grafo, leggi_da(["Ora?", "quit"]), uscite.append)
    assert any(MESSAGGIO_LIMITE in u for u in uscite)


def test_risposta_vuota_non_manda_in_crash():
    llm = LlmFinto([AIMessage("")])
    grafo = build_graph(llm, crea_strumenti(ADESSO, "Europe/Rome"), 5)
    uscite = []
    ciclo(grafo, leggi_da(["Ciao", "exit"]), uscite.append)
    assert uscite and all(u.strip() for u in uscite)


def test_input_vuoto_e_uscita():
    for finale in ["ESCI", EOFError(), KeyboardInterrupt()]:
        llm = LlmFinto([])
        grafo = build_graph(llm, crea_strumenti(ADESSO, "Europe/Rome"), 5)
        uscite = []
        ciclo(grafo, leggi_da(["", "   ", finale]), uscite.append)
        assert llm.chiamate == []


class LlmCtrlCIniziale(LlmFinto):
    def _rispondi(self, messaggi, con_strumenti):
        if not self.chiamate:
            self.chiamate.append(list(messaggi))
            raise KeyboardInterrupt
        return super()._rispondi(messaggi, con_strumenti)


def test_ctrl_c_durante_il_turno_annulla_solo_il_turno():
    llm = LlmCtrlCIniziale([AIMessage("Risposta valida")])
    grafo = build_graph(llm, crea_strumenti(ADESSO, "Europe/Rome"), 5)
    uscite = []
    ciclo(grafo, leggi_da(["Prima", "Seconda", "esci"]), uscite.append)
    assert any("annullato" in u for u in uscite)
    assert "Risposta valida" in uscite
    assert "Prima" not in unisci_testo(llm.chiamate[-1])


class ArchivioFinto:
    def __init__(self, strumenti=(), errore=None):
        self._strumenti = list(strumenti)
        self._errore = errore
        self.uscito = False

    def __enter__(self):
        if self._errore:
            raise self._errore
        return self

    def __exit__(self, *eccezione):
        self.uscito = True
        return False

    def strumenti(self):
        return self._strumenti


def imposta_env(monkeypatch):
    monkeypatch.setenv("LMSTUDIO_BASE_URL", "http://localhost:1234/v1")
    monkeypatch.setenv("LMSTUDIO_MODEL", "modello-finto")


def test_main_archivio_non_avviato(monkeypatch, capsys):
    imposta_env(monkeypatch)
    finto = ArchivioFinto(errore=ErroreArchivio("archivio non avviato: prova"))
    monkeypatch.setattr("assistente.cli.ClientArchivio", lambda: finto)

    def non_chiamare(config):
        pytest.fail("verifica_modello chiamata prima dell'archivio")

    monkeypatch.setattr("assistente.cli.verifica_modello", non_chiamare)
    assert main() == 1
    assert "Errore: archivio non avviato: prova" in capsys.readouterr().err


def test_main_passa_gli_strumenti_dell_archivio(monkeypatch):
    imposta_env(monkeypatch)
    definizione = {"type": "function", "function": {"name": "prova_esterna", "parameters": {}}}
    finto = ArchivioFinto([Strumento(definizione, lambda args: "x")])
    monkeypatch.setattr("assistente.cli.ClientArchivio", lambda: finto)
    monkeypatch.setattr("assistente.cli.verifica_modello", lambda config: None)
    monkeypatch.setattr("assistente.cli.crea_llm", lambda config: None)
    nomi = []

    def grafo_finto(llm, strumenti, max_passaggi):
        nomi.extend(strumenti)
        raise KeyboardInterrupt

    monkeypatch.setattr("assistente.cli.build_graph", grafo_finto)
    assert main() == 130
    assert "prova_esterna" in nomi
    assert finto.uscito is True


def test_main_ctrl_c_all_avvio(monkeypatch, capsys):
    imposta_env(monkeypatch)
    monkeypatch.setattr("assistente.cli.ClientArchivio", lambda: ArchivioFinto())

    def interrompi(config):
        raise KeyboardInterrupt

    monkeypatch.setattr("assistente.cli.verifica_modello", interrompi)
    assert main() == 130
    assert capsys.readouterr().err.strip() != ""


def test_main_configurazione_mancante(monkeypatch, capsys):
    monkeypatch.delenv("LMSTUDIO_MODEL", raising=False)
    monkeypatch.setenv("LMSTUDIO_BASE_URL", "http://localhost:1234/v1")
    assert main() == 1
    assert capsys.readouterr().err.strip() != ""


def test_bom_di_powershell_ignorato():
    # PowerShell antepone \ufeff alla prima riga inviata con una pipe.
    llm = LlmFinto([AIMessage("Ciao!")])
    grafo = build_graph(llm, crea_strumenti(ADESSO, "Europe/Rome"), 5)
    uscite = []
    ciclo(grafo, leggi_da(["\ufeffciao", "\ufeffesci", "non letta"]), uscite.append)
    assert uscite == ["Ciao!"]
    assert unisci_testo(llm.chiamate[0]).strip() == "ciao"
