#!/bin/bash
# Setup bot YouTube → Portrait su VM Oracle Cloud (Ubuntu o Oracle Linux)
# Esegui dalla cartella del progetto (dove ci sono bot.py, yt_portrait.py, requirements.txt)
set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo "=== Setup bot YouTube → Portrait su Oracle Cloud ==="

# Controllo di essere nella cartella giusta
if [ ! -f "bot.py" ] || [ ! -f "yt_portrait.py" ] || [ ! -f "requirements.txt" ]; then
  echo -e "${RED}Esegui questo script dalla cartella del progetto (dove ci sono bot.py, yt_portrait.py, requirements.txt).${NC}"
  exit 1
fi

BOT_DIR="$(realpath .)"
echo "Cartella progetto: $BOT_DIR"

# Rileva OS e installa dipendenze di sistema
if command -v apt-get &>/dev/null; then
  echo "Rilevato: Debian/Ubuntu. Installazione dipendenze..."
  sudo apt-get update -qq
  sudo apt-get install -y -qq python3 python3-pip python3-venv ffmpeg
elif command -v dnf &>/dev/null; then
  echo "Rilevato: Oracle Linux / RHEL / Fedora. Installazione dipendenze..."
  sudo dnf install -y python3 python3-pip python3-venv ffmpeg
elif command -v yum &>/dev/null; then
  echo "Rilevato: Oracle Linux / RHEL (yum). Installazione dipendenze..."
  sudo yum install -y python3 python3-pip ffmpeg
  # Su alcune distro yum non ha python3-venv: creiamo venv con pip
else
  echo -e "${RED}Sistema non supportato. Usa Ubuntu o Oracle Linux.${NC}"
  exit 1
fi

# Venv e pip (se venv non disponibile, usa pip --user)
echo "Installazione pacchetti Python..."
if python3 -m venv venv 2>/dev/null; then
  "$BOT_DIR/venv/bin/pip" install -q --upgrade pip
  "$BOT_DIR/venv/bin/pip" install -q -r requirements.txt
  PYTHON_BIN="$BOT_DIR/venv/bin/python"
else
  python3 -m pip install -q --user --upgrade pip
  python3 -m pip install -q --user -r requirements.txt
  PYTHON_BIN="$(which python3)"
fi

# Token: deve esistere token.txt
if [ ! -f "token.txt" ]; then
  echo ""
  echo -e "${YELLOW}Manca token.txt.${NC}"
  echo "Crea il file con il token del bot (da @BotFather):"
  echo "  nano token.txt"
  echo "  (incolla il token, salva con Ctrl+O e esci con Ctrl+X)"
  echo "Poi riesegui: ./oracle-setup.sh"
  exit 1
fi

TOKEN="$(cat token.txt | tr -d '\n\r' | head -1)"
if [ -z "$TOKEN" ] || [ "$TOKEN" = "INSERISCI_QUI_IL_TOKEN" ]; then
  echo -e "${RED}token.txt è vuoto o contiene il placeholder. Inserisci il token da @BotFather.${NC}"
  exit 1
fi

# File .env per systemd (KEY=value)
echo "TELEGRAM_BOT_TOKEN=$TOKEN" > "$BOT_DIR/.env.bot"
chmod 600 "$BOT_DIR/.env.bot"

# Systemd user service (così il bot riparte al reboot e non serve root)
mkdir -p "$HOME/.config/systemd/user"
SVC="$HOME/.config/systemd/user/yt-portrait-bot.service"
cat > "$SVC" << EOF
[Unit]
Description=Bot Telegram YouTube → Portrait
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
WorkingDirectory=$BOT_DIR
EnvironmentFile=$BOT_DIR/.env.bot
ExecStart=$PYTHON_BIN bot.py
Restart=always
RestartSec=10

[Install]
WantedBy=default.target
EOF

# Abilita il servizio utente anche senza login (linger)
systemctl --user daemon-reload
systemctl --user enable yt-portrait-bot.service
loginctl enable-linger "$USER" 2>/dev/null || true
systemctl --user start yt-portrait-bot.service

echo ""
echo -e "${GREEN}Setup completato. Il bot è in esecuzione.${NC}"
echo ""
echo "Comandi utili:"
echo "  Stato:    systemctl --user status yt-portrait-bot"
echo "  Log:      journalctl --user -u yt-portrait-bot -f"
echo "  Riavvia:  systemctl --user restart yt-portrait-bot"
echo "  Stop:     systemctl --user stop yt-portrait-bot"
echo ""
