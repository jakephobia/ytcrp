# Alternative a Oracle: hostare il bot in 5 minuti

Se Oracle dà “Out of capacity” o problemi, usa **Railway** o **Fly.io**. Il bot resta online 24/7 senza il tuo PC.

---

## Opzione 1: Railway (la più semplice)

Niente SSH, niente VM: colleghi GitHub e aggiungi il token. Tempo: ~5 minuti.

### Cosa ti serve
- Account **GitHub** (gratis)
- Il progetto su GitHub (se non c’è ancora: crea un repo, carica i file e push)
- Token del bot da @BotFather

### Passi

1. **Metti il progetto su GitHub** (se non l’hai già)
   - Vai su [github.com](https://github.com) → **New repository** (es. nome `yt-portrait-bot`).
   - Carica nella root del repo almeno: `bot.py`, `yt_portrait.py`, `requirements.txt`, `Dockerfile.bot` (e opzionale `README.md`).
   - Oppure da PC: nella cartella del progetto apri terminale e:
     ```bash
     git init
     git add bot.py yt_portrait.py requirements.txt Dockerfile.bot
     git commit -m "Bot Telegram"
     git remote add origin https://github.com/TUO_USER/TUO_REPO.git
     git push -u origin main
     ```
     (sostituisci TUO_USER e TUO_REPO)

2. **Vai su [railway.app](https://railway.app)** e accedi con **GitHub**.

3. **New Project** → **Deploy from GitHub repo** → autorizza Railway e scegli il repository del bot.

4. Railway crea un servizio. Nella **dashboard del servizio**:
   - **Settings** (icona ingranaggio) → **Build** → nel campo **Dockerfile Path** scrivi: `Dockerfile.bot` → salva.
   - **Variables** → **Add variable** → nome `TELEGRAM_BOT_TOKEN`, valore = il token (incolla quello di @BotFather) → salva.

5. **Deploy**: se non parte da solo, clicca **Deploy** / **Redeploy**. Attendi che lo stato sia “Success” o “Running”.

6. Controlla su Telegram: scrivi al bot; se risponde, è online 24/7.

**Costo:** Railway dà circa **5 $ di credito gratis al mese**. Un bot che risponde e fa qualche download al giorno di solito resta dentro il free tier; oltre si paga a consumo (pochi centesimi).

**Video "non disponibile nel tuo paese":** Il download avviene dai server Railway (es. USA). Il bot **prova in automatico** un proxy italiano gratuito (da Free Proxy DB) quando rileva questo errore; spesso funziona, ma i proxy gratuiti sono instabili. Se non basta: imposta **`YT_PROXY`** con un proxy a pagamento a uscita italiana (Variables → `YT_PROXY` = `http://...`). Oppure usa il bot **in locale** (`Avvia bot.bat`): da casa tua l’IP è italiano.

**Se il bot si blocca su "Ritaglio e invio in corso":** su Railway il container ha poca RAM. Prova con **video brevi** (es. sotto 2–3 minuti). Se serve, nella dashboard del servizio aumenta la **memoria** (Settings → Resources). Controlla i **log** (Deployments → View logs) per vedere se c’è timeout o errore ffmpeg.

---

## Opzione 2: Fly.io (da terminale)

Se preferisci non usare GitHub o vuoi deploy da PC:

1. Installa **flyctl**: [fly.io/docs/hands-on/install-flyctl](https://fly.io/docs/hands-on/install-flyctl/) (Windows: `powershell -Command "iwr https://fly.io/install.ps1 -useb | iex"`).
2. Login: `fly auth login` (si apre il browser).
3. Nella **cartella del progetto** (dove c’è `Dockerfile.bot`):
   ```bash
   fly launch --no-deploy --name yt-portrait-bot
   ```
   - Se chiede “Dockerfile?”, scegli quello che indica `Dockerfile.bot` o scrivi `Dockerfile.bot`.
   - Database: **No**.
4. Imposta il token:
   ```bash
   fly secrets set TELEGRAM_BOT_TOKEN=il_tuo_token
   ```
5. Avvia:
   ```bash
   fly deploy
   ```
6. Il bot è online. Per vedere i log: `fly logs`.

**Costo:** Fly.io ha un [piano free](https://fly.io/docs/about/pricing/) con limiti; per un bot leggero spesso basta.

---

## Riepilogo

| Servizio   | Difficoltà | Gratis / costo        |
|-----------|------------|------------------------|
| **Railway** | ⭐ Facile   | ~5 $/mese credito, poi a consumo |
| **Fly.io**  | ⭐⭐ Media  | Piano free con limiti  |
| Oracle     | ⭐⭐⭐ Alta  | 100% gratis ma spesso “Out of capacity” |

Consiglio: inizia con **Railway** (opzione 1). Se il progetto è già su GitHub sono davvero pochi clic.
