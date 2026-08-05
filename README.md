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
- **Automatische Fallback-Logik ändern** (nur relevant für Wochen ohne
  Eintrag in `training_plan.json`): Funktionen `getPhase`, `getLongRunKm`
  und `DAY_TEMPLATES` in `docs/index.html`.
- **Sync-Häufigkeit ändern**: `cron`-Zeile in
  `.github/workflows/sync.yml` (z. B. `*/30 * * * *` für alle 30 Minuten).

## Echter Trainingsplan (`docs/training_plan.json`)

Enthält deinen vollständigen 17-Wochen-Plan (Sub-4h-Marathon, herzfrequenz-
basiert), eine Woche pro Eintrag, Schlüssel = Montagsdatum. Für die aktuelle
Woche zeigt das Dashboard automatisch die hier hinterlegten Tage an; Klick
auf einen Tag öffnet die Details (Zielbereich, Umfang, Hinweise). Wochen
ohne Eintrag fallen automatisch auf die generische Phasenlogik zurück — du
kannst also jederzeit weitere reale Wochen ergänzen oder bestehende direkt
im GitHub-Web-Editor anpassen, ohne Code zu berühren.

Format pro Tag:
```json
"Sa": { "title": "Long Run 22 km, B2", "type": "long", "details": "…" }
```
`type` steuert nur die Farbe: `rest`, `easy`, `hard`, `long`, `race`.

## Farblogik bei Wellness-Ringen

- **Body Battery, Schlaf, Bereitschaft**: höher = besser (grün ab ~70%).
- **Stress**: umgekehrt — niedrig = grün/gut, hoch = rot/schlecht (Garmin-Skala
  0-100, 0 = Ruhe).
- **HRV**: kein simpler Schwellenwert. Genutzt wird Garmins eigener,
  personalisierter Status (`hrv_status`: Ausgeglichen/Unausgeglichen/Niedrig)
  bzw. ersatzweise die persönliche Baseline-Range (`hrv_baseline_low/high`).
  Ohne diese Felder (z. B. bei älteren `data.json`-Ständen vor diesem Update)
  bleibt der Ring neutral grau, bis der nächste Sync sie liefert.

## Aktivitäts-Details & Auswertung

- Klick auf eine Aktivität in der Liste öffnet Splits, Höhenmeter und
  Pulszonen (sofern Garmin diese Daten für die Aktivität liefert — nicht
  jedes Gerät/jede Aktivität hat Splits oder Pulszonen-Daten).
- Die Kurzauswertung unter "Diese Woche" basiert weiterhin auf **regelbasiert
  berechneten Kennzahlen** (Pace-/HF-Drift 1. vs. 2. Hälfte, Split-Streuung,
  Zonenzeit-Verteilung — `compute_pacing_facts()` in `scripts/garmin_sync.py`).
  Diese Kennzahlen laufen immer, unabhängig von einem API-Key.
- **Optional** wird daraus zusätzlich ein kurzer Kommentar von **Claude Haiku
  4.5** erzeugt (`generate_ai_assessment()`), wenn der GitHub-Actions-Secret
  `ANTHROPIC_API_KEY` gesetzt ist. Wichtig: das passiert **nicht bei jedem
  stündlichen Sync**, sondern nur, wenn seit dem letzten Mal eine neue
  Aktivität dazugekommen ist (Dedupe über die Activity-ID). Bei 3–4
  Läufen/Woche sind das 3–4 API-Calls/Woche — Kosten liegen im Bereich weniger
  Cent pro Monat. Ohne den Secret läuft alles wie zuvor, nur ohne KI-Kommentar
  (Frontend fällt automatisch auf die regelbasierte Textvariante in
  `renderAssessment()`, `docs/index.html`, zurück).
- **Secret einrichten (optional):** Repo → *Settings* → *Secrets and
  variables* → *Actions* → *New repository secret* → Name
  `ANTHROPIC_API_KEY`, Wert dein Anthropic-API-Key von
  [console.anthropic.com](https://console.anthropic.com). Der Key landet nur
  im Actions-Secret, nie im öffentlichen `docs/`-Code.
