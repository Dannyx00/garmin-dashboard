"""
Garmin -> data.json Sync

Loggt sich per garminconnect (inoffizielle Bibliothek) bei Garmin Connect ein,
liest Wellness- und Aktivitätsdaten (inkl. Splits & Pulszonen für die letzten
Aktivitäten) und schreibt eine JSON-Datei nach docs/data.json. Diese Datei wird
per GitHub Pages öffentlich ausgeliefert und vom Dashboard (docs/index.html)
per fetch() gelesen.

Die Kurzauswertung ("Diese Woche") ist weiterhin primär regelbasiert
(deterministische Kennzahlen, kein API-Call nötig). Optional -- nur wenn
ANTHROPIC_API_KEY gesetzt ist -- wird daraus zusätzlich ein 2-3-Satz-Kommentar
von Claude Haiku 4.5 erzeugt. Das passiert NICHT bei jedem Sync-Lauf, sondern
nur, wenn seit dem letzten Mal eine NEUE Aktivität dazugekommen ist (Vergleich
der Activity-ID mit dem vorherigen data.json-Stand). Bei 3-4 Läufen/Woche sind
das 3-4 API-Calls/Woche, nicht 24/Tag. Schlägt der Call fehl oder ist kein Key
gesetzt, bleibt der zuletzt erzeugte KI-Text (oder gar keiner) einfach stehen
-- die Seite bricht nie, das Dashboard fällt im Frontend auf die regelbasierte
Logik zurück.

Benötigte Umgebungsvariablen (in GitHub Actions als Secrets hinterlegt):
  GARMIN_EMAIL
  GARMIN_PASSWORD
  ANTHROPIC_API_KEY   (optional -- ohne ihn läuft alles wie bisher, nur ohne
                        KI-Kommentar)
"""

import os
import sys
import json
import datetime as dt

try:
    from garminconnect import Garmin
except ImportError:
    print("Bitte zuerst installieren: pip install garminconnect", file=sys.stderr)
    raise

try:
    import requests
except ImportError:
    requests = None  # KI-Kommentar wird dann einfach übersprungen

DETAIL_COUNT = 5  # für wie viele der jüngsten Aktivitäten Splits/Pulszonen geladen werden
AI_MODEL = "claude-haiku-4-5"
AI_MAX_TOKENS = 220

AI_SYSTEM_PROMPT = """Du bist ein direkter, sachlicher Lauftrainer für Daniel.
Er trainiert für einen Marathon (Ziel: unter 4:00 h, Rennen 01.11.2026, Zielpace
~5:41 min/km). Du bekommst bereits fertig berechnete Kennzahlen zu seinem letzten
Lauf (keine Rohdaten) und schreibst dazu 2-3 kurze Sätze auf Deutsch.

Wichtiger Kontext zu Daniel: Er hat ein wiederkehrendes Pacing-Muster -- zu
konservativer Start, dann Überkorrektur mit Tempospitzen/Zone-5-Ausreißern zum
Ende hin. Wenn die gelieferten Kennzahlen (erste vs. zweite Laufhälfte) dieses
Muster zeigen, sprich es konkret und ohne Beschönigung an. Seine HF-Zonen
(LTHR ~197 bpm) sind vorläufig und noch nicht sauber retestet -- sei bei
Aussagen zu Zone 4/5 entsprechend vorsichtig formuliert.

Stil: direkt, keine Floskeln, keine leeren Komplimente. Lob nur, wenn es durch
die Zahlen tatsächlich gedeckt ist (z. B. gleichmäßige Splits, Zielbereich
getroffen). Keine Emojis, keine Überschriften, reiner Fließtext, maximal 3 Sätze."""


def safe_call(fn, *args, **kwargs):
    """Ruft fn auf und gibt None zurück, falls das Gerät/Konto den Wert nicht liefert."""
    try:
        return fn(*args, **kwargs)
    except Exception as e:
        print(f"[warn] {getattr(fn, '__name__', fn)} fehlgeschlagen: {e}", file=sys.stderr)
        return None


