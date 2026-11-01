from datetime import date
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from trend_screener.cache import PriceCache
from trend_screener.demo import DemoProvider
from trend_screener.engine import ScreenRun
from trend_screener.history import HistoryStore
from trend_screener.presets import builtins
from trend_screener.research_dashboard import RESEARCH_HELP
import pandas as pd


def test_both_missing_ends_do_not_redownload_saved_middle(tmp_path, fake_provider):
    cache = PriceCache(tmp_path, fake_provider)
    cache.get_many(['AAA'], date(2023, 1, 3), date(2024, 1, 31))
    result = cache.get_many(['AAA'], date(2022, 1, 3), date(2025, 1, 31))
    requests = fake_provider.calls[1:]
    assert len(requests) == 2
    assert requests[0][2] < date(2023, 2, 1)
    assert requests[1][1] > date(2024, 1, 1)
    assert not result.errors
    calls = len(fake_provider.calls)
    cache.get_many(['AAA'], date(2022, 1, 3), date(2025, 1, 31))
    assert len(fake_provider.calls) == calls


def test_delete_snapshots_is_targeted_and_updates_comparisons(tmp_path):
    store = HistoryStore(tmp_path)
    cfg = builtins()[0]
    frame = pd.DataFrame([{'ticker': 'AAA', 'status': 'PASS'}])
    first = store.save_screen(ScreenRun(cfg, date(2024, 1, 2), frame))
    second = store.save_screen(ScreenRun(cfg, date(2024, 1, 3), frame))
    ledger = store.record_experiment('test', {'keep': True})
    assert store.compare(second)[0]['id'] == first
    assert store.delete_screens([first, first, "unknown' OR 1=1 --"]) == 1
    assert store.compare(second)[0] is None
    assert store.experiment(ledger)['plan'] == {'keep': True}
    assert store.screen(second)['id'] == second
    with pytest.raises(ValueError):
        store.screen(first)


@pytest.fixture
def dashboard(tmp_path, monkeypatch):
    monkeypatch.setenv('SCREENER_HOME', str(tmp_path))
    cfg = builtins()[0]
    cfg.data_settings = {'source': 'Synthetic demo (offline)', 'time_mode': 'Historical date',
                         'requested_date': '2024-01-16', 'period': '1 year'}
    app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / 'app.py'), default_timeout=60)
    app.session_state['draft'], app.session_state['editor_version'] = cfg, 0
    app.run().button(key='run_screen').click().run()
    assert not app.exception
    return app


def test_study_cache_only_update_and_tab_help(dashboard, monkeypatch):
    app, calls = dashboard, []
    original = DemoProvider.download
    def download(provider, tickers, start, end):
        calls.append((tickers, start, end))
        return original(provider, tickers, start, end)
    monkeypatch.setattr(DemoProvider, 'download', download)
    app.date_input(key='study_start').set_value(date(2023, 10, 2)).run()
    app.button(key='study_load').click().run()
    assert not app.exception and not app.error
    assert calls  # Additional warm-up before the original screen's history is needed.
    calls.clear()
    app.button(key='study_load').click().run()
    assert not app.exception and not app.error and not calls
    assert any('No price downloads were requested' in c.value for c in app.caption)
    app.checkbox(key='study_cache_only').check().run()
    app.date_input(key='study_start').set_value(date(2022, 10, 3)).run()
    app.button(key='study_load').click().run()
    assert not app.exception and not calls
    assert app.button(key='study_update').disabled
    app.checkbox(key='study_cache_only').uncheck().run()
    app.button(key='study_update').click().run()
    assert not app.exception and not app.error and calls
    for title, explanation in RESEARCH_HELP.items():
        assert any(h.value == title and h.proto.help == explanation for h in app.subheader)


def test_delete_snapshot_widget_keeps_applied_screen(dashboard, tmp_path):
    app = dashboard
    applied = app.session_state['run']
    assert app.button(key='history_delete').disabled
    app.checkbox(key='history_delete_confirm').check().run()
    app.button(key='history_delete').click().run()
    assert not app.exception and not app.error
    assert HistoryStore(tmp_path / 'research').list_screens().empty
    assert app.session_state['run'] is applied


def test_single_date_download_stops_at_longest_requested_horizon(dashboard, monkeypatch):
    from trend_screener.calendar import sessions
    calls = []
    original = DemoProvider.download
    def download(provider, tickers, start, end):
        calls.append((start, end))
        return original(provider, tickers, start, end)
    monkeypatch.setattr(DemoProvider, 'download', download)
    app = dashboard
    app.checkbox(key='enable_research').check().run()
    next(b for b in app.button if b.label == 'Calculate 5 / 20 / 60-session forward returns').click().run()
    assert not app.exception and not app.error
    expected = sessions(date(2024, 1, 16), date(2024, 6, 1))[60].date()
    assert calls and all(end == expected for _, end in calls)
    calls.clear()
    next(b for b in app.button if b.label == 'Calculate 5 / 20 / 60-session forward returns').click().run()
    assert not app.exception and not calls
