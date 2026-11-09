"""Logica pura dell'inventario: caricamento, validazione, ricerca e dettaglio."""

import pytest

from archivio.inventario import PERCORSO_INVENTARIO, ErroreInventario, carica

INTESTAZIONE = "codice;nome;categoria;quantita;collocazione;descrizione"

MULTIMETRO = "MIS-001;Multimetro digitale;strumenti di misura;4;Armadio A, ripiano 2;Fluke 115"
OSCILLOSCOPIO = "MIS-002;Oscilloscopio;strumenti di misura;1;Bancone 3;"
PINZA = "ATT-001;Pinza;attrezzi;1;Cassetto;"


def scrivi_csv(tmp_path, righe, *, bom=False, fine="\n"):
    testo = fine.join([INTESTAZIONE, *righe]) + fine
    percorso = tmp_path / "inventario.csv"
    percorso.write_bytes((("﻿" if bom else "") + testo).encode("utf-8"))
    return percorso


def inventario(tmp_path, righe):
    return carica(scrivi_csv(tmp_path, righe))


def test_carica_valido(tmp_path):
    inv = inventario(
        tmp_path,
        [
            "  MIS-001 ; Multimetro ; strumenti ; 4 ; Armadio ; Nota ",
            "ATT-001;Pinza;attrezzi;0;Cassetto;",
        ],
    )
    assert len(inv.articoli) == 2
    a = next(x for x in inv.articoli if x.codice == "MIS-001")
    assert (a.codice, a.nome, a.categoria, a.collocazione, a.descrizione) == (
        "MIS-001", "Multimetro", "strumenti", "Armadio", "Nota",
    )
    assert a.quantita == 4 and isinstance(a.quantita, int)


def test_csv_da_excel(tmp_path):
    percorso = scrivi_csv(
        tmp_path,
        ['MIS-001;Multimetro;strumenti;4;Armadio;"tensione; corrente"'],
        bom=True,
        fine="\r\n",
    )
    assert carica(percorso).articoli[0].descrizione == "tensione; corrente"


@pytest.mark.parametrize(
    "testo, riga",
    [
        ("codice;nome;categoria;quantita;collocazione\n", 1),
        (INTESTAZIONE + "\nA-1;nome;cat;1;dove\n", 2),
        (INTESTAZIONE + "\n;nome;cat;1;dove;d\n", 2),
        (INTESTAZIONE + "\nA-1;;cat;1;dove;d\n", 2),
        (INTESTAZIONE + "\nA-1;nome;;1;dove;d\n", 2),
        (INTESTAZIONE + "\nA-1;nome;cat;1;;d\n", 2),
        (INTESTAZIONE + "\nMIS-001;a;c;1;d;\nmis-001;b;c;1;d;\n", 3),
        (INTESTAZIONE + "\nA-1;nome;cat;-1;dove;d\n", 2),
        (INTESTAZIONE + "\nA-1;nome;cat;due;dove;d\n", 2),
        (INTESTAZIONE + "\nA-1;nome;cat;4.0;dove;d\n", 2),
    ],
)
def test_errori_di_validazione(tmp_path, testo, riga):
    percorso = tmp_path / "inventario.csv"
    percorso.write_text(testo, encoding="utf-8")
    with pytest.raises(ErroreInventario, match=rf"^inventario non valido, riga {riga}: .+\.$"):
        carica(percorso)


@pytest.mark.parametrize("testo", ["", "\n\n", " ; ;\n"])
def test_file_senza_intestazione(tmp_path, testo):
    percorso = tmp_path / "inventario.csv"
    percorso.write_text(testo, encoding="utf-8")
    with pytest.raises(ErroreInventario, match=r"^inventario non valido, riga 1: intestazione non valida\.$"):
        carica(percorso)


def test_righe_vuote_prima_dell_intestazione(tmp_path):
    percorso = tmp_path / "inventario.csv"
    percorso.write_text("\n\n" + INTESTAZIONE + "\n" + MULTIMETRO + "\n", encoding="utf-8")
    assert [a.codice for a in carica(percorso).articoli] == ["MIS-001"]
    percorso.write_text("\ncodice;nome\n", encoding="utf-8")
    with pytest.raises(ErroreInventario, match=r"^inventario non valido, riga 2: intestazione non valida\.$"):
        carica(percorso)


def test_descrizione_vuota_ammessa(tmp_path):
    assert inventario(tmp_path, [OSCILLOSCOPIO]).articoli[0].descrizione == ""


def test_cerca_maiuscole_e_accenti(tmp_path):
    inv = inventario(
        tmp_path,
        ["ATT-001;Saldatore a stagno;attrezzi;2;Bancone più vicino alla finestra;"],
    )
    assert inv.cerca("SALDATORE", None).startswith("Trovato 1 articolo:")
    assert inv.cerca("piu", None).startswith("Trovato 1 articolo:")


def test_cerca_singolare_plurale(tmp_path):
    inv = inventario(
        tmp_path,
        [
            "MIS-001;Multimetro digitale;strumenti di misura;1;Armadio;",
            "CAV-001;Cavo USB;cavi e connettori;3;Cassetto;",
        ],
    )
    assert "MIS-001" in inv.cerca("multimetri", None)
    assert "CAV-001" in inv.cerca("cavi", None)
    assert inv.cerca("usb", None).startswith("Trovato 1 articolo:")


