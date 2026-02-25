# YouTube → Portrait

Scarica video da YouTube e ritagliali in formato **portrait 9:16** con zoom regolabile (0–30%).

- **Tecnologie:** yt-dlp, ffmpeg
- **Interfacce:** bot Telegram (consigliato) o web Flask

---

## Bot Telegram (consigliato)

Invii il link al bot → scegli lo zoom → **vedi l’anteprima** → confermi e scarichi il video in portrait 9:16.

### Avvio standalone (senza terminale)

1. Installa Python e ffmpeg, poi nella cartella del progetto:
   ```bash
   pip install -r requirements.txt
   ```
2. Crea il file **token.txt** nella stessa cartella e incolla dentro il token del bot (da [@BotFather](https://t.me/BotFather)). Puoi copiare `token.txt.example` e rinominarlo.
3. **Doppio clic su `Avvia bot.bat`**: il bot parte in background (nessuna finestra). Puoi chiudere tutto e usarlo dal cellulare; resta attivo finché non spegni il PC.

### Avvio da terminale

```bash
pip install -r requirements.txt
set TELEGRAM_BOT_TOKEN=il_tuo_token
python bot.py
```

### Hosting 24/7 (bot sempre attivo, senza PC)

Puoi hostare il bot in cloud così resta online anche a PC spento. Due opzioni semplici:

#### Opzione A: Railway (consigliata)

1. Vai su [railway.app](https://railway.app), accedi con GitHub.
2. **New Project** → **Deploy from GitHub repo** → scegli questo repository (o fai fork e connetti il fork).
3. Railway rileva il Dockerfile: va bene, ma per il **bot** usa il file dedicato. Nella dashboard del servizio:
   - **Settings** → **Build** → **Dockerfile Path** → imposta `Dockerfile.bot`.
   - **Settings** → **Variables** → aggiungi `TELEGRAM_BOT_TOKEN` = il tuo token (da @BotFather).
4. **Deploy**: il bot parte e resta attivo. Costo: circa 5 €/mese di credito gratuito; oltre si paga a consumo (pochi cent per un bot leggero).

#### Opzione B: Fly.io

1. Installa [flyctl](https://fly.io/docs/hands-on/install-flyctl/) e fai `fly auth login`.
2. Nella cartella del progetto crea l’app (una sola volta):
   ```bash
   fly launch --no-deploy --name yt-portrait-bot
   ```
   Quando chiede il Dockerfile, indica `Dockerfile.bot`. Rispondi No a “Would you like to set up a PostgreSQL database”.
3. Imposta il token:
   ```bash
   fly secrets set TELEGRAM_BOT_TOKEN=il_tuo_token
   ```
4. Deploy:
   ```bash
   fly deploy
   ```
5. Il bot gira 24/7. Fly.io ha un [piano free](https://fly.io/docs/about/pricing/) con limiti; per uso normale il bot resta nei limiti gratuiti.

#### Opzione C: Oracle Cloud (100% gratuito, sempre acceso)

Guida passo passo in **[ORACLE-CLOUD.md](ORACLE-CLOUD.md)**. In sintesi: crei un account Oracle Cloud Free Tier, una VM Ubuntu, ti connetti in SSH, carichi i file del bot, esegui lo script `oracle-setup.sh` e il bot parte in automatico (e si riavvia a ogni reboot).

### Utilizzo

- Invia un link YouTube (video o Shorts) → scegli zoom (0%, 7%, 15%, 30%) → compare **l’anteprima** → **Conferma e scarica** oppure **Cambia zoom**.
- Oppure: `/download <link> [zoom]` per scaricare subito senza anteprima.

**Comandi:** `/start` — istruzioni | `/download <link> [0-30]` — download diretto.

**Video "non disponibile nel tuo paese":** Su Railway/Fly.io il download usa l’IP del server (es. USA). Per video solo in Italia: imposta la variabile **`YT_PROXY`** con un proxy a uscita italiana (vedi ALTERNATIVE-HOSTING.md), oppure usa il bot in **locale** (da casa tua l’IP è italiano).

---

## Web (Flask)

```bash
pip install -r requirements.txt
python app.py
```

Apri http://localhost:5000

### Deploy su Render

1. Collega il repository a [Render](https://render.com) (New → Web Service).
2. Runtime **Docker**, piano Free.
3. URL tipo `https://ytcrp-xxxx.onrender.com`.

---

## File principali

- `bot.py` — bot Telegram (entry point consigliato)
- `yt_portrait.py` — logica download + crop (condivisa)
- `app.py` — backend Flask (download, crop, anteprima)
- `index.html`, `css/`, `js/` — interfaccia web
- `Dockerfile`, `render.yaml` — deploy Render
