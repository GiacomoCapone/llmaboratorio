import logging
from datetime import datetime, timezone

import pytest
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from assistente.cli import MESSAGGIO_TURNO_ANNULLATO, ciclo, esegui_turno, main
from assistente.config import carica_config
from assistente.grafo import MESSAGGIO_LIMITE, MESSAGGIO_RIFIUTO, build_graph
from assistente import mcp_client
from assistente.mcp_client import ErroreArchivio, PromptArchivio
from assistente.modello import ErroreModello
from assistente.riassunto import PREFISSO_RIASSUNTO
from assistente.strumenti import Strumento, crea_strumenti
from finti import LlmFinto, RevisoreFinto, RiassuntoreFinto, RouterFinto, richiesta_ora

ADESSO = lambda: datetime(2026, 1, 15, 12, 0, tzinfo=timezone.utc)  # noqa: E731


def crea_grafo(llm, max_passaggi, router=None, revisore=None):
    """Grafo con gli strumenti veri, router e revisore simulati (in ambito e approvato, se
    non indicati)."""
    return build_graph(
        llm,
        crea_strumenti(ADESSO, "Europe/Rome"),
        max_passaggi,
        router or RouterFinto("conversazione"),
        revisore or RevisoreFinto([True]),
        2,
        RiassuntoreFinto(),
        100000,
    )


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
    grafo = crea_grafo(llm, 5)
    esito1 = esegui_turno(grafo, [], "Prima domanda")
    esito2 = esegui_turno(grafo, esito1.cronologia, "Seconda domanda")
    visto = unisci_testo(llm.chiamate[1])
    assert "Prima domanda" in visto
    assert "Risposta uno" in visto
    assert esito2.testo == "Risposta due"
    assert esito2.interrotto is False


def test_turno_interrotto_non_entra_in_cronologia():
    llm = LlmFinto([richiesta_ora("Europe/Rome")], ripeti_ultima=True)
    grafo = crea_grafo(llm, 1)
    esito = esegui_turno(grafo, [], "Che ore sono?")
    assert esito.interrotto is True
    assert esito.testo == MESSAGGIO_LIMITE
    assert esito.cronologia == []

    llm2 = LlmFinto([AIMessage("Ok")])
    grafo2 = crea_grafo(llm2, 1)
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
    grafo = crea_grafo(llm, 5)
    uscite = []
    ciclo(grafo, leggi_da(["Prima", "Seconda", "esci"]), uscite.append)
    assert any(u.startswith("Errore:") for u in uscite)
    assert "Risposta valida" in uscite
    assert "Prima" not in unisci_testo(llm.chiamate[-1])


def test_ciclo_segnala_turno_interrotto():
    llm = LlmFinto([richiesta_ora("Europe/Rome")], ripeti_ultima=True)
    grafo = crea_grafo(llm, 1)
    uscite = []
    ciclo(grafo, leggi_da(["Ora?", "quit"]), uscite.append)
    assert any(MESSAGGIO_LIMITE in u for u in uscite)


def test_risposta_vuota_non_manda_in_crash():
    llm = LlmFinto([AIMessage("")])
    grafo = crea_grafo(llm, 5)
    uscite = []
    ciclo(grafo, leggi_da(["Ciao", "exit"]), uscite.append)
    assert uscite and all(u.strip() for u in uscite)


def test_input_vuoto_e_uscita():
    for finale in ["ESCI", EOFError(), KeyboardInterrupt()]:
        llm = LlmFinto([])
        grafo = crea_grafo(llm, 5)
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
    grafo = crea_grafo(llm, 5)
    uscite = []
    ciclo(grafo, leggi_da(["Prima", "Seconda", "esci"]), uscite.append)
    assert any("annullato" in u for u in uscite)
    assert "Risposta valida" in uscite
    assert "Prima" not in unisci_testo(llm.chiamate[-1])


RESOURCE_DI_PROVA = "Categorie:\n- attrezzi (2 articoli)\n- sicurezza (1 articolo)"


