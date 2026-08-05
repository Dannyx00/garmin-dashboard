"""
Garmin -> data.json Sync

Loggt sich per garminconnect (inoffizielle Bibliothek) bei Garmin Connect ein,
liest Wellness- und Aktivitätsdaten (inkl. Splits & Pulszonen für die letzten
Aktivitäten) und schreibt eine JSON-Datei nach docs/data.json. Diese Datei wird
per GitHub Pages öffentlich ausgeliefert und vom Dashboard (docs/index.html)
per fetch() gelesen -- ohne Claude, ohne API-Key, ohne Tokenverbrauch im
laufenden Betrieb.

Benötigte Umgebungsvariablen (in GitHub Actions als Secrets hinterlegt):
  GARMIN_EMAIL
  GARMIN_PASSWORD
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

DETAIL_COUNT = 5  # für wie viele der jüngsten Aktivitäten Splits/Pulszonen geladen werden


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
    if not email or not password:
        print("GARMIN_EMAIL / GARMIN_PASSWORD nicht gesetzt.", file=sys.stderr)
        sys.exit(1)

    client = Garmin(email, password)
    client.login()

    today = dt.date.today()
    today_str = today.isoformat()

    wellness = extract_wellness(client, today_str)
    activities = extract_activities(client, limit=10)
    summary = week_summary(activities, today)

    output = {
        "generated_at": dt.datetime.utcnow().isoformat() + "Z",
        "week_km": summary["week_km"],
        "week_sessions": summary["week_sessions"],
        "week_calories": summary["week_calories"],
        "wellness": wellness,
        "activities": activities[:5],
    }

    out_path = os.path.join(os.path.dirname(__file__), "..", "docs", "data.json")
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"OK -> {out_path}")


if __name__ == "__main__":
    main()
