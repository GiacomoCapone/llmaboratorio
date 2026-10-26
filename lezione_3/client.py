"""Client minimo per il server locale di LM Studio.

Scheletro da completare con Claude Code (slide 19-22):
configurazione, messaggi, payload e chiamata HTTP.
Import e gestione degli errori sono gia' presenti: conservarli.
"""

import json
import os

import requests
from dotenv import load_dotenv

# --- Configurazione -------------------------------------------------------
load_dotenv()
base_url = os.environ["LM_BASE_URL"].rstrip("/")
model = os.environ["LM_MODEL"]

# --- Messaggi -------------------------------------------------------------
# La cronologia vive solo in memoria: alla chiusura del client si perde.
messages = [
    {"role": "system", "content": "Sei un assistente conciso. Rispondi sempre in italiano."},
]

# --- Payload --------------------------------------------------------------
payload = {
    "model": model,
    "messages": messages,
    "temperature": 0.2,
    "max_tokens": 300,
    "reasoning_effort": "none",
    "stream": True,
}

# --- Chiamata -------------------------------------------------------------
print('Scrivi una domanda; "esci" o Ctrl+C per terminare.')
try:
    while True:
        question = input("Domanda: ").strip()
        if question.lower() == "esci":
            break
        if not question:
            continue

        messages.append({"role": "user", "content": question})
        try:
            response = requests.post(
                f"{base_url}/v1/chat/completions", json=payload, timeout=60, stream=True
            )
            response.raise_for_status()
            # Risposta in streaming (SSE): una riga "data: {...}" per ogni frammento.
            parts = []
            for raw in response.iter_lines():
                line = raw.decode("utf-8")
                if not line.startswith("data: "):
                    continue
                data = line[len("data: "):]
                if data == "[DONE]":
                    break
                delta = json.loads(data)["choices"][0]["delta"]
                text = delta.get("content") or ""
                parts.append(text)
                print(text, end="", flush=True)
            print()
            answer = "".join(parts)
            if answer:
                messages.append({"role": "assistant", "content": answer})
            else:
                messages.pop()
        except requests.exceptions.Timeout:
            messages.pop()
            print("Attesa scaduta: controllare server, carico e tempi.")
        except requests.exceptions.ConnectionError:
            messages.pop()
            print("Connessione fallita: controllare server, URL e porta.")
        except requests.exceptions.HTTPError:
            messages.pop()
            print("Errore HTTP:", response.status_code, response.text)
except (KeyboardInterrupt, EOFError):
    print()
print("Arrivederci.")
