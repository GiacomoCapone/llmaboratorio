"""Modello finto per i test del grafo: risposte predefinite, nessun server."""

from langchain_core.messages import AIMessage

from assistente.revisore import Valutazione
from assistente.router import Classificazione
from assistente.strumenti.orologio import NOME_ORA_CORRENTE


class LlmFinto:
    def __init__(self, risposte: list[AIMessage], ripeti_ultima: bool = False):
        self.risposte = list(risposte)
        self.ripeti_ultima = ripeti_ultima
        self.chiamate: list[list] = []
        self.strumenti: list = []
        self.opzioni_strumenti: dict = {}  # argomenti in più passati a bind_tools
        self.con_strumenti: list[bool] = []  # per invocazione: con o senza strumenti
        self._indice = 0

    def bind_tools(self, tools, **opzioni) -> "_LlmLegato":
        self.strumenti = list(tools)
        self.opzioni_strumenti = opzioni
        return _LlmLegato(self)

    def invoke(self, messaggi) -> AIMessage:
        return self._rispondi(messaggi, con_strumenti=False)

    def _rispondi(self, messaggi, con_strumenti: bool) -> AIMessage:
        self.con_strumenti.append(con_strumenti)
        self.chiamate.append(list(messaggi))
        if self._indice < len(self.risposte):
            risposta = self.risposte[self._indice]
            self._indice += 1
        elif self.ripeti_ultima and self.risposte:
            risposta = self.risposte[-1]
        else:
            raise AssertionError("LlmFinto: risposte esaurite")
        # Come un modello vero, ogni invocazione produce un messaggio nuovo: senza
        # copia, add_messages (che deduplica per id) sostituirebbe la ripetizione.
        return risposta.model_copy(update={"id": None}, deep=True)


class _LlmLegato:
    """Vista restituita da bind_tools: le invocazioni risultano fatte con gli strumenti."""

    def __init__(self, base: LlmFinto):
        self.base = base

    def invoke(self, messaggi) -> AIMessage:
        return self.base._rispondi(messaggi, con_strumenti=True)


class RouterFinto:
    """Router simulato: restituisce le categorie indicate (l'ultima si ripete)."""

    def __init__(self, categoria: str | list[str], motivo: str = "motivo di prova"):
        self.categorie = [categoria] if isinstance(categoria, str) else list(categoria)
        self.motivo = motivo
        self.chiamate: list[list] = []

    def __call__(self, messaggi) -> Classificazione:
        indice = min(len(self.chiamate), len(self.categorie) - 1)
        self.chiamate.append(list(messaggi))
        return Classificazione(categoria=self.categorie[indice], motivo=self.motivo)


class RevisoreFinto:
    """Revisore simulato: restituisce gli esiti indicati (l'ultimo si ripete)."""

    def __init__(self, esiti: list[bool], motivo: str = "motivo di prova"):
        self.esiti = list(esiti)
        self.motivo = motivo
        self.chiamate: list[list] = []

    def __call__(self, messaggi) -> Valutazione:
        indice = min(len(self.chiamate), len(self.esiti) - 1)
        self.chiamate.append(list(messaggi))
        return Valutazione(coerente=self.esiti[indice], motivo=self.motivo)


def richiesta(nome: str, args, id: str = "c1") -> AIMessage:
    """Una sola tool call verso lo strumento `nome`."""
    return AIMessage(content="", tool_calls=[{"name": nome, "args": args, "id": id}])


def richiesta_ora(fuso, id: str = "c1") -> AIMessage:
    return AIMessage(
        content="",
        tool_calls=[{"name": NOME_ORA_CORRENTE, "args": {"fuso": fuso}, "id": id}],
    )


def richiesta_malformata(id: str | None = "c1") -> AIMessage:
    """Tool call con argomenti non JSON: langchain la mette in invalid_tool_calls."""
    return AIMessage(
        content="",
        invalid_tool_calls=[
            {
                "name": NOME_ORA_CORRENTE,
                "args": '{"fuso": "Europe/Rome"',
                "id": id,
                "error": "JSON non valido",
            }
        ],
    )
