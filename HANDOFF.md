# Projekt-Übergabe: Garmin Marathon Dashboard

Diese Datei ist für eine neue Claude-Konversation gedacht, damit sie ohne
Rückfragen nahtlos an diesem Projekt weiterarbeiten kann. Lade sie zusammen
mit dem beigefügten `garmin-dashboard.zip` (aktueller Datei-Stand) in den
neuen Chat hoch und schreib z. B.: *"Hier ist die Übergabe eines laufenden
Projekts, lies dir das durch und arbeite danach mit mir weiter."*

---

## 1. Worum es geht

Ein persönliches, eigenständig laufendes **Garmin-Trainings-Dashboard** für
Daniel (Ziel: Marathon Sub-4 Stunden, Rennen am **1. November 2026**,
herzfrequenzbasiertes Training mit Garmin Forerunner 265 + Polar H10, 3–4
Einheiten/Woche). Läuft komplett ohne Claude/Anthropic-API im laufenden
Betrieb — bewusst so gebaut, dass keine Tokens verbraucht werden und die
Seite auch offline von der Konversation aus funktioniert.

**Wichtig:** Es gibt einen bereits eingerichteten, laufenden GitHub-Repo bei
Daniel (Name/Owner ist Claude nicht bekannt — der neue Chat sollte danach
fragen oder Daniel sollte die Repo-URL mitteilen). Secrets (`GARMIN_EMAIL`,
`GARMIN_PASSWORD`) sind dort bereits hinterlegt, GitHub Pages ist aktiv,
der stündliche Sync läuft.

## 2. Architektur

```
GitHub Actions (stündlich, Minute 17)
  -> scripts/garmin_sync.py  (nutzt die inoffizielle "garminconnect"-Bibliothek)
  -> schreibt docs/data.json
       |
GitHub Pages liefert docs/ öffentlich aus
       |
docs/index.html liest data.json + training_plan.json per fetch()
  (kein API-Key, keine Claude-Tokens im Betrieb)
```

## 3. Dateistruktur (siehe Zip)

- `docs/index.html` — das Dashboard selbst. Dark Mode, Outfit/Inter/
  JetBrains-Mono-Typografie, Ring-Gauges für Wellness, klickbare
  Tages-Kacheln & Aktivitäts-Karten mit Modal-Detailansicht,
  Wochen-Navigation mit Swipe-Animation, regelbasierte Kurzauswertung.
- `docs/data.json` — vom Sync-Job erzeugte Live-Daten (Wellness, letzte
  Aktivitäten inkl. Splits/Höhenmeter/Pulszonen für die neuesten 5).
- `docs/training_plan.json` — Daniels **echter** 17-Wochen-Trainingsplan
  (Sub-4h-Marathon), Schlüssel = Montagsdatum jeder Woche, beginnend
  `2026-07-06`. Für Wochen ohne Eintrag gibt es einen automatischen
  Fallback-Plan (generische Phasenlogik nach Wochen-bis-Rennen).
- `docs/favicon.svg`, `favicon-32.png`, `apple-touch-icon.png`,
  `icon-512.png` — Icon-Set (indigo/dunkel, Puls-Symbol), für Browser-Tab
  und Homescreen-Shortcut.
- `scripts/garmin_sync.py` — Login bei Garmin Connect via `garminconnect`,
  liest Wellness (Body Battery, Schlaf, HRV inkl. Garmin-Status/Baseline,
  Stress, Trainingsbereitschaft) und Aktivitäten inkl. Splits/Pulszonen/
  Höhenmeter für die letzten 5, schreibt `docs/data.json`.
- `.github/workflows/sync.yml` — Cron `17 * * * *` (bewusst nicht Minute 0,
  da GitHub Scheduled-Runs zur vollen Stunde häufiger verzögert/verworfen
  werden) + `workflow_dispatch` für manuelles Auslösen.
- `requirements.txt` — nur `garminconnect`.
- `README.md` — vollständige Setup- und Anpassungs-Doku, bereits aktuell.

## 4. Bereits gebaute Features (fertig, funktionierend)

1. Live-Sync via GitHub Actions, stündlich.
2. Marathon-Countdown (immer echtes "heute", unabhängig von Wochen-Navigation).
3. Wochenkarte mit Daniels echtem Trainingsplan, Fallback-Logik für nicht
   erfasste Wochen.
4. Klickbare Tages-Kacheln → Modal mit Session-Details.
5. Klickbare Aktivitäts-Karten → Modal mit Splits, Höhenmeter, Pulszonen.
6. Regelbasierte Kurzauswertung des letzten Trainings (**explizit keine
   KI-Analyse** — deterministische Schwellenwert-Logik in
   `renderAssessment()`).
7. Wochen-Navigation (Pfeile links/rechts) mit Swipe-Animation, "Zur
   aktuellen Woche"-Reset-Button.
8. Eigenes Favicon/App-Icon.
9. Timezone-Bug gefixt (Datumsschlüssel-Berechnung nutzte vorher
   `toISOString()`, das bei UTC+2 den falschen Tag lieferte).
10. Cron-Minute von `0` auf `17` verschoben (GitHub verwirft/verzögert
    Scheduled-Runs zur vollen Stunde häufiger).
11. **Gerade fertiggestellt:** durchgängige, konsistente Hover-/Klick-
    Animationen (globale `--ease`/`--dur`-Tokens), animiertes Modal-Öffnen/
    -Schließen (Fade+Scale statt hartem Umschalten), Ring-Gauges zeichnen
    sich beim Laden animiert ein, HR-Balken bei Aktivitäten füllt sich
    animiert, Eintritts-Stagger für Karten/Kacheln.
