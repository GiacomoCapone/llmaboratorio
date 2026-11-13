// Pagina delle conversazioni: parla solo con /api/... (il servizio del front-end inoltra al back-end).
// Ogni testo che arriva dal back-end va nella pagina con textContent, mai come HTML.
"use strict";

const stato = {
  conversazioni: [],
  apertaId: null,
  messaggi: [],
  avviso: null, // {testo, tipo: "errore" | "info"}
  turnoInCorso: null, // {id, domanda, inizio, cronometro}; id null mentre si prepara l'invio
  prompts: null, // [{nome, argomenti, descrizione}] quando caricati
  erroreComandi: null,
  menuChiuso: false,
};

const $ = (id) => document.getElementById(id);

// ---------------------------------------------------------------- chiamate

// Esito: {ok: true, stato, dati} oppure {ok: false, stato, errore, forseSalvato}.
async function chiamaApi(metodo, percorso, corpo) {
  const opzioni = { method: metodo, headers: {} };
  if (corpo !== undefined) {
    opzioni.headers["Content-Type"] = "application/json";
    opzioni.body = JSON.stringify(corpo);
  }
  let risposta;
  try {
    risposta = await fetch("/api/" + percorso, opzioni);
  } catch (e) {
    return { ok: false, stato: 0, errore: "errore di rete: " + e.message, forseSalvato: true };
  }
  let dati = null;
  if (risposta.status !== 204) {
    try {
      dati = await risposta.json();
    } catch {
      dati = null;
    }
  }
  if (risposta.ok) {
    return { ok: true, stato: risposta.status, dati };
  }
  const errore =
    dati && typeof dati.errore === "string" ? dati.errore : "errore " + risposta.status;
  const forseSalvato = risposta.status === 502 && errore.startsWith("back-end non disponibile:");
  return { ok: false, stato: risposta.status, errore, forseSalvato };
}

// ---------------------------------------------------------------- comandi

function elencoPrompt(prompts) {
  if (prompts.length === 0) {
    return "Nessun prompt disponibile.";
  }
  return prompts.map(descriviPrompt).join("\n");
}

function descriviPrompt(p) {
  return ["/" + p.nome, ...p.argomenti.map((a) => "<" + a + ">")].join(" ") + " — " + p.descrizione;
}

// Come str.split(maxsplit=n-1) di Python su un testo senza spazi ai bordi.
function dividi(testo, n) {
  const parti = [];
  let resto = testo;
  while (resto && parti.length < n - 1) {
    const m = resto.match(/^(\S+)\s+([\s\S]*)$/);
    if (!m) {
      break;
    }
    parti.push(m[1]);
    resto = m[2];
  }
  if (resto) {
    parti.push(resto);
  }
  return parti;
}

// Riga scritta → {tipo: "domanda" | "elenco" | "errore" | "prompt", ...}; stesse regole della CLI.
function scomponiComando(riga, prompts) {
  const testo = riga.trim();
  if (!testo.startsWith("/")) {
    return { tipo: "domanda", testo };
  }
  const corpo = testo.slice(1);
  const spazio = corpo.search(/\s/);
  const nome = spazio < 0 ? corpo : corpo.slice(0, spazio);
  const resto = spazio < 0 ? "" : corpo.slice(spazio).trim();
  if (nome === "prompt" && !resto) {
    return { tipo: "elenco", testo: elencoPrompt(prompts) };
  }
  const voce = prompts.find((p) => p.nome === nome);
  if (!voce) {
    return {
      tipo: "errore",
      testo: "Errore: prompt sconosciuto '/" + nome + "'. Scrivere /prompt per l'elenco.",
    };
  }
  if (voce.argomenti.length === 0) {
    if (resto) {
      return { tipo: "errore", testo: "Errore: /" + nome + " non ha argomenti." };
    }
    return { tipo: "prompt", nome, argomenti: {} };
  }
  const valori = dividi(resto, voce.argomenti.length);
  if (valori.length < voce.argomenti.length) {
    const richiesti = voce.argomenti.map((a) => "<" + a + ">").join(" ");
    return { tipo: "errore", testo: "Errore: /" + nome + " richiede: " + richiesti + "." };
  }
  const argomenti = {};
  voce.argomenti.forEach((a, i) => {
    argomenti[a] = valori[i];
  });
  return { tipo: "prompt", nome, argomenti };
}

