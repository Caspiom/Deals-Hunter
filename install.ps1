# ==============================================================================
# DEALS HUNTER - WINDOWS 10/11 INSTALLER (PowerShell)
# Configura venv, dependências, notificações nativas, ícone na bandeja (Tray)
# e inicialização automática com o Windows.
# ==============================================================================

$ErrorActionPreference = "Stop"
$InstallDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $InstallDir

Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "   Deals Hunter - Instalador Windows (Tray & Notificacoes)" -ForegroundColor Green
Write-Host "============================================================" -ForegroundColor Cyan

if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
    Write-Host "[ERRO] Python 3 nao encontrado! Instale em https://www.python.org/downloads/ marcando 'Add Python to PATH'." -ForegroundColor Red
    exit 1
}

Write-Host "`n[1/4] Criando ambiente virtual (.venv) e instalando pacotes..." -ForegroundColor Cyan
python -m venv .venv
& "$InstallDir\.venv\Scripts\python.exe" -m pip install --upgrade pip
& "$InstallDir\.venv\Scripts\pip.exe" install -r requirements.txt

Write-Host "`n[2/4] Configurando arquivo .env e banco de dados..." -ForegroundColor Cyan
if (-not (Test-Path "$InstallDir\.env")) {
    Copy-Item "$InstallDir\.env.example" "$InstallDir\.env"
}
& "$InstallDir\.venv\Scripts\python.exe" -c "from config import load_settings; from db import Database; Database(load_settings(False).db_path)"

Write-Host "`n[3/4] Criando launchers silenciosos (sem janela preta do CMD)..." -ForegroundColor Cyan
$PythonwPath = "$InstallDir\.venv\Scripts\pythonw.exe"

$TrayVbs = @"
Set WshShell = CreateObject("WScript.Shell")
WshShell.CurrentDirectory = "$InstallDir"
WshShell.Run """$PythonwPath"" ""$InstallDir\main.py"" --tray", 0, False
"@
[System.IO.File]::WriteAllText("$InstallDir\DealsHunter-Tray.vbs", $TrayVbs, [System.Text.Encoding]::Default)

$GuiVbs = @"
Set WshShell = CreateObject("WScript.Shell")
WshShell.CurrentDirectory = "$InstallDir"
WshShell.Run """$PythonwPath"" ""$InstallDir\main.py"" --gui", 0, False
"@
[System.IO.File]::WriteAllText("$InstallDir\DealsHunter-Panel.vbs", $GuiVbs, [System.Text.Encoding]::Default)

Write-Host "`n[4/4] Criando atalhos na Area de Trabalho e Inicializacao do Windows..." -ForegroundColor Cyan
$WshShell = New-Object -ComObject WScript.Shell

# Atalho na Area de Trabalho (abre o Painel de Controle direto via pythonw.exe)
$DesktopPath = [Environment]::GetFolderPath("Desktop")
$DesktopShortcut = $WshShell.CreateShortcut("$DesktopPath\Deals Hunter.lnk")
$DesktopShortcut.TargetPath = $PythonwPath
$DesktopShortcut.Arguments = """$InstallDir\main.py"" --gui"
$DesktopShortcut.WorkingDirectory = $InstallDir
$DesktopShortcut.Description = "Deals Hunter - Painel de Controle"
$DesktopShortcut.Save()

# Atalho na pasta Startup (inicia na Bandeja do Windows ao ligar o PC direto via pythonw.exe)
$StartupPath = [Environment]::GetFolderPath("Startup")
$StartupShortcut = $WshShell.CreateShortcut("$StartupPath\Deals Hunter Tray.lnk")
$StartupShortcut.TargetPath = $PythonwPath
$StartupShortcut.Arguments = """$InstallDir\main.py"" --tray"
$StartupShortcut.WorkingDirectory = $InstallDir
$StartupShortcut.Description = "Deals Hunter - System Tray Monitor"
$StartupShortcut.Save()

Write-Host "`nIniciando o Deals Hunter na bandeja do Windows..." -ForegroundColor Green
Start-Process -FilePath $PythonwPath -ArgumentList """$InstallDir\main.py"" --tray" -WorkingDirectory $InstallDir
Start-Process -FilePath $PythonwPath -ArgumentList """$InstallDir\main.py"" --gui" -WorkingDirectory $InstallDir

Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "Instalacao concluida! O Deals Hunter ja esta na bandeja ao lado do relogio." -ForegroundColor Green
Write-Host "============================================================" -ForegroundColor Cyan
