# Windows용 작업 스크립트. 사용: .\tasks.ps1 setup | seed | collect | smoke | run | api | web | test | eval | eval-live
param([Parameter(Position = 0)][string]$Task = "help")
$ErrorActionPreference = "Stop"
$Root = $PSScriptRoot
$Py = Join-Path $Root ".venv\Scripts\python.exe"

switch ($Task) {
  "setup" {
    if (-not (Test-Path $Py)) { py -3 -m venv (Join-Path $Root ".venv") }
    & $Py -m pip install -r (Join-Path $Root "requirements.txt")
    Push-Location (Join-Path $Root "frontend"); npm install; Pop-Location
    if (-not (Test-Path (Join-Path $Root ".env"))) { Copy-Item (Join-Path $Root ".env.example") (Join-Path $Root ".env") }
  }
  "seed" {
    & $Py (Join-Path $Root "scripts\gen_market_sample.py")
    & $Py (Join-Path $Root "scripts\gen_fake_sessions.py")
  }
  "collect" {
    & $Py (Join-Path $Root "collectors\work24_courses.py")                  # 학습경로 카탈로그
    & $Py (Join-Path $Root "collectors\work24_courses.py") --region-scan    # 지역 전수 (공급 집계용)
    & $Py (Join-Path $Root "collectors\alio_postings.py")                   # 잡알리오 공공기관 공고 (ALIO_API_KEY)
    & $Py (Join-Path $Root "collectors\build_supply.py")                    # 스킬 x 지역 공급
  }
  "smoke" { & $Py (Join-Path $Root "scripts\smoke_bedrock.py") }
  "api" {
    Push-Location (Join-Path $Root "backend"); & $Py -m uvicorn app.main:app --reload --port 8010; Pop-Location
  }
  "web" {
    Push-Location (Join-Path $Root "frontend"); npm run dev; Pop-Location
  }
  "run" {
    # 백엔드는 새 창, 프런트는 현재 창
    Start-Process powershell -ArgumentList "-NoExit", "-Command", "& '$Root\tasks.ps1' api"
    Push-Location (Join-Path $Root "frontend"); npm run dev; Pop-Location
  }
  "test" { & $Py -m pytest (Join-Path $Root "backend\tests") -q }
  "eval" { & $Py (Join-Path $Root "eval\run_eval.py") }                   # 저장된 Bedrock 예측으로 eval\report.md
  "eval-live" { & $Py (Join-Path $Root "eval\run_eval.py") --live }       # aws sso login --profile kosa 후
  default { Write-Host "사용법: .\tasks.ps1 setup | seed | collect | smoke | run | api | web | test | eval | eval-live | mine | mine-free" }
}
