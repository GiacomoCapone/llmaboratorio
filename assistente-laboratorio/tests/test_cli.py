from datetime import datetime, timezone

from langchain_core.messages import AIMessage

from assistente.cli import ciclo, esegui_turno, main
from assistente.grafo import MESSAGGIO_LIMITE, build_graph
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
    grafo = build_graph(llm, ADESSO, 5)
    esito1 = esegui_turno(grafo, [], "Prima domanda")
    esito2 = esegui_turno(grafo, esito1.cronologia, "Seconda domanda")
    visto = unisci_testo(llm.chiamate[1])
    assert "Prima domanda" in visto
    assert "Risposta uno" in visto
    assert esito2.testo == "Risposta due"
    assert esito2.interrotto is False


def test_turno_interrotto_non_entra_in_cronologia():
    llm = LlmFinto([richiesta_ora("Europe/Rome")], ripeti_ultima=True)
    grafo = build_graph(llm, ADESSO, 1)
    esito = esegui_turno(grafo, [], "Che ore sono?")
    assert esito.interrotto is True
    assert esito.testo == MESSAGGIO_LIMITE
    assert esito.cronologia == []

    llm2 = LlmFinto([AIMessage("Ok")])
    grafo2 = build_graph(llm2, ADESSO, 1)
    esito2 = esegui_turno(grafo2, esito.cronologia, "Ciao")
    assert esito2.testo == "Ok"
    assert tool_calls_orfani(llm2.chiamate[0]) == []
    assert "Che ore sono?" not in unisci_testo(llm2.chiamate[0])


class LlmErroreIniziale(LlmFinto):
    def invoke(self, messaggi):
        if not self.chiamate:
            self.chiamate.append(list(messaggi))
            raise RuntimeError("connessione")
        return super().invoke(messaggi)


def test_errore_del_modello_non_chiude_la_sessione():
    llm = LlmErroreIniziale([AIMessage("Risposta valida")])
    grafo = build_graph(llm, ADESSO, 5)
    uscite = []
    ciclo(grafo, leggi_da(["Prima", "Seconda", "esci"]), uscite.append)
    assert any(u.startswith("Errore:") for u in uscite)
    assert "Risposta valida" in uscite
    assert "Prima" not in unisci_testo(llm.chiamate[-1])


def test_ciclo_segnala_turno_interrotto():
    llm = LlmFinto([richiesta_ora("Europe/Rome")], ripeti_ultima=True)
    grafo = build_graph(llm, ADESSO, 1)
    uscite = []
    ciclo(grafo, leggi_da(["Ora?", "quit"]), uscite.append)
    assert any(MESSAGGIO_LIMITE in u for u in uscite)


def test_risposta_vuota_non_manda_in_crash():
    llm = LlmFinto([AIMessage("")])
    grafo = build_graph(llm, ADESSO, 5)
    uscite = []
    ciclo(grafo, leggi_da(["Ciao", "exit"]), uscite.append)
    assert uscite and all(u.strip() for u in uscite)


def test_input_vuoto_e_uscita():
    for finale in ["ESCI", EOFError(), KeyboardInterrupt()]:
        llm = LlmFinto([])
        grafo = build_graph(llm, ADESSO, 5)
        uscite = []
        ciclo(grafo, leggi_da(["", "   ", finale]), uscite.append)
        assert llm.chiamate == []


def test_main_configurazione_mancante(monkeypatch, capsys):
    monkeypatch.delenv("LMSTUDIO_MODEL", raising=False)
    monkeypatch.setenv("LMSTUDIO_BASE_URL", "http://localhost:1234/v1")
    assert main() == 1
    assert capsys.readouterr().err.strip() != ""
