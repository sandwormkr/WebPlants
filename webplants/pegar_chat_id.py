"""Descobre o seu chat_id do Telegram e envia uma mensagem de teste.

Antes de rodar:
  1. Coloque o TELEGRAM_TOKEN no arquivo .env
  2. Abra o seu bot no Telegram e mande /start

Uso:  python pegar_chat_id.py
"""
import os
import sys
from pathlib import Path

import requests
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent / ".env")
token = (os.getenv("TELEGRAM_TOKEN") or "").strip()
if not token:
    sys.exit("Coloque o TELEGRAM_TOKEN no arquivo .env primeiro.")

api = f"https://api.telegram.org/bot{token}"
r = requests.get(f"{api}/getUpdates", timeout=15).json()
if not r.get("ok"):
    sys.exit(f"Erro do Telegram: {r.get('description')}. Confira o token.")

vistos = {}
for upd in r["result"]:
    msg = upd.get("message") or upd.get("edited_message")
    if msg:
        chat = msg["chat"]
        vistos[chat["id"]] = chat.get("username") or chat.get("first_name") or chat.get("title")

if not vistos:
    sys.exit("Nenhuma mensagem encontrada. Abra o bot no Telegram, mande /start e rode de novo.")

print("Conversas encontradas:")
for chat_id, nome in vistos.items():
    print(f"  chat_id = {chat_id}   (@{nome})")

alvo = next((cid for cid, nome in vistos.items() if str(nome).lower() == "sandwormkr"), None)
if alvo is None and len(vistos) == 1:
    alvo = next(iter(vistos))

if alvo is not None:
    print(f"\nColoque no .env:  TELEGRAM_CHAT_ID={alvo}")
    t = requests.post(f"{api}/sendMessage", data={
        "chat_id": alvo, "text": "✅ WebPlants conectado! Os alertas de manchas chegarão aqui."
    }, timeout=15).json()
    print("Mensagem de teste enviada." if t.get("ok") else f"Falha no teste: {t.get('description')}")
