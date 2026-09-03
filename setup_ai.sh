#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="$ROOT_DIR/.venv"
AI_HF_CACHE_DIR="$ROOT_DIR/.cache/huggingface"

if ! command -v python3 >/dev/null 2>&1; then
  echo "Erro: Python 3 não foi encontrado."
  exit 1
fi

if ! python3 - <<'PY'
import sys
if sys.version_info < (3, 10):
    raise SystemExit("Python >= 3.10 é necessário.")
print(f"Python {sys.version.split()[0]} OK")
PY
then
  exit 1
fi

for required_binary in ffmpeg ffprobe; do
  if ! command -v "$required_binary" >/dev/null 2>&1; then
    echo "Erro: $required_binary não foi encontrado."
    echo "Instale-o com: sudo apt install ffmpeg"
    exit 1
  fi
done

if ! command -v nvidia-smi >/dev/null 2>&1; then
  echo "Erro: nvidia-smi não foi encontrado; o setup exige uma instalação CUDA funcional."
  exit 1
fi

echo "GPU detectada pelo driver:"
nvidia-smi --query-gpu=name,memory.total --format=csv,noheader

if [ ! -d "$VENV_DIR" ]; then
  echo "Criando ambiente virtual em .venv..."
  python3 -m venv "$VENV_DIR"
fi

# shellcheck disable=SC1091
source "$VENV_DIR/bin/activate"
python -m pip install --upgrade pip
python -m pip install -r "$ROOT_DIR/app/requirements-ai.txt"

mkdir -p "$ROOT_DIR/tmp/tiktok_ai" "$AI_HF_CACHE_DIR"

echo "Verificando CUDA pelo PyTorch..."
python - <<'PY'
import sys
import torch

print("torch version:", torch.__version__)
print("CUDA disponível:", torch.cuda.is_available())
print("CUDA runtime:", getattr(torch.version, "cuda", None))
if not torch.cuda.is_available():
    raise SystemExit("CUDA não está disponível no PyTorch; não há fallback automático para CPU.")
index = torch.cuda.current_device()
properties = torch.cuda.get_device_properties(index)
print("GPU:", torch.cuda.get_device_name(index))
print("VRAM total:", round(properties.total_memory / (1024**3), 1), "GB")
PY

echo "Baixando/verificando faster-whisper large-v3-turbo no cache local..."
HF_HOME="$AI_HF_CACHE_DIR" HUGGINGFACE_HUB_CACHE="$AI_HF_CACHE_DIR/hub" python - <<'PY'
from pathlib import Path
import os
import wave

from faster_whisper import WhisperModel

cache = Path(os.environ["HF_HOME"])
model = WhisperModel(
    "large-v3-turbo",
    device="cuda",
    compute_type="float16",
    download_root=str(cache / "faster-whisper"),
)
fixture = cache / "ai_setup_silence.wav"
with wave.open(str(fixture), "wb") as handle:
    handle.setnchannels(1)
    handle.setsampwidth(2)
    handle.setframerate(16000)
    handle.writeframes(b"\x00\x00" * 16000)
segments, info = model.transcribe(str(fixture), vad_filter=True)
list(segments)
print("faster-whisper carregado; idioma detectado:", getattr(info, "language", None))
fixture.unlink(missing_ok=True)
PY

echo "Baixando/verificando Qwen/Qwen3-VL-8B-Instruct no cache local..."
HF_HOME="$AI_HF_CACHE_DIR" HUGGINGFACE_HUB_CACHE="$AI_HF_CACHE_DIR/hub" python - <<'PY'
import os
from huggingface_hub import snapshot_download

path = snapshot_download("Qwen/Qwen3-VL-8B-Instruct")
print("Qwen3-VL disponível no cache:", path)
PY

echo "Executando teste de carregamento do Qwen3-VL em BF16..."
HF_HOME="$AI_HF_CACHE_DIR" HUGGINGFACE_HUB_CACHE="$AI_HF_CACHE_DIR/hub" python - <<'PY'
from app.ai.vision import QwenVisionAnalyzer

analyzer = QwenVisionAnalyzer(
    "Qwen/Qwen3-VL-8B-Instruct",
    dtype="bfloat16",
    device="cuda",
)
analyzer.load()
print("Qwen/Qwen3-VL-8B-Instruct carregado com sucesso.")
analyzer.close()
PY

echo
echo "Setup de IA local concluído com sucesso."
echo "Configure AI_ENABLED=true em app/.env e inicie com ./run.sh."