async function caricaPrompt() {
  const esito = await chiamaApi("GET", "prompt");
  if (esito.ok && esito.dati && Array.isArray(esito.dati.prompt)) {
    stato.prompts = esito.dati.prompt;
    stato.erroreComandi = null;
  } else {
    stato.erroreComandi = esito.ok ? "risposta non valida" : esito.errore;
  }
  aggiornaMenu();
}

// ---------------------------------------------------------------- date

function dueCifre(n) {
  return String(n).padStart(2, "0");
}

function oraBreve(iso) {
  const data = new Date(iso);
  if (Number.isNaN(data.getTime())) {
    return "";
  }
  const ora = dueCifre(data.getHours()) + ":" + dueCifre(data.getMinutes());
  if (data.toDateString() === new Date().toDateString()) {
    return ora;
  }
  return dueCifre(data.getDate()) + "/" + dueCifre(data.getMonth() + 1) + " " + ora;
}

function durata(ms) {
  const secondi = Math.floor(ms / 1000);
  return Math.floor(secondi / 60) + ":" + dueCifre(secondi % 60);
}

// ---------------------------------------------------------------- disegno

function nuovo(tag, classe, testo) {
  const elemento = document.createElement(tag);
  if (classe) {
    elemento.className = classe;
  }
  if (testo !== undefined) {
    elemento.textContent = testo;
  }
  return elemento;
}

function disegnaElenco() {
  const elenco = $("elenco");
  elenco.replaceChildren();
  for (const c of stato.conversazioni) {
    const pulsante = nuovo("button", c.id === stato.apertaId ? "aperta" : "");
    pulsante.type = "button";
    pulsante.append(nuovo("span", "voce-titolo", c.titolo), nuovo("span", "voce-ora", oraBreve(c.aggiornata)));
    pulsante.title = c.titolo;
    pulsante.addEventListener("click", () => apri(c.id));
    const voce = nuovo("li");
    voce.append(pulsante);
    elenco.append(voce);
  }
}

function conversazioneAperta() {
  return stato.conversazioni.find((c) => c.id === stato.apertaId) || null;
}

function disegnaChat() {
  const aperta = conversazioneAperta();
  $("titolo").textContent = aperta ? aperta.titolo : "Assistente del laboratorio";
  $("elimina").hidden = stato.apertaId === null;

  const area = $("messaggi");
  area.replaceChildren();
  if (stato.apertaId === null && !stato.turnoInCorso && !stato.avviso) {
    area.append(
      nuovo(
        "p",
        "invito",
        "Scegli una conversazione a sinistra, oppure scrivi una domanda per iniziarne una nuova.\n" +
          "I comandi dell'archivio iniziano con / (scrivi /prompt per l'elenco)."
      )
    );
  }
  for (const m of stato.messaggi) {
    const elemento = nuovo("div", "messaggio " + m.ruolo);
    elemento.append(nuovo("span", "ora", oraBreve(m.ora)), document.createTextNode(m.testo));
    area.append(elemento);
  }
  const turno = stato.turnoInCorso;
  if (turno && turno.partito && turno.id === stato.apertaId) {
    const provvisorio = nuovo("div", "messaggio utente provvisorio");
    provvisorio.append(nuovo("span", "ora", oraBreve(new Date(turno.inizio).toISOString())), document.createTextNode(turno.domanda));
    const attesa = nuovo("div", "attesa");
    attesa.id = "attesa";
    area.append(provvisorio, attesa);
    aggiornaCronometro();
  }
  if (stato.avviso) {
    area.append(nuovo("div", "avviso " + stato.avviso.tipo, stato.avviso.testo));
  }
  area.scrollTop = area.scrollHeight;
  aggiornaControlli();
}

function aggiornaCronometro() {
  const attesa = $("attesa");
  if (attesa && stato.turnoInCorso) {
    attesa.textContent =
      "L'assistente sta rispondendo… (" + durata(Date.now() - stato.turnoInCorso.inizio) + ")";
  }
}

function aggiornaControlli() {
  const occupato = stato.turnoInCorso !== null;
  $("casella").disabled = occupato;
  $("invia").disabled = occupato;
  $("elimina").disabled = occupato && stato.turnoInCorso.id === stato.apertaId;
}

function mostraAvviso(testo, tipo) {
  stato.avviso = { testo, tipo };
  disegnaChat();
}

// ---------------------------------------------------------------- menu dei comandi

