from io import BytesIO
import hashlib
import json
from pathlib import Path
import zipfile

import numpy as np
import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest

from trend_screener.demo import DemoProvider
from trend_screener.history import HistoryStore
from trend_screener.membership import MembershipHistory
from trend_screener.models import MovingAverage, Rule, ScreenConfig
from trend_screener.providers import YFinanceProvider
from trend_screener.risk import RiskSettings
from trend_screener.robustness import (
    evaluate_frozen_holdout, export_frozen_bundle, freeze_study, import_frozen_bundle,
)
from trend_screener.snapshots import SnapshotStore
from trend_screener.studies import BacktestSettings, StudyEngine, frozen_plan
from trend_screener.universe import custom_universe


@pytest.fixture
def study(make_bars):
    cfg = ScreenConfig(moving_averages=[MovingAverage(period=3)],
                        rules=[Rule(id="rising", ma="SMA3", lookback=3)],
                        risk=RiskSettings(enabled=False),
                        data_settings={"source": "Synthetic demo (offline)"})
    prices = {"A": make_bars(100 * 1.01**np.arange(70)),
              "B": make_bars(100 * .99**np.arange(70)),
              "SPY": make_bars(100 * 1.002**np.arange(70))}
    dates = prices["A"].index
    universe = custom_universe(["A", "B"])
    universe["sector"] = ["Tech", "Health"]
    return StudyEngine(prices, universe, cfg, dates[10].date(), dates[-1].date())


def freeze(store, study):
    return freeze_study(store, study.config, BacktestSettings(max_positions=1, holding_sessions=5),
                         study, study.dates[30].date(), {"source": "Synthetic demo (offline)"})


def rewrite_zip(raw, transform):
    with zipfile.ZipFile(BytesIO(raw)) as source:
        files = {name: source.read(name) for name in source.namelist()}
    transform(files)
    out = BytesIO()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, data in files.items():
            archive.writestr(name, data)
    return out.getvalue()


def test_input_snapshot_roundtrip_and_deduplication(study, tmp_path):
    snapshots = SnapshotStore(tmp_path)
    descriptor = snapshots.save(study, {"source": "synthetic"})
    assert snapshots.save(study, {"source": "synthetic"}) == descriptor
    assert len(list(tmp_path.glob("*.zip"))) == 1
    restored = snapshots.load(descriptor, study.config)
    assert restored.fingerprint == study.fingerprint
    pd.testing.assert_frame_equal(restored.universe, study.universe)
    for ticker in study.prices:
        pd.testing.assert_frame_equal(restored.prices[ticker], study.prices[ticker])
    pd.testing.assert_frame_equal(restored.signals(study.dates[5]), study.signals(study.dates[5]))
    study.config.rules[0].threshold = 2.0
    assert snapshots.save(study, {"source": "synthetic"}) == descriptor  # Rules do not duplicate input bars.


def test_snapshot_preserves_effective_membership_and_missing_values(study, tmp_path):
    cutoff = study.dates[20].date()
    membership = MembershipHistory.from_csv(
        f"ticker,start_date,end_date,sector\nA,2020-01-01,{cutoff},Tech\nB,{cutoff},,Health\n",
        study.start, study.end, "Synthetic intervals")
    prices = {ticker: frame.copy() for ticker, frame in study.prices.items()}
    prices["B"].loc[study.dates[25], "adj_close"] = np.nan
    original = StudyEngine(prices, study.universe, study.config, study.start, study.end, membership)
    snapshots = SnapshotStore(tmp_path)
    restored = snapshots.load(snapshots.save(original), original.config)
    assert restored.membership.digest == membership.digest
    assert restored.universe_at(study.dates[0]).ticker.tolist() == ["A"]
    assert restored.universe_at(study.dates[20]).ticker.tolist() == ["B"]
    assert pd.isna(restored.prices["B"].loc[study.dates[25], "adj_close"])
    assert restored.signals(study.dates[25]).status.tolist() == ["INSUFFICIENT"]


