#!/usr/bin/env python3
"""
Huntcliff Neighborhood Power Outage Poller (cloud version)
------------------------------------------------------------
Meant to be run by the included GitHub Actions workflow every 15 minutes.
Reads/writes docs/history.json so it can be committed back to the repo and
served by GitHub Pages as a live status page.
"""

import json
import os
from datetime import datetime, timezone
import requests

BBOX = {"xmin": -84.375, "ymin": 33.9746, "xmax": -84.351, "ymax": 34.0001}

FEED_URL = (
    "https://services.arcgis.com/BLN4oKB0N1YSgvY8/ArcGIS/rest/services/"
    "Power_Outages_(View)/FeatureServer/0/query"
)

HISTORY_PATH = os.path.join(os.path.dirname(__file__), "docs", "history.json")


def load_history():
    if os.path.exists(HISTORY_PATH):
        with open(HISTORY_PATH, "r") as f:
            return json.load(f)
    return {}


def save_history(history):
    os.makedirs(os.path.dirname(HISTORY_PATH), exist_ok=True)
    with open(HISTORY_PATH, "w") as f:
        json.dump(history, f, indent=2, sort_keys=True)


def fetch_outages():
    params = {
        "where": "1=1",
        "geometry": f"{BBOX['xmin']},{BBOX['ymin']},{BBOX['xmax']},{BBOX['ymax']}",
        "geometryType": "esriGeometryEnvelope",
        "inSR": "4326",
        "spatialRel": "esriSpatialRelIntersects",
        "outFields": "*",
        "returnGeometry": "false",
        "f": "geojson",
    }
    resp = requests.get(FEED_URL, params=params, timeout=30)
    resp.raise_for_status()
    return resp.json().get("features", [])


def main():
    history = load_history()
    history.pop("_lastChecked", None)  # strip marker before treating entries as records
    now = datetime.now(timezone.utc).isoformat()
    seen_ids = set()

    try:
        features = fetch_outages()
    except requests.RequestException as e:
        print(f"Fetch failed: {e}")
        return

    for feat in features:
        p = feat.get("properties", {})
        incident_id = str(p.get("IncidentId") or p.get("OBJECTID"))
        seen_ids.add(incident_id)
        existing = history.get(incident_id, {})
        history[incident_id] = {
            "id": incident_id,
            "utility": p.get("UtilityCompany") or existing.get("utility") or "Georgia Power",
            "startDate": p.get("StartDate") or existing.get("startDate") or now,
            "estRestore": p.get("EstimatedRestoreDate", existing.get("estRestore")),
            "cause": p.get("Cause") or existing.get("cause") or "Unknown",
            "customers": p.get("ImpactedCustomers", existing.get("customers")),
            "county": p.get("County") or existing.get("county") or "",
            "outageType": p.get("OutageType") or existing.get("outageType") or "",
            "firstSeen": existing.get("firstSeen") or now,
            "lastSeen": now,
            "status": "Active",
            "resolvedAt": None,
        }
        if incident_id not in existing:
            print(f"[NEW OUTAGE] {incident_id} — {p.get('Cause')}")

    for incident_id, rec in history.items():
        if rec.get("status") == "Active" and incident_id not in seen_ids:
            rec["status"] = "Restored"
            rec["resolvedAt"] = now
            print(f"[RESTORED] {incident_id}")

    history["_lastChecked"] = now
    save_history(history)
    print(f"{now} — {len(features)} outage(s) currently active in Huntcliff bbox")


if __name__ == "__main__":
    main()