function vociMenu(scritto) {
  const nome = scritto.slice(1);
  const voci = [];
  for (const p of stato.prompts) {
    if (p.nome.startsWith(nome)) {
      voci.push({ nome: p.nome, testo: descriviPrompt(p) });
    }
  }
  if ("prompt".startsWith(nome)) {
    voci.push({ nome: "prompt", testo: "/prompt — elenco dei comandi" });
  }
  return voci;
}

function aggiornaMenu() {
  const menu = $("menu");
  const scritto = $("casella").value;
  menu.replaceChildren();
  if (stato.menuChiuso || !scritto.startsWith("/") || /\s/.test(scritto)) {
    menu.hidden = true;
    return;
  }
  if (stato.prompts === null) {
    if (stato.erroreComandi === null) {
      menu.hidden = true;
      return;
    }
    menu.append(nuovo("li", "non-disponibile", "Comandi non disponibili: " + stato.erroreComandi));
    menu.hidden = false;
    return;
  }
  const voci = vociMenu(scritto);
  for (const voce of voci) {
    const riga = nuovo("li", "", voce.testo);
    riga.addEventListener("mousedown", (evento) => {
      evento.preventDefault(); // la casella resta col fuoco
      completa(voce.nome);
    });
    menu.append(riga);
  }
  menu.hidden = voci.length === 0;
}

function completa(nome) {
  const casella = $("casella");
  casella.value = "/" + nome + " ";
  casella.focus();
  aggiornaMenu();
}

// ---------------------------------------------------------------- azioni

async function ricaricaElenco() {
  const esito = await chiamaApi("GET", "conversazioni");
  const errore = $("errore-elenco");
  if (esito.ok && esito.dati && Array.isArray(esito.dati.conversazioni)) {
    stato.conversazioni = esito.dati.conversazioni;
    errore.hidden = true;
  } else {
    errore.textContent = esito.ok ? "risposta non valida" : esito.errore;
    errore.hidden = false;
  }
  disegnaElenco();
  disegnaChat();
}

async function apri(id) {
  document.body.classList.remove("elenco-aperto");
  stato.apertaId = id;
  stato.messaggi = [];
  stato.avviso = null;
  disegnaElenco();
  disegnaChat();
  const esito = await chiamaApi("GET", "conversazioni/" + id);
  if (stato.apertaId !== id) {
    return; // nel frattempo se n'è aperta un'altra
  }
  if (esito.ok && esito.dati && Array.isArray(esito.dati.messaggi)) {
    stato.messaggi = esito.dati.messaggi;
    disegnaChat();
  } else {
    mostraAvviso(esito.ok ? "risposta non valida" : esito.errore, "errore");
  }
}

async function creaConversazione() {
  const esito = await chiamaApi("POST", "conversazioni");
  if (!esito.ok) {
    mostraAvviso(esito.errore, "errore");
    return null;
  }
  stato.conversazioni = [esito.dati, ...stato.conversazioni.filter((c) => c.id !== esito.dati.id)];
  return esito.dati.id;
}

async function nuovaConversazione() {
  const id = await creaConversazione();
  if (id !== null) {
    await apri(id);
  }
}

async function elimina() {
  const aperta = conversazioneAperta();
  if (stato.apertaId === null) {
    return;
  }
  const id = stato.apertaId;
  const titolo = aperta ? aperta.titolo : String(id);
  if (!window.confirm("Eliminare la conversazione «" + titolo + "»?")) {
    return;
  }
  const esito = await chiamaApi("DELETE", "conversazioni/" + id);
  if (!esito.ok) {
    mostraAvviso(esito.errore, "errore");
    return;
  }
  if (stato.apertaId === id) {
    stato.apertaId = null;
    stato.messaggi = [];
    stato.avviso = null;
  }
  await ricaricaElenco();
}

function fineTurno() {
  if (stato.turnoInCorso && stato.turnoInCorso.cronometro) {
    clearInterval(stato.turnoInCorso.cronometro);
  }
  stato.turnoInCorso = null;
}

// Ricarica i messaggi di `id` dal back-end, se è ancora la conversazione aperta.
async function ricaricaMessaggi(id) {
  const esito = await chiamaApi("GET", "conversazioni/" + id);
  if (stato.apertaId === id && esito.ok && esito.dati && Array.isArray(esito.dati.messaggi)) {
    stato.messaggi = esito.dati.messaggi;
    disegnaChat();
  }
}