class ArchivioFinto:
    def __init__(
        self, strumenti=(), errore=None, contesto=RESOURCE_DI_PROVA, errore_lettura=None
    ):
        self._strumenti = list(strumenti)
        self._errore = errore
        self._contesto = contesto
        self._errore_lettura = errore_lettura
        self.letti = []
        self.uscito = False

    def leggi_risorsa(self, uri):
        self.letti.append(uri)
        if self._errore_lettura:
            raise self._errore_lettura
        return self._contesto

    def __enter__(self):
        if self._errore:
            raise self._errore
        return self

    def __exit__(self, *eccezione):
        self.uscito = True
        return False

    def strumenti(self):
        return self._strumenti

    def prompt_disponibili(self):
        return []


def imposta_env(monkeypatch):
    monkeypatch.setenv("LMSTUDIO_BASE_URL", "http://localhost:1234/v1")
    monkeypatch.setenv("LMSTUDIO_MODEL", "modello-finto")


def test_main_archivio_non_avviato(monkeypatch, capsys):
    imposta_env(monkeypatch)
    finto = ArchivioFinto(errore=ErroreArchivio("archivio non avviato: prova"))
    monkeypatch.setattr("assistente.avvio.ClientArchivio", lambda **kwargs: finto)

    def non_chiamare(config):
        pytest.fail("verifica_modello chiamata prima dell'archivio")

    monkeypatch.setattr("assistente.avvio.verifica_modello", non_chiamare)
    assert main() == 1
    assert "Errore: archivio non avviato: prova" in capsys.readouterr().err


def test_main_passa_gli_strumenti_dell_archivio(monkeypatch):
    imposta_env(monkeypatch)
    definizione = {"type": "function", "function": {"name": "prova_esterna", "parameters": {}}}
    finto = ArchivioFinto([Strumento(definizione, lambda args: "x")])
    monkeypatch.setattr("assistente.avvio.ClientArchivio", lambda **kwargs: finto)
    monkeypatch.setattr("assistente.avvio.verifica_modello", lambda config: None)
    monkeypatch.setattr("assistente.avvio.crea_llm", lambda config: None)
    monkeypatch.setattr("assistente.avvio.crea_router", lambda llm, ambito: None)
    monkeypatch.setattr("assistente.avvio.crea_revisore", lambda llm: None)
    monkeypatch.setattr("assistente.avvio.crea_riassuntore", lambda llm: None)
    nomi = []

    def grafo_finto(
        llm,
        strumenti,
        max_passaggi,
        router,
        revisore,
        max_revisioni,
        riassuntore,
        soglia_riassunto,
    ):
        nomi.extend(strumenti)
        raise KeyboardInterrupt

    monkeypatch.setattr("assistente.avvio.build_graph", grafo_finto)
    assert main() == 130
    assert "prova_esterna" in nomi
    assert finto.uscito is True


def test_main_passa_note_db_e_fuso(monkeypatch, tmp_path):
    imposta_env(monkeypatch)
    percorso = tmp_path / "note.db"
    monkeypatch.setenv("NOTE_DB", str(percorso))
    monkeypatch.setenv("FUSO_PREDEFINITO", "UTC")
    ricevuti = {}

    def crea_finto(**kwargs):
        ricevuti.update(kwargs)
        return ArchivioFinto()

    monkeypatch.setattr("assistente.avvio.ClientArchivio", crea_finto)

    def interrompi(config):
        raise KeyboardInterrupt

    monkeypatch.setattr("assistente.avvio.verifica_modello", interrompi)
    assert main() == 130
    assert ricevuti["ambiente"] == {"NOTE_DB": str(percorso), "FUSO_PREDEFINITO": "UTC"}


