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

Write-Host "`n[2/4] Configurando arquivo .env e banco de dados inicial..." -ForegroundColor Cyan
if (-not (Test-Path "$InstallDir\.env")) {
    Copy-Item "$InstallDir\.env.example" "$InstallDir\.env"
}
& "$InstallDir\.venv\Scripts\python.exe" "$InstallDir\seed.py"

Write-Host "`n[3/4] Criando launchers silenciosos (sem janela preta do CMD)..." -ForegroundColor Cyan
$PythonwPath = "$InstallDir\.venv\Scripts\pythonw.exe"

$TrayVbs = @"
Set WshShell = CreateObject("WScript.Shell")
WshShell.CurrentDirectory = "$InstallDir"
WshShell.Run """$PythonwPath"" ""$InstallDir\main.py"" --tray", 0, False
"@
Set-Content -Path "$InstallDir\DealsHunter-Tray.vbs" -Value $TrayVbs -Encoding UTF8

$GuiVbs = @"
Set WshShell = CreateObject("WScript.Shell")
WshShell.CurrentDirectory = "$InstallDir"
WshShell.Run """$PythonwPath"" ""$InstallDir\main.py"" --gui", 0, False
"@
Set-Content -Path "$InstallDir\DealsHunter-Panel.vbs" -Value $GuiVbs -Encoding UTF8

Write-Host "`n[4/4] Criando atalhos na Area de Trabalho e Inicializacao do Windows..." -ForegroundColor Cyan
$WshShell = New-Object -ComObject WScript.Shell

# Atalho na Area de Trabalho (abre o Painel de Controle)
$DesktopPath = [Environment]::GetFolderPath("Desktop")
$DesktopShortcut = $WshShell.CreateShortcut("$DesktopPath\Deals Hunter.lnk")
$DesktopShortcut.TargetPath = "wscript.exe"
$DesktopShortcut.Arguments = """$InstallDir\DealsHunter-Panel.vbs"""
$DesktopShortcut.WorkingDirectory = $InstallDir
$DesktopShortcut.Description = "Deals Hunter - Painel de Controle"
$DesktopShortcut.Save()

# Atalho na pasta Startup (inicia na Bandeja do Windows ao ligar o PC)
$StartupPath = [Environment]::GetFolderPath("Startup")
$StartupShortcut = $WshShell.CreateShortcut("$StartupPath\Deals Hunter Tray.lnk")
$StartupShortcut.TargetPath = "wscript.exe"
$StartupShortcut.Arguments = """$InstallDir\DealsHunter-Tray.vbs"""
$StartupShortcut.WorkingDirectory = $InstallDir
$StartupShortcut.Description = "Deals Hunter - System Tray Monitor"
$StartupShortcut.Save()

Write-Host "`nIniciando o Deals Hunter na bandeja do Windows..." -ForegroundColor Green
Start-Process "wscript.exe" -ArgumentList """$InstallDir\DealsHunter-Tray.vbs"""
Start-Process "wscript.exe" -ArgumentList """$InstallDir\DealsHunter-Panel.vbs"""

Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "Instalacao concluida! O Deals Hunter ja esta na bandeja ao lado do relogio." -ForegroundColor Green
Write-Host "============================================================" -ForegroundColor Cyan
