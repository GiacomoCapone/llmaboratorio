"""Server finto per i test: inoltra lo stdio al vero `python -m archivio` e muore alla seconda
chiamata di strumento (la prima riceve risposta), come un server che termina a metà sessione.

Uso: `python muore_dopo_una_chiamata.py`; l'ambiente (PYTHONPATH con `src/`) è quello del client.
"""

import os
import subprocess
import sys

server = subprocess.Popen([sys.executable, "-m", "archivio"], stdin=subprocess.PIPE, stdout=sys.stdout)
chiamate = 0
for riga in sys.stdin.buffer:
    if b'"tools/call"' in riga:
        chiamate += 1
        if chiamate == 2:
            server.kill()
            server.wait()
            os._exit(3)
    server.stdin.write(riga)
    server.stdin.flush()
server.stdin.close()
server.wait()
