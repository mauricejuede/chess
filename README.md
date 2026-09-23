# Patzer-Training

Macht aus deinen eigenen chess.com-Partien Schach-Puzzles. Jede Stellung ist ein grober Fehler, den du tatsächlich gespielt hast. Du siehst die Stellung vor dem Fehler und suchst den richtigen Zug. Danach kannst du die beste Fortsetzung, die Widerlegung deines Partiezugs und die ganze Partie durchspielen.

Eine GitHub Action lädt jeden Tag deine neuen Partien über die chess.com-API, analysiert sie mit Stockfish und veröffentlicht die Seite über GitHub Pages.

## Einrichten

1. Neues Repository auf GitHub erstellen, z. B. `patzer-training` (öffentlich, sonst braucht GitHub Pages ein kostenpflichtiges Konto).
2. Den Inhalt dieses Ordners hochladen:
   ```bash
   git init
   git add .
   git commit -m "Erste Version"
   git branch -M main
   git remote add origin https://github.com/DEIN-GITHUB-NAME/patzer-training.git
   git push -u origin main
   ```
   Wichtig ist, dass der versteckte Ordner `.github` mit hochgeladen wird. Beim Hochladen per Drag & Drop im Browser fehlt er oft.
3. Im Repository unter **Settings → Pages** bei „Source“ **GitHub Actions** auswählen.
4. Unter **Settings → Actions → General** ganz unten bei „Workflow permissions“ **Read and write permissions** wählen und speichern.
5. Unter **Actions → Puzzles aktualisieren → Run workflow** den ersten Lauf starten. Der erste Lauf dauert einige Minuten, spätere Läufe analysieren nur neue Partien.
6. Die Seite ist danach unter `https://DEIN-GITHUB-NAME.github.io/patzer-training/` erreichbar.

Ab dann läuft die Aktualisierung jeden Tag um 04:00 UTC automatisch. Für sofortige Aktualisierung einfach Schritt 5 wiederholen.

## Einstellungen (`config.json`)

| Feld | Bedeutung |
|---|---|
| `username` | chess.com-Benutzername |
| `time_classes` | welche Partien analysiert werden: `bullet`, `blitz`, `rapid`, `daily` |
| `rated_only` | nur gewertete Partien |
| `months` | wie viele Monate zurück Partien geladen werden |
| `max_games` | Höchstzahl Partien pro Lauf |
| `blunder_cp` | ab wie viel Materialverlust (in Hundertstel-Bauern) ein Zug als Patzer gilt |
| `scan_depth`, `puzzle_depth` | Rechentiefe von Stockfish |

## Lokal ausführen

```bash
pip install chess
# Stockfish installieren (macOS: brew install stockfish, Linux: apt install stockfish)
python scripts/build_puzzles.py                      # über die chess.com-API
python scripts/build_puzzles.py --pgn partien.pgn    # oder mit einer heruntergeladenen PGN-Datei
cd docs && python -m http.server 8000                # dann http://localhost:8000 öffnen
```

## Aufbau

- `scripts/build_puzzles.py`: lädt die Partien, findet Patzer mit Stockfish, schreibt `docs/puzzles.json`
- `data/cache.json`: bereits analysierte Partien, damit nichts doppelt gerechnet wird
- `docs/`: die Webseite (reines HTML/JS, kein Build nötig)
- `.github/workflows/update.yml`: tägliche Aktualisierung und Veröffentlichung

## Lizenzen

- Figuren: cburnett, CC BY-SA 3.0
- chess.js: BSD-2-Clause, © Jeff Hlywa
- Stockfish (GPLv3) wird nur während der Analyse installiert und ist nicht Teil dieses Repositorys.