def extract_wellness(client, today_str):
    wellness = {
        "body_battery": None,
        "sleep_score": None,
        "hrv": None,
        "hrv_status": None,       # BALANCED / UNBALANCED / LOW (von Garmin selbst ermittelt)
        "hrv_baseline_low": None, # untere Grenze von Garmins persönlichem "ausgeglichenem" Bereich
        "hrv_baseline_high": None,
        "stress_avg": None,
        "readiness": None,
    }

    bb = safe_call(client.get_body_battery, today_str, today_str)
    if bb and isinstance(bb, list) and len(bb) > 0:
        entry = bb[0]
        wellness["body_battery"] = entry.get("charged")

    sleep = safe_call(client.get_sleep_data, today_str)
    if sleep and isinstance(sleep, dict):
        dto = sleep.get("dailySleepDTO", {}) or {}
        scores = dto.get("sleepScores", {}) or {}
        wellness["sleep_score"] = (scores.get("overall", {}) or {}).get("value") or dto.get("overallSleepScore")

    hrv = safe_call(client.get_hrv_data, today_str)
    if hrv and isinstance(hrv, dict):
        summary = hrv.get("hrvSummary", {}) or {}
        wellness["hrv"] = summary.get("lastNightAvg")
        wellness["hrv_status"] = summary.get("status")
        baseline = summary.get("baseline", {}) or {}
        wellness["hrv_baseline_low"] = baseline.get("balancedLow")
        wellness["hrv_baseline_high"] = baseline.get("balancedUpper")

    stress = safe_call(client.get_stress_data, today_str)
    if stress and isinstance(stress, dict):
        wellness["stress_avg"] = stress.get("avgStressLevel")

    readiness = safe_call(client.get_training_readiness, today_str)
    if readiness and isinstance(readiness, list) and len(readiness) > 0:
        wellness["readiness"] = readiness[0].get("score")

    return wellness


def format_pace(duration_s, distance_km):
    if not distance_km or distance_km <= 0:
        return None
    pace_min = (duration_s / 60) / distance_km
    minutes = int(pace_min)
    seconds = round((pace_min % 1) * 60)
    if seconds == 60:
        minutes += 1
        seconds = 0
    return f"{minutes}:{seconds:02d}"


def extract_activity_detail(client, activity_id):
    detail = {"elevation_gain_m": None, "splits": [], "hr_zones": []}

    full = safe_call(client.get_activity, activity_id)
    if full and isinstance(full, dict):
        summary = full.get("summaryDTO", full.get("summary", {})) or {}
        detail["elevation_gain_m"] = summary.get("elevationGain")

    splits = safe_call(client.get_activity_splits, activity_id)
    if splits and isinstance(splits, dict):
        for lap in splits.get("lapDTOs", []) or []:
            dist_km = round((lap.get("distance") or 0) / 1000, 2)
            dur_s = lap.get("duration") or 0
            detail["splits"].append({
                "km": dist_km,
                "pace": format_pace(dur_s, dist_km),
                "hr": lap.get("averageHR"),
            })

    zones = safe_call(client.get_activity_hr_in_timezones, activity_id)
    if zones and isinstance(zones, list):
        for z in zones:
            detail["hr_zones"].append({
                "zone": z.get("zoneNumber"),
                "minutes": round((z.get("secsInZone") or 0) / 60, 1),
            })

    return detail


def extract_activities(client, limit=10):
    raw = safe_call(client.get_activities, 0, limit) or []
    activities = []
    for idx, a in enumerate(raw):
        distance_km = round((a.get("distance") or 0) / 1000, 2)
        duration_s = a.get("duration") or 0
        activity_id = a.get("activityId")
        item = {
            "id": activity_id,
            "name": a.get("activityName"),
            "type": (a.get("activityType", {}) or {}).get("typeKey", "").upper(),
            "date": (a.get("startTimeLocal") or "")[:10],
            "distance_km": distance_km,
            "duration_min": round(duration_s / 60, 1),
            "avg_pace_per_km": format_pace(duration_s, distance_km),
            "avg_hr": a.get("averageHR"),
            "max_hr": a.get("maxHR"),
            "calories": a.get("calories"),
            "elevation_gain_m": None,
            "splits": [],
            "hr_zones": [],
        }
        if idx < DETAIL_COUNT and activity_id:
            item.update(extract_activity_detail(client, activity_id))
        activities.append(item)
    return activities


