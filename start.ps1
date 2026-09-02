$ErrorActionPreference = "Stop"
$projectRoot = $PSScriptRoot

foreach ($commandName in @("uv", "node", "npm")) {
    if (-not (Get-Command $commandName -ErrorAction SilentlyContinue)) {
        throw "Missing $commandName. Install uv and Node.js 20 or newer, then run start.ps1 again."
    }
}

if (-not $env:UV_CACHE_DIR) {
    $env:UV_CACHE_DIR = Join-Path $projectRoot ".cache\uv"
}
if (-not $env:npm_config_cache) {
    $env:npm_config_cache = Join-Path $projectRoot ".cache\npm"
}

if (-not $env:AI_GALGAME_DATA_DIR) {
    $env:AI_GALGAME_DATA_DIR = Join-Path $projectRoot ".data"
}
$serverHost = if ($env:AI_GALGAME_HOST) { $env:AI_GALGAME_HOST } else { "127.0.0.1" }
$serverPort = if ($env:AI_GALGAME_PORT) { $env:AI_GALGAME_PORT } else { "8765" }

Push-Location $projectRoot
try {
    uv sync --extra dev
    uv run alembic upgrade head
    Push-Location "frontend"
    try {
        npm install
        npm run build
    } finally {
        Pop-Location
    }
    $appUrl = "http://${serverHost}:${serverPort}"
    Start-Process $appUrl
    uv run uvicorn app.main:app --app-dir backend --host $serverHost --port $serverPort
} finally {
    Pop-Location
}