12. **Gerade fertiggestellt:** korrigierte Farblogik bei den Wellness-Ringen:
    - Body Battery/Schlaf/Bereitschaft: höher = besser (wie vorher).
    - **Stress: umgekehrt** — niedrig = grün/gut, hoch = rot/schlecht.
    - **HRV**: kein simpler Schwellenwert mehr, sondern Garmins eigener
      Status (`hrv_status`: BALANCED/UNBALANCED/LOW) bzw. ersatzweise seine
      persönliche Baseline-Range (`hrv_baseline_low/high`). Diese Felder
      liefert `garmin_sync.py` seit diesem Update mit; ohne sie (alte
      `data.json`) bleibt der Ring neutral grau statt falsch eingefärbt.

## 5. Bewusste Design-/Sicherheitsentscheidungen (bitte nicht rückgängig machen, ohne zu fragen)

- **Kein Live-Trigger-Button auf der Webseite selbst.** Wurde explizit
  geprüft und von Daniel abgelehnt, weil dafür ein GitHub-Token im
  öffentlichen Seiten-Code liegen müsste. Sync bleibt rein
  zeitgesteuert/manuell über den GitHub-Actions-Tab.
- **Update (05.08.2026): Kurzauswertung ist jetzt hybrid.** Die Kennzahlen
  (Pace-/HF-Drift 1. vs. 2. Hälfte, Split-Streuung, Zonenzeit) werden weiterhin
  komplett regelbasiert berechnet, `scripts/garmin_sync.py:compute_pacing_facts()`.
  Optional (nur wenn Secret `ANTHROPIC_API_KEY` gesetzt ist) wird daraus
  zusätzlich ein 2–3-Satz-Kommentar von **Claude Haiku 4.5** erzeugt
  (`generate_ai_assessment()`), aber NUR serverseitig im stündlichen
  GitHub-Actions-Job und NUR bei einer neuen Aktivität (Dedupe über
  Activity-ID) — nicht bei jedem Sync-Lauf und nicht im Browser. Kosten:
  ~3–4 Calls/Woche, ca. 3–4 Cent/Monat. Ohne den Secret läuft alles exakt wie
  vorher (regelbasierter Text, kein API-Call, `$0`). Das war Daniels bewusste
  Entscheidung, die alte "kein-KI"-Regel zu lockern — die Grundausrichtung
  ("kein Live-Betrieb ohne API-Key nötig") bleibt aber erhalten.
- **`training_plan.json` ist die Quelle der Wahrheit**, sobald ein Eintrag
  für eine Woche existiert; die generische Phasenlogik (`getPhase`,
  `getLongRunKm`, `DAY_TEMPLATES` in `index.html`) ist nur Fallback für
  nicht erfasste Wochen (z. B. weit in der Zukunft nach Woche 17).

## 6. Offene Punkte / mögliche nächste Schritte

- Nichts akut Offenes — der letzte Auftrag (Animationen + Farblogik
  HRV/Stress) ist fertig und in diesem Zip-Stand enthalten.
- Falls Daniel weitere Wochen seines Plans nachträgt: einfach neue
  Einträge nach demselben Schema in `docs/training_plan.json` ergänzen
  (Schlüssel = Montagsdatum, Format siehe bestehende Einträge).
- `garmin_sync.py`s HRV-Feldnamen (`hrvSummary.status`,
  `hrvSummary.baseline.balancedLow/balancedUpper`) sind auf Basis der
  inoffiziellen `garminconnect`-Bibliothek geschätzt/dokumentiert, aber
  **nicht live gegen Daniels echtes Konto verifiziert** — falls die Ringe
  nach dem nächsten Sync weiterhin grau bleiben (statt farbig), zuerst
  `docs/data.json` nach dem Sync inspizieren, ob `hrv_status`/
  `hrv_baseline_*` tatsächlich befüllt werden, und die Feldnamen im
  Skript ggf. an die reale API-Antwort anpassen.

## 7. Wie Daniel bisher immer vorgeht, um Änderungen einzuspielen

Kein automatisches Deployment von hier aus möglich (kein GitHub-Zugriff
für Claude). Ablauf bisher immer:
1. Claude ändert Dateien im Container, packt sie neu als
   `garmin-dashboard.zip`.
2. Daniel lädt das Zip herunter, entpackt es.
3. Daniel geht in sein GitHub-Repo → **Add file → Upload files** → zieht
   die geänderten Dateien/Ordner rein (Pfade wie `docs/index.html` müssen
   erhalten bleiben) → **Commit changes**.
4. GitHub Pages baut automatisch neu, meist unter einer Minute.

## 8. Tonfall/Stil-Hinweise für die Weiterarbeit

- Kommunikation durchgehend auf Deutsch.
- Daniel ist technisch interessiert, aber kein Profi-Entwickler — braucht
  bei GitHub-UI-Schritten (Secrets, Actions, Pages) klare Schritt-für-
  Schritt-Anleitungen, keine Annahme von Vorwissen.
- Daniel reagiert gut auf präzise, kurze Erklärungen von Bugs (z. B. beim
  Timezone-Bug) — technische Ursache kurz benennen, dann Fix.
- Sicherheitsbewusst (hat z. B. explizit nach Secret-Sichtbarkeit gefragt
  und den Live-Trigger-Button aus Sicherheitsgründen abgelehnt) — bei
  neuen Features mit Zugriffsrechten/Tokens/Credentials transparent auf
  Trade-offs hinweisen statt einfach zu implementieren.