def load_plan_day(activity_date_str):
    """Sucht im echten Trainingsplan (docs/training_plan.json) den Tageseintrag
    für ein gegebenes Datum (YYYY-MM-DD). Gibt None zurück, wenn kein Plan-Eintrag
    für die betreffende Woche existiert (dann greift im Frontend die Fallback-Logik)."""
    try:
        plan_path = os.path.join(os.path.dirname(__file__), "..", "docs", "training_plan.json")
        with open(plan_path, "r", encoding="utf-8") as f:
            plan = json.load(f)
        weeks = plan.get("weeks", {})
        d = dt.date.fromisoformat(activity_date_str)
        monday = (d - dt.timedelta(days=d.weekday())).isoformat()
        week = weeks.get(monday)
        if not week:
            return None
        day_abbr = ["Mo", "Di", "Mi", "Do", "Fr", "Sa", "So"][d.weekday()]
        return week.get("days", {}).get(day_abbr)
    except Exception as e:
        print(f"[warn] Plan-Lookup fehlgeschlagen: {e}", file=sys.stderr)
        return None


def compute_pacing_facts(activity):
    """Deterministische Kennzahlen zur Pacing-Disziplin -- laufen komplett ohne
    API und sind die Basis sowohl für den Regel-Fallback im Frontend als auch
    für den Kontext, den Claude für den Kommentar bekommt."""
    facts = {
        "half_split_drift": None,   # Sekunden/km schneller (negativ) oder langsamer (positiv) in 2. Hälfte
        "half_split_hr_drift": None,  # bpm-Unterschied 2. vs 1. Hälfte
        "split_std_dev_s": None,
        "zone_low_pct": None,   # % der Zeit in Zone 1-2
        "zone_high_pct": None,  # % der Zeit in Zone 3-5
    }

    splits = [s for s in (activity.get("splits") or []) if s.get("pace")]
    if len(splits) >= 4:
        def pace_to_s(p):
            m, s = p.split(":")
            return int(m) * 60 + int(s)

        mid = len(splits) // 2
        first, second = splits[:mid], splits[mid:]
        first_paces = [pace_to_s(s["pace"]) for s in first]
        second_paces = [pace_to_s(s["pace"]) for s in second]
        facts["half_split_drift"] = round((sum(second_paces) / len(second_paces)) - (sum(first_paces) / len(first_paces)), 1)

        first_hrs = [s["hr"] for s in first if s.get("hr")]
        second_hrs = [s["hr"] for s in second if s.get("hr")]
        if first_hrs and second_hrs:
            facts["half_split_hr_drift"] = round((sum(second_hrs) / len(second_hrs)) - (sum(first_hrs) / len(first_hrs)), 1)

        all_paces = first_paces + second_paces
        avg = sum(all_paces) / len(all_paces)
        variance = sum((p - avg) ** 2 for p in all_paces) / len(all_paces)
        facts["split_std_dev_s"] = round(variance ** 0.5, 1)

    zones = activity.get("hr_zones") or []
    total_min = sum(z.get("minutes") or 0 for z in zones)
    if total_min > 0:
        low = sum(z.get("minutes") or 0 for z in zones if (z.get("zone") or 0) <= 2)
        facts["zone_low_pct"] = round(100 * low / total_min, 1)
        facts["zone_high_pct"] = round(100 - facts["zone_low_pct"], 1)

    return facts


def generate_ai_assessment(activity, plan_day, facts, api_key):
    """Ein einzelner, kurzer Haiku-4.5-Call, der die bereits berechneten Fakten
    in einen Coaching-Kommentar umwandelt. Gibt None zurück bei jedem Fehler
    (fehlender Key, Netzwerkproblem, Timeout, unerwartete Antwort) -- der
    Aufrufer behält dann einfach den vorherigen Stand."""
    if not requests or not api_key:
        return None

    payload_facts = {
        "lauf": activity.get("name") or activity.get("type"),
        "datum": activity.get("date"),
        "distanz_km": activity.get("distance_km"),
        "dauer_min": activity.get("duration_min"),
        "schnitt_pace_min_km": activity.get("avg_pace_per_km"),
        "hf_avg": activity.get("avg_hr"),
        "hf_max": activity.get("max_hr"),
        "pace_drift_2_haelfte_s_pro_km": facts.get("half_split_drift"),
        "hf_drift_2_haelfte_bpm": facts.get("half_split_hr_drift"),
        "split_streuung_s": facts.get("split_std_dev_s"),
        "zeit_in_zone_1_2_prozent": facts.get("zone_low_pct"),
        "zeit_in_zone_3_5_prozent": facts.get("zone_high_pct"),
        "plan_fuer_diesen_tag": plan_day.get("title") if plan_day else None,
    }

    try:
        resp = requests.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json={
                "model": AI_MODEL,
                "max_tokens": AI_MAX_TOKENS,
                "system": AI_SYSTEM_PROMPT,
                "messages": [
                    {"role": "user", "content": json.dumps(payload_facts, ensure_ascii=False)}
                ],
            },
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
        text = "".join(
            block.get("text", "") for block in data.get("content", []) if block.get("type") == "text"
        ).strip()
        return text or None
    except Exception as e:
        print(f"[warn] KI-Kommentar fehlgeschlagen, behalte alten Stand: {e}", file=sys.stderr)
        return None


