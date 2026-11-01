"""Local SQLite snapshots and a reproducible research-experiment ledger."""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sqlite3
from uuid import uuid4

import pandas as pd


def definition_hash(config):
    data = config.to_dict()
    data.pop("name", None)
    data.pop("risk", None)  # Descriptive ratios do not change MA eligibility.
    for ma in data["moving_averages"]:
        ma.pop("show", None)
    for rule in data["rules"]:
        rule.pop("name", None)
        rule.pop("lookback_mode", None)  # Effective lookback, not its editor mode, defines eligibility.
    for group in data["groups"]:
        group.pop("name", None)
    settings = data["data_settings"]
    data["data_settings"] = {k: settings.get(k) for k in (
        "source", "universe_mode", "tickers", "single_ticker", "sector", "ticker_aliases", "membership_digest")}
    data.pop("return_kind", None)
    return hashlib.sha256(json.dumps(data, sort_keys=True).encode()).hexdigest()


class HistoryStore:
    def __init__(self, directory):
        directory = Path(directory)
        directory.mkdir(parents=True, exist_ok=True)
        self.path = directory / "history.sqlite3"
        with self.connect() as db:
            db.executescript("""
            CREATE TABLE IF NOT EXISTS screens(
              id TEXT PRIMARY KEY, created_at TEXT, screen_date TEXT, definition TEXT,
              config_json TEXT, results_json TEXT);
            CREATE INDEX IF NOT EXISTS screen_dates ON screens(definition,screen_date,created_at);
            CREATE TABLE IF NOT EXISTS experiments(
              id TEXT PRIMARY KEY, created_at TEXT, kind TEXT, plan_json TEXT, result_json TEXT);
            """)

    def connect(self):
        return sqlite3.connect(self.path, timeout=30)

    def save_screen(self, run):
        identifier = uuid4().hex
        with self.connect() as db:
            db.execute("INSERT INTO screens VALUES(?,?,?,?,?,?)", (
                identifier, datetime.now(timezone.utc).isoformat(), str(run.screen_date),
                definition_hash(run.config), run.config.to_json(), run.table.to_json(orient="records")))
        return identifier

    def list_screens(self, limit=200):
        with self.connect() as db:
            return pd.read_sql_query("SELECT id,created_at,screen_date,definition FROM screens "
                                     "ORDER BY created_at DESC LIMIT ?", db, params=(int(limit),))

    def screen(self, identifier):
        with self.connect() as db:
            row = db.execute("SELECT * FROM screens WHERE id=?", (identifier,)).fetchone()
        if row is None:
            raise ValueError("Screen snapshot not found")
        return {"id": row[0], "created_at": row[1], "screen_date": row[2], "definition": row[3],
                "config": json.loads(row[4]), "table": pd.DataFrame(json.loads(row[5]))}

    def delete_screens(self, identifiers):
        """Delete explicit snapshot IDs only; preserve prices and experiment inputs."""
        identifiers = list(dict.fromkeys(identifiers))
        with self.connect() as db:
            before = db.total_changes
            db.executemany("DELETE FROM screens WHERE id=?", [(i,) for i in identifiers])
            return db.total_changes - before

    def compare(self, identifier):
        current = self.screen(identifier)
        with self.connect() as db:
            prior = db.execute(
                "SELECT id FROM screens WHERE definition=? AND screen_date<? "
                "ORDER BY screen_date DESC,created_at DESC LIMIT 1",
                (current["definition"], current["screen_date"])).fetchone()
        if prior is None:
            return None, pd.DataFrame()
        old = self.screen(prior[0])
        before = old["table"].set_index("ticker")
        after = current["table"].set_index("ticker")
        rows = []
        rules = [r for r in current["config"]["rules"] if r["enabled"]]
        with self.connect() as db:
            saved = db.execute(
                "SELECT screen_date,results_json FROM screens WHERE definition=? AND screen_date<=? AND created_at<=? "
                "ORDER BY screen_date DESC,created_at DESC",
                (current["definition"], current["screen_date"], current["created_at"])).fetchall()
        dates, sessions = set(), []
        for day, text in saved:
            if day not in dates:
                dates.add(day)
                sessions.append({r["ticker"]: r["status"] for r in json.loads(text)})
        for ticker in sorted(set(before.index) | set(after.index)):
            a = before.loc[ticker].to_dict() if ticker in before.index else {}
            b = after.loc[ticker].to_dict() if ticker in after.index else {}
            previous, latest = a.get("status", "NOT_IN_UNIVERSE"), b.get("status", "NOT_IN_UNIVERSE")
            if latest == "INSUFFICIENT":
                change = "Now unavailable" if previous != latest else "Still unavailable"
            elif latest == "NOT_IN_UNIVERSE":
                change = "Left universe"
            elif previous == "NOT_IN_UNIVERSE":
                change = "New to universe"
            elif latest == "PASS" and previous == "INSUFFICIENT":
                change = "Now qualifying; prior data unavailable"
            elif latest == "PASS" and previous != "PASS":
                change = "Newly qualifying"
            elif latest == "PASS":
                change = "Still qualifying"
            elif previous == "PASS":
                change = "Stopped qualifying"
            else:
                change = "Still not qualifying"
            changed = []
            for rule in rules:
                key = rule["id"]
                def state(row):
                    return "UNAVAILABLE" if pd.isna(row.get(key + ".value")) else (
                        "PASS" if row.get(key + ".pass", False) else "FAIL")
                left, right = state(a), state(b)
                if left != right:
                    changed.append(f"{rule['name']}: {left} → {right}")
            streak = 0
            for states in sessions:
                if states.get(ticker) != "PASS":
                    break
                streak += 1
            rows.append({"ticker": ticker, "previous": previous, "latest": latest, "change": change,
                         "changed_rules": " | ".join(changed), "consecutive_saved_sessions": streak})
        return old, pd.DataFrame(rows)

    def record_experiment(self, kind, plan, result=None):
        identifier = uuid4().hex
        with self.connect() as db:
            db.execute("INSERT INTO experiments VALUES(?,?,?,?,?)", (
                identifier, datetime.now(timezone.utc).isoformat(), kind,
                json.dumps(plan, sort_keys=True, allow_nan=False),
                json.dumps(result, default=str) if result is not None else None))
        return identifier

    def experiment(self, identifier):
        with self.connect() as db:
            row = db.execute("SELECT * FROM experiments WHERE id=?", (identifier,)).fetchone()
        if row is None:
            raise ValueError("Experiment not found")
        return {"id": row[0], "created_at": row[1], "kind": row[2],
                "plan": json.loads(row[3]), "result": json.loads(row[4]) if row[4] else None}

    def complete_experiment(self, identifier, result):
        with self.connect() as db:
            db.execute("UPDATE experiments SET result_json=? WHERE id=?", (json.dumps(result, default=str), identifier))

    def list_experiments(self):
        with self.connect() as db:
            return pd.read_sql_query("SELECT id,created_at,kind,plan_json,result_json FROM experiments "
                                     "ORDER BY created_at DESC", db)