def test_cerca_parole_in_and(tmp_path):
    inv = inventario(
        tmp_path,
        [
            "MIS-001;Multimetro digitale;strumenti;1;Armadio A;",
            "MIS-002;Multimetro analogico;strumenti;1;Bancone;",
            "ATT-001;Pinza;attrezzi;1;Armadio B;",
        ],
    )
    risultato = inv.cerca("multimetro armadio", None)
    assert risultato.startswith("Trovato 1 articolo:")
    assert "MIS-001" in risultato and "MIS-002" not in risultato


def test_cerca_formato(tmp_path):
    inv = inventario(tmp_path, [OSCILLOSCOPIO, MULTIMETRO])
    assert inv.cerca("misura", None) == (
        "Trovati 2 articoli:\n"
        "- MIS-001 — Multimetro digitale — 4 pezzi — Armadio A, ripiano 2\n"
        "- MIS-002 — Oscilloscopio — 1 pezzo — Bancone 3"
    )
    zero = inventario(tmp_path, ["MIS-001;Multimetro;strumenti;0;Armadio;"])
    assert "— 0 pezzi —" in zero.cerca("multimetro", None)


def test_cerca_limite(tmp_path):
    righe = [f"ATT-{n:03d};Pinza {n};attrezzi;1;Cassetto;" for n in range(12)]
    linee = inventario(tmp_path, righe).cerca("pinza", None).split("\n")
    assert linee[0] == "Trovati 12 articoli:"
    assert sum(1 for linea in linee if linea.startswith("- ")) == 10
    assert linee[-1] == "(altri 2 risultati: restringere la ricerca)"


def test_cerca_categoria(tmp_path):
    inv = inventario(tmp_path, [MULTIMETRO, PINZA])
    risultato = inv.cerca(None, "Strumenti di Misura")
    assert risultato.startswith("Trovato 1 articolo:") and "MIS-001" in risultato
    assert inv.cerca("multimetro", "attrezzi").startswith("Nessun articolo trovato")


def test_cerca_categoria_sconosciuta(tmp_path):
    inv = inventario(tmp_path, [MULTIMETRO, PINZA])
    assert inv.cerca(None, "cucina") == (
        "Errore: categoria sconosciuta 'cucina'. Categorie: attrezzi, strumenti di misura."
    )


def test_cerca_nessun_risultato(tmp_path):
    inv = inventario(tmp_path, [MULTIMETRO, PINZA])
    assert inv.cerca(" Laser ", None) == "Nessun articolo trovato per «Laser»."
    assert inv.cerca(" Laser ", " attrezzi ") == (
        "Nessun articolo trovato per «Laser» nella categoria «attrezzi»."
    )
    # Le categorie sono ricavate dai dati: la sola categoria trova sempre almeno un articolo.
    assert inv.cerca("Multimetro", "Attrezzi") == (
        "Nessun articolo trovato per «Multimetro» nella categoria «Attrezzi»."
    )


def test_cerca_parametri_vuoti(tmp_path):
    inv = inventario(tmp_path, [MULTIMETRO])
    atteso = "Errore: indicare un testo da cercare o una categoria."
    assert inv.cerca(None, None) == atteso
    assert inv.cerca("  ", "") == atteso


def test_cerca_troppo_lungo(tmp_path):
    inv = inventario(tmp_path, [MULTIMETRO])
    atteso = "Errore: testo troppo lungo (massimo 100 caratteri)."
    assert inv.cerca("a" * 101, None) == atteso
    assert inv.cerca(None, "a" * 101) == atteso
    assert inv.cerca("a" * 100, None) != atteso
    assert inv.cerca(None, "a" * 100) != atteso


def test_dettaglio(tmp_path):
    inv = inventario(tmp_path, [MULTIMETRO.replace("Fluke 115", "Fluke 115: tensione")])
    assert inv.dettaglio("  mis-001 ") == (
        "Codice: MIS-001\n"
        "Nome: Multimetro digitale\n"
        "Categoria: strumenti di misura\n"
        "Quantità: 4\n"
        "Collocazione: Armadio A, ripiano 2\n"
        "Descrizione: Fluke 115: tensione"
    )
    vuoto = inventario(tmp_path, [OSCILLOSCOPIO])
    assert vuoto.dettaglio("MIS-002").endswith("Descrizione: (nessuna)")


def test_dettaglio_errori(tmp_path):
    inv = inventario(tmp_path, [MULTIMETRO])
    vuoto = "Errore: indicare il codice dell'articolo, per esempio MIS-001."
    assert inv.dettaglio("") == vuoto
    assert inv.dettaglio(None) == vuoto
    assert inv.dettaglio("XYZ-9") == "Errore: nessun articolo con codice 'XYZ-9'."
    assert inv.dettaglio("a" * 101) == "Errore: testo troppo lungo (massimo 100 caratteri)."


def test_codice_canonico(tmp_path):
    inv = inventario(tmp_path, [MULTIMETRO])
    assert inv.codice_canonico(" mis-001 ") == "MIS-001"
    assert inv.codice_canonico("XYZ-9") is None
    assert inv.codice_canonico("") is None


def test_inventario_del_pacchetto():
    inv = carica(PERCORSO_INVENTARIO)
    assert len(inv.articoli) >= 20
    assert {a.categoria for a in inv.articoli} == {
        "strumenti di misura", "alimentatori", "componenti passivi",
        "schede e microcontrollori", "cavi e connettori", "attrezzi", "sicurezza",
    }
    mis = next(a for a in inv.articoli if a.codice == "MIS-001")
    assert "Multimetro" in mis.nome and mis.quantita > 1
    assert any(a.quantita == 0 for a in inv.articoli)