def week_summary(activities, today):
    week_ago = today - dt.timedelta(days=7)
    week_acts = [
        a for a in activities
        if a["date"] and dt.date.fromisoformat(a["date"]) >= week_ago
    ]
    return {
        "week_km": round(sum(a["distance_km"] for a in week_acts), 1),
        "week_sessions": len(week_acts),
        "week_calories": sum(a["calories"] or 0 for a in week_acts),
    }


def main():
    email = os.environ.get("GARMIN_EMAIL")
    password = os.environ.get("GARMIN_PASSWORD")
    anthropic_key = os.environ.get("ANTHROPIC_API_KEY")  # optional
    if not email or not password:
        print("GARMIN_EMAIL / GARMIN_PASSWORD nicht gesetzt.", file=sys.stderr)
        sys.exit(1)

    out_path = os.path.join(os.path.dirname(__file__), "..", "docs", "data.json")

    # Vorherigen Stand lesen -- brauchen wir für die Dedupe-Prüfung (nur bei
    # NEUER Aktivität einen KI-Call machen) und um bei einem fehlgeschlagenen
    # Call den letzten guten KI-Text nicht zu verlieren.
    previous = {}
    if os.path.exists(out_path):
        try:
            with open(out_path, "r", encoding="utf-8") as f:
                previous = json.load(f)
        except Exception as e:
            print(f"[warn] konnte vorherige data.json nicht lesen: {e}", file=sys.stderr)

    client = Garmin(email, password)
    client.login()

    today = dt.date.today()
    today_str = today.isoformat()

    wellness = extract_wellness(client, today_str)
    activities = extract_activities(client, limit=10)
    summary = week_summary(activities, today)

    ai_text = previous.get("ai_assessment")
    ai_activity_id = previous.get("ai_assessment_activity_id")
    ai_model = previous.get("ai_assessment_model")
    ai_updated_at = previous.get("ai_assessment_updated_at")

    latest = activities[0] if activities else None
    if latest and latest.get("id") and latest["id"] != ai_activity_id:
        if anthropic_key:
            plan_day = load_plan_day(latest["date"]) if latest.get("date") else None
            facts = compute_pacing_facts(latest)
            new_text = generate_ai_assessment(latest, plan_day, facts, anthropic_key)
            if new_text:
                ai_text = new_text
                ai_activity_id = latest["id"]
                ai_model = AI_MODEL
                ai_updated_at = dt.datetime.utcnow().isoformat() + "Z"
                print(f"KI-Kommentar aktualisiert für Aktivität {latest['id']}")
            else:
                print("KI-Kommentar nicht aktualisiert (Call fehlgeschlagen oder kein Text) -- alter Stand bleibt.")
        else:
            print("ANTHROPIC_API_KEY nicht gesetzt -- überspringe KI-Kommentar, regelbasierte Auswertung läuft im Frontend weiter.")

    output = {
        "generated_at": dt.datetime.utcnow().isoformat() + "Z",
        "week_km": summary["week_km"],
        "week_sessions": summary["week_sessions"],
        "week_calories": summary["week_calories"],
        "wellness": wellness,
        "activities": activities[:5],
        "ai_assessment": ai_text,
        "ai_assessment_activity_id": ai_activity_id,
        "ai_assessment_model": ai_model,
        "ai_assessment_updated_at": ai_updated_at,
    }

    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"OK -> {out_path}")


if __name__ == "__main__":
    main()