def test_main_ctrl_c_all_avvio(monkeypatch, capsys):
    imposta_env(monkeypatch)
    monkeypatch.setattr("assistente.avvio.ClientArchivio", lambda **kwargs: ArchivioFinto())

    def interrompi(config):
        raise KeyboardInterrupt

    monkeypatch.setattr("assistente.avvio.verifica_modello", interrompi)
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
    grafo = crea_grafo(llm, 5)
    uscite = []
    ciclo(grafo, leggi_da(["\ufeffciao", "\ufeffesci", "non letta"]), uscite.append)
    assert uscite == ["Ciao!"]
    assert unisci_testo(llm.chiamate[0]).strip() == "ciao"


def test_turno_rifiutato_resta_in_cronologia():
    llm = LlmFinto([AIMessage("Ciao!")])
    router = RouterFinto(["fuori_ambito", "conversazione"], "poesia")
    grafo = crea_grafo(llm, 5, router)
    primo = esegui_turno(grafo, [], "Scrivi una poesia")
    assert primo.interrotto is False
    assert [m.type for m in primo.cronologia] == ["human", "ai"]
    assert primo.cronologia[-1].content == MESSAGGIO_RIFIUTO.format(motivo="poesia")
    secondo = esegui_turno(grafo, primo.cronologia, "Ciao")
    assert secondo.testo == "Ciao!"
    assert MESSAGGIO_RIFIUTO.format(motivo="poesia") in unisci_testo(llm.chiamate[0])


def test_main_passa_il_router(monkeypatch):
    imposta_env(monkeypatch)
    monkeypatch.setattr("assistente.avvio.ClientArchivio", lambda **kwargs: ArchivioFinto())
    monkeypatch.setattr("assistente.avvio.verifica_modello", lambda config: None)
    llm_finto = object()
    monkeypatch.setattr("assistente.avvio.crea_llm", lambda config: llm_finto)
    router_finto = object()
    ricevuti = {}

    def crea_router_finto(llm, ambito):
        ricevuti.update(llm=llm, ambito=ambito)
        return router_finto

    def grafo_finto(
        llm,
        strumenti,
        max_passaggi,
        router,
        revisore,
        max_revisioni,
        riassuntore,
        soglia_riassunto,
    ):
        ricevuti["router"] = router
        raise KeyboardInterrupt

    monkeypatch.setattr("assistente.avvio.crea_router", crea_router_finto)
    monkeypatch.setattr("assistente.avvio.crea_revisore", lambda llm: None)
    monkeypatch.setattr("assistente.avvio.crea_riassuntore", lambda llm: None)
    monkeypatch.setattr("assistente.avvio.build_graph", grafo_finto)
    assert main() == 130
    assert ricevuti["llm"] is llm_finto
    assert ricevuti["ambito"] == carica_config().ambito
    assert ricevuti["router"] is router_finto


class GrafoCheRegistra:
    """Grafo finto: registra lo stato iniziale e risponde con una risposta fissa."""

    def __init__(self):
        self.stati = []

    def invoke(self, stato):
        self.stati.append(stato)
        return {**stato, "messaggi": stato["messaggi"] + [AIMessage("ok")]}


def test_esegui_turno_azzera_la_revisione():
    grafo = GrafoCheRegistra()
    esegui_turno(grafo, [], "ciao")
    stato = grafo.stati[0]
    assert stato["revisioni"] == 0
    assert stato["scartati"] == []
    assert stato["esito_revisione"] == ""


def test_turno_dopo_revisione_cronologia_pulita():
    llm = LlmFinto([AIMessage("bozza"), AIMessage("finale"), AIMessage("secondo")])
    revisore = RevisoreFinto([False, True, True])
    grafo = crea_grafo(llm, 5, revisore=revisore)
    primo = esegui_turno(grafo, [], "domanda uno")
    assert [m.content for m in primo.cronologia] == ["domanda uno", "finale"]
    esegui_turno(grafo, primo.cronologia, "domanda due")
    for messaggi in [llm.chiamate[-1], revisore.chiamate[-1]]:
        testi = unisci_testo(messaggi)
        assert "bozza" not in testi
        assert "Indicazione del revisore" not in testi


