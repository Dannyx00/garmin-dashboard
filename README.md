# Garmin Dashboard (eigenständig, ohne Claude)

Ein Dashboard mit deinen Garmin-Daten (Wellness, letzte Aktivitäten) plus
Marathon-Countdown und wöchentlichem Trainingsplan. Die Seite läuft komplett
eigenständig über GitHub Pages; ein GitHub-Actions-Job synct stündlich im
Hintergrund mit Garmin Connect. Kein Anthropic-API-Key, keine Claude-Tokens
im laufenden Betrieb.

## Funktionsweise

```
GitHub Actions (stündlich) --> scripts/garmin_sync.py --> docs/data.json
                                                                 |
                                          GitHub Pages liefert docs/ aus
                                                                 |
                                        docs/index.html liest data.json
```

## Einrichtung (einmalig, ca. 5 Minuten)

1. **Neues Repository auf GitHub anlegen** (z. B. `garmin-dashboard`) und
   diesen kompletten Ordner hochladen — Ordnerstruktur unbedingt beibehalten
   (`.github/workflows/sync.yml`, `scripts/garmin_sync.py`, `docs/index.html` …).

2. **Zugangsdaten als Secrets hinterlegen**
   Repo → *Settings* → *Secrets and variables* → *Actions* → *New repository secret*
   - `GARMIN_EMAIL` — deine Garmin-Connect-E-Mail
   - `GARMIN_PASSWORD` — dein Garmin-Connect-Passwort

3. **GitHub Pages aktivieren**
   Repo → *Settings* → *Pages* → *Source*: „Deploy from a branch“ →
   Branch `main`, Ordner `/docs` → *Save*.
   GitHub zeigt dir danach die URL an, z. B.
   `https://DEIN-NUTZERNAME.github.io/garmin-dashboard/`

4. **Ersten Sync manuell anstoßen**
   Repo → Tab *Actions* → Workflow „Garmin Sync“ auswählen →
   *Run workflow*. Nach ca. 1–2 Minuten ist `docs/data.json` befüllt.

5. **Dashboard öffnen**
   Die URL aus Schritt 3 aufrufen — das ist deine dauerhafte Live-Adresse.
   Diese kannst du dir als Browser-Lesezeichen speichern oder (Handy) über
   „Zum Startbildschirm hinzufügen“ als App-Icon ablegen.

Ab jetzt synct die Action automatisch jede volle Stunde. Du kannst die
Frequenz in `.github/workflows/sync.yml` über die `cron`-Zeile anpassen.

## Wenn der Sync mal fehlschlägt

Garmin verlangt bei Logins von neuen/unbekannten Servern (wie den
GitHub-Actions-Maschinen) gelegentlich eine Verifizierung per E-Mail-Code.
In dem Fall schlägt der Job im *Actions*-Tab rot fehl. Meist reicht es, sich
einmal ganz normal im Browser bei Garmin Connect einzuloggen und eine
eventuelle Sicherheitsabfrage zu bestätigen — danach läuft der automatische
Sync wieder.

## Anpassen

- **Marathon-Datum ändern**: in `docs/index.html` die Zeile
  `const RACE_DATE = new Date("2026-11-01T23:59:59");` anpassen.
- **Trainingsplan-Logik ändern**: Funktionen `getPhase`, `getLongRunKm` und
  `DAY_TEMPLATES` in `docs/index.html` — läuft komplett im Browser, kein
  Server nötig.
- **Sync-Häufigkeit ändern**: `cron`-Zeile in
  `.github/workflows/sync.yml` (z. B. `*/30 * * * *` für alle 30 Minuten).
