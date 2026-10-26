"""Modello finto per i test del grafo: risposte predefinite, nessun server."""

from langchain_core.messages import AIMessage

from assistente.strumenti import NOME_ORA_CORRENTE


class LlmFinto:
    def __init__(self, risposte: list[AIMessage], ripeti_ultima: bool = False):
        self.risposte = list(risposte)
        self.ripeti_ultima = ripeti_ultima
        self.chiamate: list[list] = []
        self._indice = 0

    def bind_tools(self, tools) -> "LlmFinto":
        return self

    def invoke(self, messaggi) -> AIMessage:
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
