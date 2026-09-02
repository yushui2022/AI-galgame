#!/usr/bin/env sh
set -eu

PROJECT_ROOT=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
export AI_GALGAME_DATA_DIR="${AI_GALGAME_DATA_DIR:-$PROJECT_ROOT/.data}"
export AI_GALGAME_HOST="${AI_GALGAME_HOST:-127.0.0.1}"
export AI_GALGAME_PORT="${AI_GALGAME_PORT:-8765}"
export UV_CACHE_DIR="${UV_CACHE_DIR:-$PROJECT_ROOT/.cache/uv}"
export npm_config_cache="${npm_config_cache:-$PROJECT_ROOT/.cache/npm}"

for command_name in uv node npm; do
  if ! command -v "$command_name" >/dev/null 2>&1; then
    echo "缺少 $command_name。请先安装 uv 与 Node.js 20 或更高版本。" >&2
    exit 1
  fi
done

cd "$PROJECT_ROOT"
uv sync --extra dev
uv run alembic upgrade head
cd frontend
npm install
npm run build
cd "$PROJECT_ROOT"
uv run uvicorn app.main:app --app-dir backend --host "$AI_GALGAME_HOST" --port "$AI_GALGAME_PORT"