def test_main_passa_il_revisore(monkeypatch):
    imposta_env(monkeypatch)
    monkeypatch.setattr("assistente.avvio.ClientArchivio", lambda **kwargs: ArchivioFinto())
    monkeypatch.setattr("assistente.avvio.verifica_modello", lambda config: None)
    llm_finto = object()
    monkeypatch.setattr("assistente.avvio.crea_llm", lambda config: llm_finto)
    monkeypatch.setattr("assistente.avvio.crea_router", lambda llm, ambito: None)
    revisore_finto = object()
    ricevuti = {}

    def crea_revisore_finto(llm):
        ricevuti["llm"] = llm
        return revisore_finto

    def grafo_finto(
        llm,
        strumenti,
        max_passaggi,
        router,
        revisore,
        max_revisioni,
        riassuntore,
        soglia_riassunto,
    ):
        ricevuti.update(revisore=revisore, max_revisioni=max_revisioni)
        raise KeyboardInterrupt

    monkeypatch.setattr("assistente.avvio.crea_revisore", crea_revisore_finto)
    monkeypatch.setattr("assistente.avvio.crea_riassuntore", lambda llm: None)
    monkeypatch.setattr("assistente.avvio.build_graph", grafo_finto)
    assert main() == 130
    assert ricevuti["llm"] is llm_finto
    assert ricevuti["revisore"] is revisore_finto
    assert ricevuti["max_revisioni"] == carica_config().max_revisioni


def test_main_passa_il_riassuntore(monkeypatch):
    imposta_env(monkeypatch)
    monkeypatch.setattr("assistente.avvio.ClientArchivio", lambda **kwargs: ArchivioFinto())
    monkeypatch.setattr("assistente.avvio.verifica_modello", lambda config: None)
    llm_finto = object()
    monkeypatch.setattr("assistente.avvio.crea_llm", lambda config: llm_finto)
    monkeypatch.setattr("assistente.avvio.crea_router", lambda llm, ambito: None)
    monkeypatch.setattr("assistente.avvio.crea_revisore", lambda llm: None)
    riassuntore_finto = object()
    ricevuti = {}

    def crea_riassuntore_finto(llm):
        ricevuti["llm"] = llm
        return riassuntore_finto

    def grafo_finto(
        llm,
        strumenti,
        max_passaggi,
        router,
        revisore,
        max_revisioni,
        riassuntore,
        soglia_riassunto,
    ):
        ricevuti.update(riassuntore=riassuntore, soglia_riassunto=soglia_riassunto)
        raise KeyboardInterrupt

    monkeypatch.setattr("assistente.avvio.crea_riassuntore", crea_riassuntore_finto)
    monkeypatch.setattr("assistente.avvio.build_graph", grafo_finto)
    assert main() == 130
    assert ricevuti["llm"] is llm_finto
    assert ricevuti["riassuntore"] is riassuntore_finto
    assert ricevuti["soglia_riassunto"] == carica_config().soglia_riassunto


def test_cronologia_compatta_al_turno_dopo():
    llm = LlmFinto([AIMessage(f"R{i}") for i in range(1, 6)])
    grafo = build_graph(
        llm,
        crea_strumenti(ADESSO, "Europe/Rome"),
        5,
        RouterFinto("conversazione"),
        RevisoreFinto([True]),
        2,
        RiassuntoreFinto(),
        1,
    )
    cronologia = []
    for i in range(1, 5):
        cronologia = esegui_turno(grafo, cronologia, f"D{i}").cronologia
    assert isinstance(cronologia[0], SystemMessage)
    assert cronologia[0].content.startswith(PREFISSO_RIASSUNTO)
    esegui_turno(grafo, cronologia, "D5")
    assert llm.chiamate[-1][0].content == PREFISSO_RIASSUNTO + "riassunto di prova"


def prepara_main(monkeypatch, finto):
    imposta_env(monkeypatch)
    monkeypatch.setattr("assistente.avvio.ClientArchivio", lambda **kwargs: finto)
    monkeypatch.setattr("assistente.avvio.verifica_modello", lambda config: None)
    monkeypatch.setattr("assistente.avvio.crea_llm", lambda config: None)
    monkeypatch.setattr("assistente.avvio.crea_router", lambda llm, ambito: None)
    monkeypatch.setattr("assistente.avvio.crea_revisore", lambda llm: None)
    monkeypatch.setattr("assistente.avvio.crea_riassuntore", lambda llm: None)


