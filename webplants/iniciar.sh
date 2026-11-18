#!/usr/bin/env bash
# Inicia o WebPlants no Linux (Arch etc.)
set -e
cd "$(dirname "$0")"

if [ ! -x .venv/bin/python ]; then
  echo "[1/3] Criando ambiente Python..."
  python -m venv .venv
  echo "[2/3] Instalando dependências..."
  .venv/bin/pip install --upgrade pip
  .venv/bin/pip install -r requirements.txt
fi

if [ ! -f .env ]; then
  cp .env.example .env
  echo "Arquivo .env criado. Preencha-o e rode de novo."
  exit 0
fi

echo "[3/3] Iniciando WebPlants..."
exec .venv/bin/python app.py
