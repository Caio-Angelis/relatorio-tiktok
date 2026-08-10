#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT_DIR"

if ! command -v python3 >/dev/null 2>&1; then
  echo "Erro: Python 3 não foi encontrado."
  exit 1
fi

if [ ! -d .venv ]; then
  echo "Criando ambiente virtual em .venv..."
  python3 -m venv .venv
fi

# shellcheck disable=SC1091
source .venv/bin/activate
python -m pip install --upgrade pip >/dev/null
python -m pip install -r app/requirements.txt

if [ ! -f app/.env ]; then
  cp app/.env.example app/.env
  echo
  echo "Criei app/.env a partir de app/.env.example."
  echo "Preencha TIKTOK_CLIENT_KEY e TIKTOK_CLIENT_SECRET antes de conectar uma conta real."
  echo "Para testar sem TikTok, defina MOCK_TIKTOK=true em app/.env e execute ./run.sh novamente."
  exit 0
fi

exec python -m app.app
