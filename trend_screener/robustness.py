"""Recorded fixed-neighborhood trials, chronological slices and frozen holdouts."""
from __future__ import annotations

from dataclasses import asdict
from datetime import timedelta
from io import BytesIO
import json
import math
import zipfile

import numpy as np
import pandas as pd

from .models import ScreenConfig
from .snapshots import SnapshotStore
from .studies import BacktestSettings, StudyEngine, backtest, frozen_plan, parameter_neighbors


def finite_json(value):
    """Strict portable JSON summaries: undefined metrics become null, not NaN."""
    if isinstance(value, dict):
        return {str(k): finite_json(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [finite_json(v) for v in value]
    if isinstance(value, (float, np.floating)):
        return float(value) if math.isfinite(value) else None
    if isinstance(value, np.integer):
        return int(value)
    return value


def engine_slice(engine, config, start, end):
    return StudyEngine(engine.prices, engine.universe, config, start, end, engine.membership)


def recorded_backtest(store, kind, engine, settings, risk=None, extra=None, progress=None):
    plan = {"config": engine.config.to_dict(), "backtest": asdict(settings),
            "start": str(engine.start), "end": str(engine.end),
            "data_fingerprint": engine.fingerprint,
            "membership_digest": engine.membership.digest if engine.membership else None,
            **(extra or {})}
    identifier = store.record_experiment(kind, plan)
    try:
        result = backtest(engine, settings, risk, progress)
        store.complete_experiment(identifier, finite_json({"status": "COMPLETED", **result.summary()}))
        return identifier, result
    except Exception as exc:
        store.complete_experiment(identifier, {"status": "ERROR", "error": str(exc)})
        raise


def robustness_trials(engine, settings, ma_key, rule_id, store, *, subperiods=3, risk=None, progress=None):
    """All fixed candidates in declared order; never sort or pick a best outcome."""
    rows = []
    variants = parameter_neighbors(engine.config, ma_key, rule_id)
    segments = [s for s in np.array_split(engine.dates, subperiods) if len(s) >= 2]
    candidates = [(name, cfg, engine.start, engine.end, error) for name, cfg, error in variants]
    candidates += [(f"Chronological slice {i + 1}", engine.config, dates[0].date(), dates[-1].date(), "")
                   for i, dates in enumerate(segments)]
    for i, (label, cfg, start, end, error) in enumerate(candidates):
        if cfg is None:
            identifier = store.record_experiment("robustness", {"variant": label},
                                                {"status": "SKIPPED", "error": error})
            row = {"variant": label, "start": str(start), "end": str(end),
                   "experiment_id": identifier, "status": "SKIPPED", "error": error}
        else:
            row = {"variant": label, "start": str(start), "end": str(end)}
            try:
                sample = engine_slice(engine, cfg, start, end)
                identifier, result = recorded_backtest(store, "robustness", sample, settings, risk,
                                                       {"variant": label})
                row.update({"experiment_id": identifier, "status": "COMPLETED", **result.summary()})
            except (ValueError, RuntimeError) as exc:
                row.update({"status": "ERROR", "error": str(exc)})
        rows.append(row)
        if progress:
            progress(i + 1, len(candidates))
    return pd.DataFrame(rows)


def _snapshot_store(store):
    return SnapshotStore(store.path.parent / "snapshots")


def validate_frozen_inputs(plan, engine):
    config = ScreenConfig.from_dict(plan["config"], require_rules=True)
    BacktestSettings(**plan["backtest"]).validate()
    if plan["data_fingerprint"] != engine.fingerprint:
        raise ValueError("Loaded prices differ from the frozen data snapshot. Load the original snapshot "
                         "or create a new explicitly recorded plan; the frozen plan was not changed.")
    if plan["membership_digest"] != (engine.membership.digest if engine.membership else None):
        raise ValueError("Historical membership differs from the frozen source")
    if (plan["start"], plan["end"]) != (str(engine.start), str(engine.end)):
        raise ValueError("Load the same full study date range as the frozen plan")
    split = pd.Timestamp(plan["split"])
    if not pd.Timestamp(engine.start) < split < pd.Timestamp(engine.end):
        raise ValueError("Frozen training/holdout split must be inside its study dates")
    if sum(engine.dates <= split) < 2 or sum(engine.dates > split) < 2:
        raise ValueError("Frozen training and holdout each need at least two trading sessions")
    return config, split.date()


def freeze_study(store, config, settings, engine, split, metadata=None):
    plan = frozen_plan(config, settings, engine, split, metadata)
    validate_frozen_inputs(plan, engine)
    plan["snapshot"] = _snapshot_store(store).save(engine, metadata)
    return store.record_experiment("frozen_holdout", plan)


def export_frozen_bundle(store, frozen_id):
    frozen = store.experiment(frozen_id)
    if frozen["kind"] != "frozen_holdout" or not frozen["plan"].get("snapshot"):
        raise ValueError("This plan has no saved price snapshot; freeze a new study to create a portable bundle")
    raw = _snapshot_store(store).read(frozen["plan"]["snapshot"])
    buffer = BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as bundle:
        bundle.writestr("plan.json", json.dumps({"format_version": 1, "origin_id": frozen_id,
                                                "created_at": frozen["created_at"], "plan": frozen["plan"]},
                                               indent=2, allow_nan=False))
        bundle.writestr("snapshot.zip", raw)
    return buffer.getvalue()


def import_frozen_bundle(store, raw):
    try:
        with zipfile.ZipFile(BytesIO(raw)) as bundle:
            if sorted(bundle.namelist()) != ["plan.json", "snapshot.zip"]:
                raise ValueError("Frozen study bundle must contain plan.json and snapshot.zip exactly once")
            document = json.loads(bundle.read("plan.json"))
            if document["format_version"] != 1:
                raise ValueError("Unsupported frozen study bundle format")
            plan = document["plan"]
            config = ScreenConfig.from_dict(plan["config"], require_rules=True)
            snapshot = bundle.read("snapshot.zip")
        # Validate everything before publishing either the imported archive or ledger row.
        snapshots = _snapshot_store(store)
        engine, _ = snapshots.decode(snapshot, plan["snapshot"], config)
        validate_frozen_inputs(plan, engine)
        plan["imported_from"] = {"origin_id": document["origin_id"], "created_at": document["created_at"]}
        json.dumps(plan, allow_nan=False)
        _, descriptor = snapshots.import_snapshot(snapshot, plan["snapshot"], config)
        plan["snapshot"] = descriptor
        return store.record_experiment("frozen_holdout", plan)
    except (zipfile.BadZipFile, KeyError, TypeError, json.JSONDecodeError, UnicodeError) as exc:
        raise ValueError(f"Invalid frozen study bundle: {exc}") from exc


def evaluate_frozen_holdout(store, frozen_id, loaded_engine=None, risk=None, progress=None):
    frozen = store.experiment(frozen_id)
    if frozen["kind"] != "frozen_holdout":
        raise ValueError("Select a frozen holdout plan")
    plan = frozen["plan"]
    config = ScreenConfig.from_dict(plan["config"])
    if plan.get("snapshot"):
        loaded_engine = _snapshot_store(store).load(plan["snapshot"], config)
    elif loaded_engine is None:
        raise ValueError("Legacy plan has no saved prices. Load its original study data in Robustness to evaluate it")
    config, split = validate_frozen_inputs(plan, loaded_engine)
    # The first holdout close generates a next-session order; never reuse a training signal.
    sample = engine_slice(loaded_engine, config, split + timedelta(days=1), loaded_engine.end)
    settings = BacktestSettings(**plan["backtest"])
    return recorded_backtest(store, "holdout_evaluation", sample, settings, config.risk,
                             {"frozen_plan_id": frozen_id, "frozen_plan": json.loads(json.dumps(plan)),
                              "input_source": "Archived snapshot" if plan.get("snapshot") else "Loaded study (legacy)"}, progress)
