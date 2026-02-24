# YouTube → Portrait

Tool web: incolla un link YouTube, scarica il video ritagliato in formato portrait 9:16 con zoom regolabile (0–30%).

- **Tecnologie:** Flask, yt-dlp, ffmpeg
- **Deploy:** Docker (es. Render) — vedi sotto

## Deploy su Render

1. Collega questo repository a [Render](https://render.com) (New → Web Service).
2. Lascia **Docker** come runtime (rileva il `Dockerfile`).
3. Piano **Free**.
4. Dopo il deploy avrai un URL da salvare nei preferiti (es. `https://ytcrp-xxxx.onrender.com`).

## Esecuzione in locale

```bash
pip install -r requirements.txt
# Serve ffmpeg e yt-dlp (pip da requirements) in PATH
python app.py
```

Apri http://localhost:5000

## File principali

- `app.py` — backend Flask (download, crop, anteprima)
- `index.html` — pagina principale
- `css/main.css` — stili
- `js/app.js` — logica frontend
- `Dockerfile` — immagine per Render (Python + ffmpeg)
- `render.yaml` — config deploy Render
