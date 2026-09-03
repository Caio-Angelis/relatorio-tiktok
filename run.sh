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

if grep -Eiq '^AI_ENABLED[[:space:]]*=[[:space:]]*(true|1|yes|on)[[:space:]]*$' app/.env; then
  if ! python - <<'PY'
import importlib.util
required = ("torch", "transformers", "faster_whisper", "yt_dlp")
raise SystemExit(0 if all(importlib.util.find_spec(name) for name in required) else 1)
PY
  then
    echo "Aviso: AI_ENABLED=true, mas as dependências pesadas não estão instaladas. Execute ./setup_ai.sh."
  fi
fi

exec python -m app.app
