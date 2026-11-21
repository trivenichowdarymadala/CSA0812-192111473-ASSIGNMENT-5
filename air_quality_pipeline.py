#!/usr/bin/env python3
"""City Air-Quality Monitoring Network: CSV -> validation -> SQLite -> analysis."""
from __future__ import annotations
import argparse, csv, sqlite3, logging, math, json
from pathlib import Path
from datetime import datetime

REQUIRED = {"station_id", "date", "hour", "pm25", "pm10", "no2", "temperature"}
LIMITS = {"pm25": (0, 1000), "pm10": (0, 2000), "no2": (0, 2000), "temperature": (-50, 60)}
logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

def parse_number(raw):
    if raw is None or str(raw).strip().upper() in {"", "NA", "N/A", "NULL"}:
        return None
    try:
        value = float(raw)
        return value if math.isfinite(value) else None
    except (TypeError, ValueError):
        return None

def clean_record(row, fahrenheit_stations):
    cleaned = dict(row)
    cleaned["station_id"] = str(row.get("station_id", "")).strip()
    if not cleaned["station_id"]:
        raise ValueError("missing station_id")
    try:
        datetime.strptime(str(row.get("date", "")).strip(), "%Y-%m-%d")
        hour = int(row.get("hour", ""))
        if not 0 <= hour <= 23:
            raise ValueError("hour outside 0..23")
    except (TypeError, ValueError) as exc:
        raise ValueError(f"invalid date/hour: {exc}") from exc
    cleaned["date"] = str(row["date"]).strip()
    cleaned["hour"] = hour
    for field, (low, high) in LIMITS.items():
        value = parse_number(row.get(field))
        if field == "temperature" and value is not None and cleaned["station_id"] in fahrenheit_stations:
            value = (value - 32) * 5 / 9
        if value is not None and not low <= value <= high:
            value = None
        cleaned[field] = value
    if all(cleaned[k] is None for k in ("pm25", "pm10", "no2", "temperature")):
        raise ValueError("all measurements missing or invalid")
    return cleaned

SCHEMA = """
CREATE TABLE IF NOT EXISTS readings (
 id INTEGER PRIMARY KEY, station_id TEXT NOT NULL, date TEXT NOT NULL,
 hour INTEGER NOT NULL CHECK(hour BETWEEN 0 AND 23),
 pm25 REAL, pm10 REAL, no2 REAL, temperature REAL, source_file TEXT,
 UNIQUE(station_id, date, hour)
);
CREATE INDEX IF NOT EXISTS idx_readings_date_station ON readings(date, station_id);
CREATE TABLE IF NOT EXISTS rejected_rows (
 id INTEGER PRIMARY KEY, source_file TEXT, line_number INTEGER, reason TEXT, raw_json TEXT
);
"""

def init_db(db_path):
    with sqlite3.connect(db_path) as con:
        con.executescript(SCHEMA)

def ingest_csv(csv_path, db_path, fahrenheit_stations):
    csv_path = Path(csv_path)
    accepted = rejected = 0
    with sqlite3.connect(db_path) as con, csv_path.open("r", encoding="utf-8-sig", newline="") as fh:
        reader = csv.DictReader(fh)
        if not reader.fieldnames:
            raise ValueError("empty CSV or missing header")
        missing = REQUIRED - set(reader.fieldnames)
        if missing:
            raise ValueError("missing required columns: " + ", ".join(sorted(missing)))
        for line_no, row in enumerate(reader, start=2):
            try:
                item = clean_record(row, fahrenheit_stations)
                con.execute("""INSERT INTO readings
                    (station_id,date,hour,pm25,pm10,no2,temperature,source_file)
                    VALUES (?,?,?,?,?,?,?,?)
                    ON CONFLICT(station_id,date,hour) DO UPDATE SET
                    pm25=excluded.pm25, pm10=excluded.pm10, no2=excluded.no2,
                    temperature=excluded.temperature, source_file=excluded.source_file""",
                    (item["station_id"], item["date"], item["hour"], item["pm25"],
                     item["pm10"], item["no2"], item["temperature"], csv_path.name))
                accepted += 1
            except (ValueError, TypeError) as exc:
                con.execute("INSERT INTO rejected_rows(source_file,line_number,reason,raw_json) VALUES (?,?,?,?)",
                            (csv_path.name, line_no, str(exc), json.dumps(row, ensure_ascii=False)))
                rejected += 1
    return accepted, rejected

def daily_summary(db_path, output_csv):
    Path(output_csv).parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(db_path) as con:
        rows = con.execute("""SELECT date, COUNT(*) AS records, COUNT(pm25) AS pm25_n,
            ROUND(AVG(pm25),2), ROUND(MAX(pm25),2), ROUND(AVG(pm10),2),
            ROUND(AVG(no2),2), ROUND(AVG(temperature),2)
            FROM readings GROUP BY date ORDER BY date""").fetchall()
    with open(output_csv, "w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(["date","records","pm25_valid","pm25_avg","pm25_max","pm10_avg","no2_avg","temp_c_avg"])
        writer.writerows(rows)
    return rows

def monthly_summary(db_path):
    with sqlite3.connect(db_path) as con:
        return con.execute("""SELECT substr(date,1,7) month, COUNT(*) records,
            ROUND(AVG(pm25),2) pm25_avg, ROUND(MAX(pm25),2) pm25_max,
            ROUND(AVG(pm10),2) pm10_avg, ROUND(AVG(no2),2) no2_avg
            FROM readings GROUP BY substr(date,1,7) ORDER BY month""").fetchall()

def make_charts(db_path, out_dir):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    out = Path(out_dir); out.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(db_path) as con:
        daily = con.execute("SELECT date, AVG(pm25) FROM readings WHERE pm25 IS NOT NULL GROUP BY date ORDER BY date").fetchall()
        station = con.execute("SELECT station_id, AVG(pm25) FROM readings WHERE pm25 IS NOT NULL GROUP BY station_id ORDER BY station_id").fetchall()
    if daily:
        plt.figure(figsize=(9,4)); plt.plot([r[0] for r in daily],[r[1] for r in daily], marker="o")
        plt.title("Daily Mean PM2.5"); plt.xlabel("Date"); plt.ylabel("PM2.5 (µg/m³)")
        plt.xticks(rotation=45, ha="right"); plt.tight_layout(); plt.savefig(out/"daily_pm25.png", dpi=150); plt.close()
    if station:
        plt.figure(figsize=(8,4)); plt.bar([r[0] for r in station],[r[1] for r in station])
        plt.title("Mean PM2.5 by Station"); plt.xlabel("Station"); plt.ylabel("PM2.5 (µg/m³)")
        plt.tight_layout(); plt.savefig(out/"station_pm25.png", dpi=150); plt.close()

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", required=True)
    ap.add_argument("--db", default="air_quality.sqlite")
    ap.add_argument("--fahrenheit-stations", default="ST11,ST12")
    ap.add_argument("--out", default="output")
    args = ap.parse_args()
    fahrenheit = {x.strip() for x in args.fahrenheit_stations.split(",") if x.strip()}
    init_db(args.db)
    accepted, rejected = ingest_csv(args.input, args.db, fahrenheit)
    daily_summary(args.db, Path(args.out)/"daily_summary.csv")
    print(f"Accepted/upserted: {accepted}; rejected: {rejected}")
    print("Monthly summary:", monthly_summary(args.db))

if __name__ == "__main__":
    main()
