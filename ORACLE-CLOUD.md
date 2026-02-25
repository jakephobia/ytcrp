# Hosting del bot su Oracle Cloud (sempre acceso, gratis)

Guida passo passo per far girare il bot Telegram su una VM Oracle Cloud Free Tier, così funziona 24/7 anche con il PC spento.

---

## Parte 1: Account e VM (da fare nel browser)

### Step 1.1 – Account Oracle Cloud

1. Vai su **[cloud.oracle.com](https://cloud.oracle.com)**.
2. Clicca **Start for free**.
3. Compila il form (email, paese, nome). Serve una **carta di credito** per la verifica; con il piano **Always Free** non ti verranno addebitati costi (le risorse free non scadono).
4. Verifica email e completa la registrazione.

---

### Step 1.2 – Creare una VM (istanza)

1. Dopo il login, dal **menu (≡)** in alto a sinistra vai su **Compute** → **Instances**.
2. Scegli il **compartment** (di solito il tuo root compartment, es. `(root)`).
3. Clicca **Create instance**.

Compila così:

| Campo | Cosa scegliere |
|-------|----------------|
| **Name** | `yt-portrait-bot` (o un nome a piacere) |
| **Placement** | Scegli un **Availability domain** diverso se vedi "Out of capacity" (prova AD-2 o AD-3). Se hai scelto un Fault domain, riprova senza selezionarlo. |
| **Image and shape** | Clicca **Edit** → **Change image** → sezione **Platform images** → **Ubuntu 22.04** (o 24.04). Poi **Change shape** → **Ampere** → seleziona **VM.Standard.A1.Flex** (gratis). Lascia 1 OCPU e 6 GB di RAM (o 2 OCPU e 12 GB se preferisci). Conferma. |
| **Networking** | Lascia “Create new virtual cloud network” e “Assign a public IPv4 address” **attivati**. |
| **Add SSH keys** | **Generate a key pair for me** → scarica la chiave privata (file `.key`) e salvala in un posto sicuro (es. Desktop). **Tieni questo file**: serve per entrare nella VM. |

**Se "Assign a public IPv4 address" è grigio:** torna al passo Networking e, nella sezione della subnet, attiva l’opzione **"Public subnet"** (o "Create public subnet"); solo così il toggle per l’IP pubblico si sblocca.

4. Clicca **Create**. Attendi 1–2 minuti fino a **Running** (icona verde).

---

### Step 1.3 – Aprire la porta SSH nel firewall

1. Nella stessa pagina, sotto **Instance information**, clicca sul **subnet** (link tipo `subnet …`).
2. Nel menu a sinistra clicca **Security Lists** → apri la **Default Security List**.
3. **Add Ingress Rules** e imposta:
   - **Source CIDR**: `0.0.0.0/0`
   - **Destination port range**: `22`
   - **Description**: `SSH`
4. **Add Ingress Rules** e salva.

(Oracle a volte crea già una regola per la porta 22; in quel caso non serve aggiungerla.)

---

### Step 1.4 – Indirizzo IP pubblico

Sulla pagina dell’istanza, in **Primary VNIC**, annota l’**Public IP address** (es. `132.145.xxx.xxx`). Ti servirà per connetterti.

---

## Parte 2: Connettersi alla VM (dal tuo PC)

### Step 2.1 – Utente predefinito

- **Ubuntu**: l’utente è `ubuntu`.
- **Oracle Linux**: di solito è `ubuntu` se hai scelto Ubuntu; altrimenti `opc`.

Useremo `ubuntu` negli esempi; se usi Oracle Linux e l’utente è `opc`, sostituisci `ubuntu` con `opc`.

### Step 2.2 – Permessi al file della chiave SSH

Sul **tuo PC** (PowerShell o terminale):

- **Windows (PowerShell)**:
  ```powershell
  icacls "C:\Users\TUO_USER\Desktop\nome-file.key" /inheritance:r /grant:r "$($env:USERNAME):R"
  ```
  (sostituisci il percorso con dove hai salvato il file `.key`)

- **Mac/Linux**:
  ```bash
  chmod 400 ~/Desktop/nome-file.key
  ```

### Step 2.3 – Connessione SSH

Sostituisci:
- `PERCORSO_CHIAVE` → percorso del file `.key` scaricato
- `132.145.xxx.xxx` → **Public IP** della tua VM
- `ubuntu` → `opc` se stai usando Oracle Linux

**Windows (PowerShell):**
```powershell
ssh -i "PERCORSO_CHIAVE" ubuntu@132.145.xxx.xxx
```

**Mac/Linux:**
```bash
ssh -i PERCORSO_CHIAVE ubuntu@132.145.xxx.xxx
```

Alla prima connessione rispondi `yes` alla domanda sul fingerprint. Se va tutto bene vedrai un prompt tipo `ubuntu@yt-portrait-bot:~$`.

---

## Parte 3: Installare il bot sulla VM

Hai due modi: **caricare i file dal PC** oppure **clonare da GitHub** (se il progetto è in un repo pubblico).

### Opzione A – Caricare i file dal PC (senza GitHub)

Sul **tuo PC**, nella cartella del progetto (dove ci sono `bot.py`, `yt_portrait.py`, `requirements.txt`, `oracle-setup.sh`), apri PowerShell e esegui (sostituisci IP e percorso chiave):

```powershell
scp -i "PERCORSO_CHIAVE" bot.py yt_portrait.py requirements.txt oracle-setup.sh ubuntu@132.145.xxx.xxx:~/
```

Poi sulla **VM** (nella sessione SSH):

```bash
mkdir -p ~/yt-portrait-bot && mv bot.py yt_portrait.py requirements.txt oracle-setup.sh ~/yt-portrait-bot/
cd ~/yt-portrait-bot
chmod +x oracle-setup.sh
```

### Opzione B – Clonare da GitHub

Sulla **VM** (in SSH):

```bash
sudo apt-get update && sudo apt-get install -y git
git clone https://github.com/TUO_USER/TUO_REPO.git yt-portrait-bot
cd yt-portrait-bot
chmod +x oracle-setup.sh
```

(Sostituisci `TUO_USER` e `TUO_REPO` con il tuo utente e nome repo; se il repo è privato dovrai usare un token o SSH key.)

---

## Parte 4: Token e avvio

### Step 4.1 – Creare `token.txt`

Sulla VM, nella cartella del bot (es. `~/yt-portrait-bot`):

```bash
nano token.txt
```

- Incolla **solo** il token del bot (quello che ti ha dato @BotFather), una riga, niente spazi.
- Salva: **Ctrl+O**, Invio, poi esci: **Ctrl+X**.

### Step 4.2 – Eseguire lo script di setup

Sempre nella stessa cartella:

```bash
./oracle-setup.sh
```

Lo script:
- installa Python, ffmpeg e le dipendenze;
- crea l’ambiente virtuale e installa i pacchetti Python;
- configura un servizio systemd che avvia il bot al boot e lo riavvia se si chiude.

Se vedi **“Setup completato. Il bot è in esecuzione.”** il bot è attivo.

### Step 4.3 – Verificare

```bash
systemctl --user status yt-portrait-bot
```

Dovresti vedere `active (running)`. Per vedere i log in tempo reale:

```bash
journalctl --user -u yt-portrait-bot -f
```

(Esci con **Ctrl+C**.)

Apri Telegram e scrivi al bot: se risponde, è tutto a posto.

---

## Comandi utili (sulla VM)

| Azione | Comando |
|--------|--------|
| Stato del bot | `systemctl --user status yt-portrait-bot` |
| Log in tempo reale | `journalctl --user -u yt-portrait-bot -f` |
| Riavviare il bot | `systemctl --user restart yt-portrait-bot` |
| Fermare il bot | `systemctl --user stop yt-portrait-bot` |
| Cambiare il token | Modifica `token.txt`, poi `systemctl --user restart yt-portrait-bot` |

---

## Riepilogo veloce

1. **Oracle Cloud**: account → Create instance → Ubuntu 22.04, shape A1.Flex, scarica chiave SSH.
2. **Rete**: verifica che la porta 22 sia aperta (Security List).
3. **PC**: connetti con `ssh -i chiave.key ubuntu@IP`.
4. **VM**: carica i file (scp) o fai `git clone` → `cd` nella cartella del bot.
5. **VM**: `nano token.txt` (incolla token) → `./oracle-setup.sh`.
6. Controllo: `systemctl --user status yt-portrait-bot` e prova il bot su Telegram.

Da questo momento il bot resta attivo 24/7 anche con il tuo PC spento.
