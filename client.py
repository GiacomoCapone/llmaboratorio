"""Client minimo per il server locale di LM Studio.

Scheletro da completare con Claude Code (slide 19-22):
configurazione, messaggi, payload e chiamata HTTP.
Import e gestione degli errori sono gia' presenti: conservarli.
"""

import os

import requests
from dotenv import load_dotenv

# --- Configurazione -------------------------------------------------------
load_dotenv()
base_url = os.environ["LM_BASE_URL"].rstrip("/")
model = os.environ["LM_MODEL"]

# --- Messaggi -------------------------------------------------------------
question = input("Domanda: ").strip()
if not question:
    raise SystemExit("Domanda vuota: nessuna richiesta inviata.")

messages = [
    {"role": "system", "content": "Sei un assistente conciso. Rispondi sempre in italiano."},
    {"role": "user", "content": question},
]

# --- Payload --------------------------------------------------------------
payload = {
    "model": model,
    "messages": messages,
    "temperature": 0.2,
    "max_tokens": 300,
    "reasoning_effort": "none",
    "stream": False,
}

# --- Chiamata -------------------------------------------------------------
try:
    response = requests.post(f"{base_url}/v1/chat/completions", json=payload, timeout=60)
    response.raise_for_status()
    print(response.json()["choices"][0]["message"]["content"])
except requests.exceptions.Timeout:
    print("Attesa scaduta: controllare server, carico e tempi.")
except requests.exceptions.ConnectionError:
    print("Connessione fallita: controllare server, URL e porta.")
except requests.exceptions.HTTPError:
    print("Errore HTTP:", response.status_code, response.text)