def cerca_finto():
    definizione = {
        "type": "function",
        "function": {
            "name": "cerca_inventario",
            "parameters": {
                "type": "object",
                "properties": {"categoria": {"type": "string", "description": "Nome esatto."}},
            },
        },
    }
    return Strumento(definizione, lambda args: "x")


def descrizione_ricevuta(monkeypatch):
    """Sostituisce build_graph: registra la descrizione di `categoria` di cerca_inventario."""
    ricevuti = {}

    def grafo_finto(llm, strumenti, *args):
        definizione = strumenti["cerca_inventario"].definizione
        ricevuti["descrizione"] = definizione["function"]["parameters"]["properties"]["categoria"][
            "description"
        ]
        raise KeyboardInterrupt

    monkeypatch.setattr("assistente.avvio.build_graph", grafo_finto)
    return ricevuti


def test_main_arricchisce_cerca_inventario(monkeypatch, caplog):
    finto = ArchivioFinto([cerca_finto()])
    prepara_main(monkeypatch, finto)
    ricevuti = descrizione_ricevuta(monkeypatch)
    with caplog.at_level(logging.INFO, logger="assistente.avvio"):
        assert main() == 130
    assert ricevuti["descrizione"] == "Nome esatto. Categorie esistenti: attrezzi, sicurezza."
    assert finto.letti == [mcp_client.URI_CATEGORIE]
    assert "contesto: letta la resource archivio://inventario/categorie (2 categorie)" in caplog.text


def test_main_contesto_non_disponibile(monkeypatch, caplog):
    guasto = ErroreArchivio("l'archivio non ha risposto entro 10 secondi")
    prepara_main(monkeypatch, ArchivioFinto([cerca_finto()], errore_lettura=guasto))
    ricevuti = descrizione_ricevuta(monkeypatch)
    with caplog.at_level(logging.INFO, logger="assistente.avvio"):
        assert main() == 130
    assert ricevuti["descrizione"] == "Nome esatto."
    avvisi = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert [r.getMessage() for r in avvisi] == [
        "contesto non disponibile: l'archivio non ha risposto entro 10 secondi"
    ]


def test_main_senza_contesto(monkeypatch, capsys):
    guasto = ErroreArchivio("lettura fallita")
    prepara_main(monkeypatch, ArchivioFinto(errore_lettura=guasto))
    monkeypatch.setattr("assistente.avvio.crea_llm", lambda config: LlmFinto([AIMessage("Ciao.")]))
    monkeypatch.setattr("assistente.avvio.crea_router", lambda llm, ambito: RouterFinto("conversazione"))
    monkeypatch.setattr("assistente.avvio.crea_revisore", lambda llm: RevisoreFinto([True]))
    monkeypatch.setattr("assistente.avvio.crea_riassuntore", lambda llm: RiassuntoreFinto())
    righe = iter(["ciao", "esci"])
    monkeypatch.setattr("builtins.input", lambda prompt="": next(righe))
    assert main() == 0
    assert "Ciao." in capsys.readouterr().out


class PromptFinti:
    """Archivio finto per i prompt: registra le chiamate e restituisce un testo o solleva `errore`."""

    def __init__(self, prompt, errore=None):
        self._prompt = list(prompt)
        self._errore = errore
        self.chiamate = []

    def prompt_disponibili(self):
        return self._prompt

    def testo_prompt(self, nome, argomenti):
        self.chiamate.append((nome, argomenti))
        if self._errore:
            raise self._errore
        return f"testo di {nome} {argomenti}"


SCHEDA = PromptArchivio("scheda_articolo", "Scheda.", ["codice"])
NOTA = PromptArchivio("nota", "Nota.", ["codice", "testo"])
SALUTO = PromptArchivio("saluto", "Saluto.", [])


