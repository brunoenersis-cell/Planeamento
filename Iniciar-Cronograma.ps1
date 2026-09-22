# Inicia o Cronograma SafetyCulture localmente, sem depender do Codex.
$appDirectory = Split-Path -Parent $MyInvocation.MyCommand.Path
$python = Join-Path $appDirectory ".venv\Scripts\python.exe"
$port = 8515

if (-not (Test-Path -LiteralPath $python)) {
    Add-Type -AssemblyName PresentationFramework
    [System.Windows.MessageBox]::Show("Não foi encontrado o ambiente Python em .venv. Execute primeiro a instalação das dependências.", "Cronograma SafetyCulture")
    exit 1
}

$isRunning = Get-NetTCPConnection -State Listen -LocalPort $port -ErrorAction SilentlyContinue
if (-not $isRunning) {
    Start-Process -FilePath $python `
        -ArgumentList "-m", "streamlit", "run", "app.py", "--server.address", "127.0.0.1", "--server.port", "$port", "--server.headless", "true" `
        -WorkingDirectory $appDirectory `
        -WindowStyle Minimized
    Start-Sleep -Seconds 2
}

Start-Process "http://localhost:$port"