// Prepara il corpo del messaggio; null se la riga si risolve nella pagina (avviso già mostrato).
async function corpoDelMessaggio(riga) {
  if (!riga.trim().startsWith("/")) {
    return { domanda: riga.trim() };
  }
  if (stato.prompts === null) {
    await caricaPrompt();
  }
  if (stato.prompts === null) {
    mostraAvviso("Comandi non disponibili: " + stato.erroreComandi, "errore");
    return null;
  }
  const comando = scomponiComando(riga, stato.prompts);
  if (comando.tipo === "errore" || comando.tipo === "elenco") {
    mostraAvviso(comando.testo, comando.tipo === "errore" ? "errore" : "info");
    return null;
  }
  return { prompt: { nome: comando.nome, argomenti: comando.argomenti } };
}

async function invia() {
  const casella = $("casella");
  const riga = casella.value;
  if (stato.turnoInCorso || !riga.trim()) {
    return;
  }
  // Si blocca subito, prima di ogni attesa: un secondo Invio non deve mandare due messaggi.
  // La conversazione di destinazione è quella aperta adesso, anche se poi se ne apre un'altra.
  stato.turnoInCorso = { id: stato.apertaId, domanda: riga.trim(), inizio: Date.now(), cronometro: null, partito: false };
  stato.avviso = null;
  stato.menuChiuso = true;
  aggiornaMenu();
  disegnaChat();
  try {
    const corpo = await corpoDelMessaggio(riga);
    if (corpo === null) {
      return;
    }
    let id = stato.turnoInCorso.id;
    if (id === null) {
      id = await creaConversazione();
      if (id === null) {
        return;
      }
      stato.turnoInCorso.id = id;
      if (stato.apertaId === null) {
        stato.apertaId = id; // nel frattempo non se n'è aperta un'altra
        stato.messaggi = [];
      }
      disegnaElenco();
    }

    stato.turnoInCorso.partito = true;
    stato.turnoInCorso.inizio = Date.now();
    stato.turnoInCorso.cronometro = setInterval(aggiornaCronometro, 1000);
    disegnaChat();

    const esito = await chiamaApi("POST", "conversazioni/" + id + "/messaggi", corpo);
    fineTurno();
    if (esito.ok && esito.dati && Array.isArray(esito.dati.messaggi)) {
      casella.value = "";
      stato.menuChiuso = false;
      await ricaricaElenco();
      await ricaricaMessaggi(id);
    } else {
      // L'avviso va nella conversazione del turno: se se n'è aperta un'altra, si torna a quella.
      if (stato.apertaId !== id) {
        await apri(id);
      }
      const errore = esito.ok ? "risposta non valida" : esito.errore;
      const nota = esito.forseSalvato
        ? "Il messaggio potrebbe non essere stato salvato: riapri la conversazione per controllare."
        : "Il messaggio non è stato salvato.";
      mostraAvviso(errore + "\n" + nota, "errore");
    }
  } finally {
    fineTurno();
    disegnaChat();
    casella.focus();
  }
}

// ---------------------------------------------------------------- eventi

function collega() {
  const casella = $("casella");
  $("nuova").addEventListener("click", nuovaConversazione);
  $("elimina").addEventListener("click", elimina);
  $("mostra-elenco").addEventListener("click", () => document.body.classList.toggle("elenco-aperto"));
  $("modulo").addEventListener("submit", (evento) => {
    evento.preventDefault();
    invia();
  });
  casella.addEventListener("input", () => {
    stato.menuChiuso = false;
    aggiornaMenu();
  });
  casella.addEventListener("keydown", (evento) => {
    const menuAperto = !$("menu").hidden;
    if (evento.key === "Enter" && !evento.shiftKey && !evento.isComposing) {
      evento.preventDefault();
      invia();
    } else if (evento.key === "Tab" && menuAperto && stato.prompts !== null) {
      const voci = vociMenu(casella.value);
      if (voci.length > 0) {
        evento.preventDefault();
        completa(voci[0].nome);
      }
    } else if (evento.key === "Escape" && menuAperto) {
      stato.menuChiuso = true;
      aggiornaMenu();
    }
  });
  casella.addEventListener("blur", () => {
    $("menu").hidden = true;
  });
  casella.addEventListener("focus", aggiornaMenu);
}

collega();
disegnaChat();
ricaricaElenco();
caricaPrompt();