def esegui_ciclo(righe, prompt, grafo=None):
    grafo = grafo or GrafoCheRegistra()
    uscite = []
    ciclo(grafo, leggi_da([*righe, "esci"]), uscite.append, prompt=prompt)
    return grafo, uscite


def domande(grafo):
    """Testo dell'ultimo HumanMessage di ogni turno eseguito dal grafo."""
    return [stato["messaggi"][-1].content for stato in grafo.stati]


def test_prompt_elenco():
    grafo, uscite = esegui_ciclo(["/prompt"], PromptFinti([SCHEDA, NOTA, SALUTO]))
    assert "\n".join(uscite).splitlines() == [
        "/scheda_articolo <codice> — Scheda.",
        "/nota <codice> <testo> — Nota.",
        "/saluto — Saluto.",
    ]
    assert grafo.stati == []


def test_prompt_elenco_vuoto():
    grafo, uscite = esegui_ciclo(["/prompt"], PromptFinti([]))
    assert uscite == ["Nessun prompt disponibile."]
    assert grafo.stati == []


def test_prompt_avvia_il_turno(caplog):
    prompt = PromptFinti([SCHEDA])
    with caplog.at_level(logging.INFO, logger="assistente.cli"):
        grafo, uscite = esegui_ciclo(["/scheda_articolo mis-001"], prompt)
    testo = "testo di scheda_articolo {'codice': 'mis-001'}"
    assert prompt.chiamate == [("scheda_articolo", {"codice": "mis-001"})]
    assert uscite == [f"(prompt) {testo}", "ok"]
    assert domande(grafo) == [testo]
    assert isinstance(grafo.stati[0]["messaggi"][-1], HumanMessage)
    assert "prompt: /scheda_articolo {'codice': 'mis-001'}" in caplog.text


def test_prompt_resta_in_cronologia():
    grafo, _ = esegui_ciclo(["/scheda_articolo MIS-001", "ciao"], PromptFinti([SCHEDA]))
    secondo = [m.content for m in grafo.stati[1]["messaggi"]]
    assert secondo == ["testo di scheda_articolo {'codice': 'MIS-001'}", "ok", "ciao"]


def test_prompt_ultimo_argomento_prende_il_resto():
    prompt = PromptFinti([NOTA])
    esegui_ciclo(["/nota MIS-001 display  rotto da ieri"], prompt)
    assert prompt.chiamate == [("nota", {"codice": "MIS-001", "testo": "display  rotto da ieri"})]


@pytest.mark.parametrize(
    "riga, atteso",
    [
        ("/scheda_articolo", "Errore: /scheda_articolo richiede: <codice>."),
        ("/scheda_articolo   ", "Errore: /scheda_articolo richiede: <codice>."),
        ("/nota MIS-001", "Errore: /nota richiede: <codice> <testo>."),
    ],
)
def test_prompt_argomento_mancante(riga, atteso):
    prompt = PromptFinti([SCHEDA, NOTA])
    grafo, uscite = esegui_ciclo([riga], prompt)
    assert uscite == [atteso]
    assert prompt.chiamate == [] and grafo.stati == []


def test_prompt_senza_argomenti_con_testo():
    prompt = PromptFinti([SALUTO])
    grafo, uscite = esegui_ciclo(["/saluto x", "/saluto"], prompt)
    assert uscite[0] == "Errore: /saluto non ha argomenti."
    assert prompt.chiamate == [("saluto", {})]
    assert len(grafo.stati) == 1


@pytest.mark.parametrize("riga, nome", [("/xyz 1", "/xyz"), ("/SCHEDA_ARTICOLO MIS-001", "/SCHEDA_ARTICOLO"), ("/", "/")])
def test_prompt_sconosciuto(riga, nome):
    prompt = PromptFinti([SCHEDA])
    grafo, uscite = esegui_ciclo([riga], prompt)
    assert uscite == [f"Errore: prompt sconosciuto '{nome}'. Scrivere /prompt per l'elenco."]
    assert prompt.chiamate == [] and grafo.stati == []


