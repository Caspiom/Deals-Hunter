#!/usr/bin/env bash
set -euo pipefail

# ==============================================================================
# DEALS HUNTER - INSTALADOR UNIVERSAL LINUX (Distros + DEs/WMs/Bars)
# Suporta: Arch, Debian/Ubuntu/Mint/Pop, Fedora, openSUSE, NixOS
# Suporta: KDE, GNOME, XFCE, Waybar, Noctalia (Niri/Hyprland), Sway, i3
# ==============================================================================

INSTALL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$INSTALL_DIR"

GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo -e "${BLUE}============================================================${NC}"
echo -e "${GREEN}   🏷️  Deals Hunter — Universal Linux Installer${NC}"
echo -e "${BLUE}============================================================${NC}"

# 1. Detectar Distro e garantir Python 3
detect_and_install_deps() {
    if command -v python3 >/dev/null 2>&1; then
        echo -e "${GREEN}✓${NC} Python 3 detectado: $(python3 --version)"
        return
    fi

    echo -e "${YELLOW}Instalando dependências do sistema...${NC}"
    if [ -f /etc/os-release ]; then
        . /etc/os-release
        case "${ID:-}" in
            arch|manjaro|endeavouros|cachyos)
                sudo pacman -Sy --noconfirm python python-pip tk libnotify
                ;;
            ubuntu|debian|linuxmint|pop|zorin)
                sudo apt-get update && sudo apt-get install -y python3 python3-venv python3-pip python3-tk libnotify-bin
                ;;
            fedora|rhel|nobara)
                sudo dnf install -y python3 python3-pip python3-tkinter libnotify
                ;;
            opensuse*|suse)
                sudo zypper install -y python3 python3-pip python3-tk libnotify-tools
                ;;
            nixos)
                echo -e "${YELLOW}NixOS detectado. Certifique-se de ter python3 no seu ambiente.${NC}"
                ;;
        esac
    fi
}

detect_and_install_deps

# 2. Criar Ambiente Virtual (.venv) e instalar pacotes
echo -e "\n${BLUE}[1/5] Configurando ambiente virtual Python (.venv)...${NC}"
if command -v uv >/dev/null 2>&1; then
    uv venv .venv
    uv pip install -r requirements.txt
else
    python3 -m venv .venv
    .venv/bin/pip install --upgrade pip
    .venv/bin/pip install -r requirements.txt
fi

# 3. Criar .env (se não existir) e popular banco inicial
echo -e "\n${BLUE}[2/5] Configurando banco de dados e arquivo .env...${NC}"
if [ ! -f "$INSTALL_DIR/.env" ]; then
    cp "$INSTALL_DIR/.env.example" "$INSTALL_DIR/.env"
    echo -e "${GREEN}✓${NC} Arquivo .env criado (Notificações direto no PC ativadas por padrão)."
fi
"$INSTALL_DIR/.venv/bin/python" "$INSTALL_DIR/seed.py"

# 4. Instalar Serviço Systemd User (deal-hunter.service)
echo -e "\n${BLUE}[3/5] Configurando serviço em background (systemd --user)...${NC}"
mkdir -p "$HOME/.config/systemd/user"
cat > "$HOME/.config/systemd/user/deal-hunter.service" <<EOF
[Unit]
Description=Deals Hunter - Monitor de Promoções (Desktop & Telegram)
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
WorkingDirectory=$INSTALL_DIR
EnvironmentFile=$INSTALL_DIR/.env
ExecStart=$INSTALL_DIR/.venv/bin/python $INSTALL_DIR/main.py
Restart=always
RestartSec=10
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=default.target
EOF

if command -v systemctl >/dev/null 2>&1; then
    systemctl --user daemon-reload || true
    systemctl --user enable --now deal-hunter.service || true
    echo -e "${GREEN}✓${NC} Serviço deal-hunter.service ativo em background!"
fi

# 5. Instalar Atalho de Aplicativo (.desktop) e System Tray para KDE/GNOME/XFCE
echo -e "\n${BLUE}[4/5] Criando atalhos para Menu de Aplicativos e Bandeja (System Tray)...${NC}"
mkdir -p "$HOME/.local/share/applications"
cat > "$HOME/.local/share/applications/deals-hunter.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=Deals Hunter
Comment=Monitor de Promoções e Painel de Controle
Exec=$INSTALL_DIR/.venv/bin/python $INSTALL_DIR/main.py --gui
Icon=tag
Terminal=false
Categories=Utility;Network;
EOF

mkdir -p "$HOME/.config/autostart"
cat > "$HOME/.config/autostart/deals-hunter-tray.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=Deals Hunter Tray
Comment=Ícone de Bandeja do Deals Hunter
Exec=$INSTALL_DIR/.venv/bin/python $INSTALL_DIR/main.py --tray
Icon=tag
Terminal=false
X-GNOME-Autostart-enabled=true
EOF
echo -e "${GREEN}✓${NC} Atalhos criados para KDE, GNOME, XFCE e Launchers (Rofi/Fuzzel)."

# 6. Detectar Barras / WMs (Noctalia, Waybar)
echo -e "\n${BLUE}[5/5] Detectando barras e ambientes gráficos (Noctalia / Waybar / DEs)...${NC}"

if command -v noctalia >/dev/null 2>&1; then
    echo -e "${GREEN}✓${NC} Barra Noctalia detectada! Instalando plugin nativo..."
    mkdir -p "$HOME/.config/noctalia/plugins/deal-hunter/translations"
    cp "$INSTALL_DIR/integrations/noctalia/catalog.toml" "$HOME/.config/noctalia/plugins/catalog.toml"
    cp -r "$INSTALL_DIR/integrations/noctalia/deal-hunter/"* "$HOME/.config/noctalia/plugins/deal-hunter/"
    sed -i "s|__INSTALL_DIR__|$INSTALL_DIR|g" "$HOME/.config/noctalia/plugins/deal-hunter/service.luau"
    noctalia msg plugins source add local path "$HOME/.config/noctalia/plugins" >/dev/null 2>&1 || true
    noctalia msg plugins enable gappy/deal-hunter >/dev/null 2>&1 || true
    echo -e "${GREEN}✓${NC} Plugin Noctalia 'gappy/deal-hunter' ativado!"
fi

if [ -d "$HOME/.config/waybar" ] || command -v waybar >/dev/null 2>&1; then
    chmod +x "$INSTALL_DIR/integrations/waybar/waybar_module.py"
    sed "s|__INSTALL_DIR__|$INSTALL_DIR|g" "$INSTALL_DIR/integrations/waybar/config.jsonc" > "$INSTALL_DIR/integrations/waybar/waybar-ready.jsonc"
    echo -e "${GREEN}✓${NC} Configuração para Waybar gerada em: integrations/waybar/waybar-ready.jsonc"
fi

echo -e "\n${BLUE}============================================================${NC}"
echo -e "${GREEN}✅ Instalação concluída com sucesso!${NC}"
echo -e "  • Abrir Painel Gráfico:  ${YELLOW}$INSTALL_DIR/.venv/bin/python $INSTALL_DIR/main.py --gui${NC}"
echo -e "  • Iniciar System Tray:   ${YELLOW}$INSTALL_DIR/.venv/bin/python $INSTALL_DIR/main.py --tray${NC}"
echo -e "${BLUE}============================================================${NC}"