def test_frozen_holdout_survives_changed_live_data_and_restart(study, tmp_path, monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("No provider call is allowed for archived evaluation")
    monkeypatch.setattr(YFinanceProvider, "download", forbidden)
    monkeypatch.setattr(DemoProvider, "download", forbidden)
    store = HistoryStore(tmp_path)
    identifier = freeze(store, study)
    _, original = evaluate_frozen_holdout(store, identifier)
    study.prices["A"].loc[:, "adj_close"] = 1
    study.fingerprint = "a changed live cache"
    study.config.rules[0].threshold = 1e9
    reopened = HistoryStore(tmp_path)
    _, restored = evaluate_frozen_holdout(reopened, identifier, study)
    pd.testing.assert_frame_equal(original.equity, restored.equity)
    pd.testing.assert_frame_equal(original.trades, restored.trades)
    assert len(restored.trades) > 0
    assert reopened.list_experiments().kind.eq("holdout_evaluation").sum() == 2


def test_portable_bundle_reproduces_results_in_an_empty_installation(study, tmp_path):
    original_store = HistoryStore(tmp_path / "original")
    identifier = freeze(original_store, study)
    _, original = evaluate_frozen_holdout(original_store, identifier)
    bundle = export_frozen_bundle(original_store, identifier)
    assert bundle.startswith(b"PK")
    destination = HistoryStore(tmp_path / "new_installation")
    imported = import_frozen_bundle(destination, bundle)
    assert imported != identifier
    plan = destination.experiment(imported)["plan"]
    assert plan["imported_from"]["origin_id"] == identifier
    assert plan["holdout_claim"].startswith("User-declared")
    _, restored = evaluate_frozen_holdout(destination, imported)
    pd.testing.assert_frame_equal(original.equity, restored.equity)
    pd.testing.assert_frame_equal(original.trades, restored.trades)
    # Restoring the same bundle creates a distinct recorded plan and reuses its price archive.
    import_frozen_bundle(destination, bundle)
    assert len(list((destination.path.parent / "snapshots").glob("*.zip"))) == 1


def test_existing_snapshot_with_a_different_container_timestamp_is_reused(study, tmp_path):
    source = HistoryStore(tmp_path / "a")
    frozen = freeze(source, study)
    destination = HistoryStore(tmp_path / "b")
    snapshot_store = SnapshotStore(destination.path.parent / "snapshots")
    desc = source.experiment(frozen)["plan"]["snapshot"]
    raw = SnapshotStore(source.path.parent / "snapshots").read(desc)
    def edit_timestamp(files):
        manifest = json.loads(files["manifest.json"])
        manifest["created_at"] = "2026-11-01T00:00:00+00:00"
        files["manifest.json"] = json.dumps(manifest).encode()
    changed = rewrite_zip(raw, edit_timestamp)
    snapshot_store.path(desc["id"]).write_bytes(changed)
    imported = import_frozen_bundle(destination, export_frozen_bundle(source, frozen))
    checked = destination.experiment(imported)["plan"]["snapshot"]
    assert checked["sha256"] == hashlib.sha256(changed).hexdigest()
    evaluate_frozen_holdout(destination, imported)


def test_missing_archive_never_falls_back_to_live_data(study, tmp_path):
    store = HistoryStore(tmp_path)
    identifier = freeze(store, study)
    descriptor = store.experiment(identifier)["plan"]["snapshot"]
    SnapshotStore(tmp_path / "snapshots").path(descriptor["id"]).unlink()
    with pytest.raises(ValueError, match="snapshot is missing"):
        evaluate_frozen_holdout(store, identifier, study)


def test_corrupt_snapshot_rejected_before_evaluation(study, tmp_path):
    store = HistoryStore(tmp_path)
    identifier = freeze(store, study)
    descriptor = store.experiment(identifier)["plan"]["snapshot"]
    path = SnapshotStore(tmp_path / "snapshots").path(descriptor["id"])
    path.write_bytes(b"invalid zip")
    with pytest.raises(ValueError, match="checksum"):
        evaluate_frozen_holdout(store, identifier, study)


def test_importing_verified_backup_repairs_corrupted_snapshot(study, tmp_path):
    store = HistoryStore(tmp_path)
    identifier = freeze(store, study)
    bundle = export_frozen_bundle(store, identifier)
    descriptor = store.experiment(identifier)["plan"]["snapshot"]
    path = SnapshotStore(tmp_path / "snapshots").path(descriptor["id"])
    path.write_bytes(b"damaged")
    imported = import_frozen_bundle(store, bundle)
    assert path.read_bytes().startswith(b"PK")
    evaluate_frozen_holdout(store, imported)
    evaluate_frozen_holdout(store, identifier)


def test_internal_file_checksums_are_checked(study, tmp_path):
    snapshots = SnapshotStore(tmp_path)
    desc = snapshots.save(study)
    def corrupt(files):
        price = next(name for name in files if name.startswith("prices/"))
        files[price] += b"damaged"
    raw = rewrite_zip(snapshots.read(desc), corrupt)
    changed = {**desc, "sha256": hashlib.sha256(raw).hexdigest()}
    with pytest.raises(ValueError, match="file checksum"):
        snapshots.decode(raw, changed, study.config)


@pytest.mark.parametrize("invalid", ["config", "split", "checksum", "format", "junk", "metadata", "nan"])
def test_invalid_bundle_does_not_publish_inputs_or_plan(study, tmp_path, invalid):
    source = HistoryStore(tmp_path / "original")
    identifier = freeze(source, study)
    raw = export_frozen_bundle(source, identifier)
    def damage(files):
        doc = json.loads(files["plan.json"])
        if invalid == "config":
            doc["plan"]["config"]["moving_averages"][0]["period"] = 0
        elif invalid == "split":
            doc["plan"]["split"] = doc["plan"]["end"]
        elif invalid == "checksum":
            files["snapshot.zip"] += b"corruption"
        elif invalid == "format":
            doc["format_version"] = 999
        elif invalid == "metadata":
            doc.pop("origin_id")
        elif invalid == "nan":
            doc["plan"]["metadata"]["invalid"] = float("nan")
        files["plan.json"] = json.dumps(doc).encode()
    raw = b"bad archive" if invalid == "junk" else rewrite_zip(raw, damage)
    destination = HistoryStore(tmp_path / "destination")
    with pytest.raises(ValueError):
        import_frozen_bundle(destination, raw)
    assert destination.list_experiments().empty
    assert not list((destination.path.parent / "snapshots").glob("*.zip"))


def test_legacy_plan_still_requires_matching_loaded_data(study, tmp_path):
    store = HistoryStore(tmp_path)
    identifier = store.record_experiment("frozen_holdout", frozen_plan(
        study.config, BacktestSettings(), study, study.dates[30].date()))
    with pytest.raises(ValueError, match="Legacy plan"):
        evaluate_frozen_holdout(store, identifier)
    with pytest.raises(ValueError, match="no saved price snapshot"):
        export_frozen_bundle(store, identifier)
    evaluate_frozen_holdout(store, identifier, study)


def test_too_short_holdout_is_rejected_before_snapshot_write(study, tmp_path):
    store = HistoryStore(tmp_path)
    with pytest.raises(ValueError, match="two trading sessions"):
        freeze_study(store, study.config, BacktestSettings(), study, study.dates[-2].date())
    assert store.list_experiments().empty
    assert not (tmp_path / "snapshots").exists()


def test_saved_holdout_buttons_work_without_run_or_download(study, tmp_path, monkeypatch):
    monkeypatch.setenv("SCREENER_HOME", str(tmp_path))
    store = HistoryStore(tmp_path / "research")
    frozen = freeze(store, study)
    def forbidden(*args, **kwargs):
        raise AssertionError("Dashboard must not download prices for saved studies")
    monkeypatch.setattr(YFinanceProvider, "download", forbidden)
    monkeypatch.setattr(DemoProvider, "download", forbidden)
    app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / "app.py"), default_timeout=60).run()
    assert not app.exception and not app.error
    assert app.selectbox(key="archived_holdout_choice").value == frozen
    app.button(key="saved_holdout_run").click().run()
    assert not app.exception and not app.error
    assert app.session_state["saved_holdout_result"][0] == frozen
    assert len(app.get("plotly_chart")) == 2
    app.button(key="saved_holdout_prepare").click().run()
    assert app.session_state["saved_holdout_bundle"][1].startswith(b"PK")
    assert not app.exception and not app.error