def test_prompt_errore_del_server():
    prompt = PromptFinti([SCHEDA], errore=ErroreArchivio("nessun articolo con codice 'XYZ'."))
    grafo, uscite = esegui_ciclo(["/scheda_articolo XYZ", "ciao"], prompt)
    assert uscite[0] == "Errore: nessun articolo con codice 'XYZ'."
    assert domande(grafo) == ["ciao"]
    assert len(grafo.stati[0]["messaggi"]) == 1  # nessuna traccia del prompt in cronologia


class GrafoCheSiInterrompe(GrafoCheRegistra):
    """Al primo turno simula Ctrl-C; poi risponde come GrafoCheRegistra."""

    def invoke(self, stato):
        if not self.stati:
            self.stati.append(stato)
            raise KeyboardInterrupt
        return super().invoke(stato)


def test_prompt_ctrl_c_annulla_il_turno():
    grafo, uscite = esegui_ciclo(
        ["/scheda_articolo MIS-001", "ciao"], PromptFinti([SCHEDA]), GrafoCheSiInterrompe()
    )
    assert MESSAGGIO_TURNO_ANNULLATO in uscite
    assert [m.content for m in grafo.stati[1]["messaggi"]] == ["ciao"]


def test_senza_prompt_la_barra_va_al_modello():
    grafo = GrafoCheRegistra()
    ciclo(grafo, leggi_da(["/prompt", "esci"]), lambda testo: None)
    assert domande(grafo) == ["/prompt"]


def test_main_passa_l_archivio_a_ciclo(monkeypatch, capsys):
    prepara_main(monkeypatch, ArchivioFinto())
    monkeypatch.setattr("assistente.avvio.crea_llm", lambda config: LlmFinto([AIMessage("Ciao.")]))
    monkeypatch.setattr("assistente.avvio.crea_router", lambda llm, ambito: RouterFinto("conversazione"))
    monkeypatch.setattr("assistente.avvio.crea_revisore", lambda llm: RevisoreFinto([True]))
    monkeypatch.setattr("assistente.avvio.crea_riassuntore", lambda llm: RiassuntoreFinto())
    righe = iter(["/prompt", "esci"])
    monkeypatch.setattr("builtins.input", lambda prompt="": next(righe))
    assert main() == 0
    uscita = capsys.readouterr().out
    assert (
        "Assistente del laboratorio. Scrivere 'esci' per terminare, '/prompt' per i prompt dell'archivio."
        in uscita
    )
    assert "Nessun prompt disponibile." in uscita


def test_prompt_ctrl_c_durante_la_richiesta():
    prompt = PromptFinti([SCHEDA], errore=KeyboardInterrupt())
    grafo, uscite = esegui_ciclo(["/scheda_articolo MIS-001", "ciao"], prompt)
    assert uscite[0] == MESSAGGIO_TURNO_ANNULLATO
    assert domande(grafo) == ["ciao"]


def test_main_http_chiama_servi(monkeypatch):
    imposta_env(monkeypatch)
    chiamate = []
    monkeypatch.setattr("assistente.servizio.servi", lambda config: chiamate.append(config))
    assert main(["--http"]) == 0
    assert len(chiamate) == 1
    assert chiamate[0].model == "modello-finto"


def test_main_argomento_sconosciuto(monkeypatch, capsys):
    imposta_env(monkeypatch)
    monkeypatch.setattr(
        "assistente.servizio.servi", lambda config: pytest.fail("servi non va chiamata")
    )
    assert main(["--boh"]) == 2
    assert "Uso: python avvia.py [--http | --backend | --frontend]" in capsys.readouterr().err


def test_main_http_errore_di_avvio(monkeypatch, capsys):
    imposta_env(monkeypatch)

    def servi_guasta(config):
        raise ErroreModello("x")

    monkeypatch.setattr("assistente.servizio.servi", servi_guasta)
    assert main(["--http"]) == 1
    assert "Errore: x" in capsys.readouterr().err
