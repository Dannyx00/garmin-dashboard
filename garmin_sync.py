"""
Garmin -> data.json Sync

Loggt sich per garminconnect (inoffizielle Bibliothek) bei Garmin Connect ein,
liest Wellness- und Aktivitätsdaten und schreibt eine kompakte JSON-Datei nach
docs/data.json. Diese Datei wird per GitHub Pages öffentlich ausgeliefert und
vom Dashboard (garmin_dashboard.html) per fetch() gelesen -- ohne Claude,
ohne API-Key, ohne Tokenverbrauch im laufenden Betrieb.

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


def safe_call(fn, *args, **kwargs):
    """Ruft fn auf und gibt None zurück, falls das Gerät/Konto den Wert nicht liefert."""
    try:
        return fn(*args, **kwargs)
    except Exception as e:
        print(f"[warn] {fn.__name__} fehlgeschlagen: {e}", file=sys.stderr)
        return None


def extract_wellness(client, today_str):
    wellness = {
        "body_battery": None,
        "sleep_score": None,
        "hrv": None,
        "stress_avg": None,
        "readiness": None,
    }

    bb = safe_call(client.get_body_battery, today_str, today_str)
    if bb and isinstance(bb, list) and len(bb) > 0:
        entry = bb[0]
        wellness["body_battery"] = entry.get("charged") or entry.get("bodyBatteryValuesArray", [[None, None]])[-1][-1] \
            if entry.get("bodyBatteryValuesArray") else entry.get("charged")

    sleep = safe_call(client.get_sleep_data, today_str)
    if sleep and isinstance(sleep, dict):
        dto = sleep.get("dailySleepDTO", {}) or {}
        wellness["sleep_score"] = dto.get("sleepScores", {}).get("overall", {}).get("value") \
            if dto.get("sleepScores") else dto.get("overallSleepScore")

    hrv = safe_call(client.get_hrv_data, today_str)
    if hrv and isinstance(hrv, dict):
        summary = hrv.get("hrvSummary", {}) or {}
        wellness["hrv"] = summary.get("lastNightAvg")

    stress = safe_call(client.get_stress_data, today_str)
    if stress and isinstance(stress, dict):
        wellness["stress_avg"] = stress.get("avgStressLevel")

    readiness = safe_call(client.get_training_readiness, today_str)
    if readiness and isinstance(readiness, list) and len(readiness) > 0:
        wellness["readiness"] = readiness[0].get("score")

    return wellness


def extract_activities(client, limit=10):
    raw = safe_call(client.get_activities, 0, limit) or []
    activities = []
    for a in raw:
        activities.append({
            "name": a.get("activityName"),
            "type": (a.get("activityType", {}) or {}).get("typeKey", "").upper(),
            "date": (a.get("startTimeLocal") or "")[:10],
            "distance_km": round((a.get("distance") or 0) / 1000, 2),
            "duration_min": round((a.get("duration") or 0) / 60, 1),
            "avg_hr": a.get("averageHR"),
            "max_hr": a.get("maxHR"),
            "calories": a.get("calories"),
        })
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
