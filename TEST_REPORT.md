# Verification report

Original release verification date: October 31, 2026 (America/New_York). Python 3.12.14.

**Latest UI update (version 1.1.1): 121 tests passed.**

The original release results below are retained as history. Risk/performance and UI update verification follow at the end.

## Automated checks

The complete suite passed: **78 tests**. The command was:

~~~bash
python -m pytest -q
~~~

Coverage includes increasing, decreasing and flat MA lines; overall rises with dips; endpoint changes opposing regression slope; exact observation/transition counts; closed-form normalized slopes and R-squared; undefined R-squared; missing/non-finite observations; insufficient warm-up; SMA/EMA and EMA gap resets; adjusted/unadjusted separation; simple/log returns; bullish/bearish crossovers; alignment and separation; acceleration; confirmed turning points; nested AND/OR with unavailable branches; historical clipping; cache reuse/extensions/revisions/failures; symbol aliases; preset JSON and file lifecycle; CSV/Excel/ZIP generation; chart window/fit data; and Streamlit interactions.

The Streamlit tests exercise actual script/widget reruns: apply-button behavior, filter changes without another download, rule methods, duplicate/disable/remove, relationship and nested-group controls, example loading, bearish alignment, custom tickers, benchmark mode, 20-chart pagination, export preparation and separate forward research.

The full live run exposed an all-missing cache-frame dtype error that the earlier synthetic tests did not cover. Numeric coercion was added before calculations, with regression tests for a completely unavailable ticker and a 120-ticker network failure. Unavailable symbols now complete with an explicit insufficient-data status.

Python compilation and Ruff checks also passed.

## Executed workflows

| Check | Observed result |
| --- | --- |
| Offline CLI, January 16, 2024 | 24 synthetic stocks analyzed; 7 passed the default three-MA screen |
| Synthetic 503-stock screen | 503 analyzed, no insufficient histories; approximately 3.617 seconds for the calculation engine, excluding generation/download |
| Live membership retrieval | 503 current securities retrieved from Wikipedia |
| Live sample Yahoo download | AAPL and BRK-B, January 2–31, 2024: 21 daily bars each, with separate raw OHLCV and adjusted close |
| Live full-universe acquisition | Requested all 503 current securities; Yahoo rate limits left 383 successfully cached histories and 120 unavailable histories |
| Final source, full cached-live screen | Screen date 2026-10-30; 503 requested, 383 analyzed, 120 insufficient, 71 passing; approximately 3.330 seconds excluding download |
| Streamlit process and HTTP readiness | Server started; its local /_stcore/health returned HTTP 200 with body “ok”; health-check process was stopped afterward |
| Plotly chart data | Exact highlighted observation counts and dates, fitted values and acceleration-window separation verified |
| Export artifacts | Excel and historical ZIP bytes generated and read back successfully |

Membership retrieval timestamp: 2026-11-01T03:39:44.539802+00:00. Successful live screening used the data already downloaded during the rate-limited acquisition. No assertion is made that all 503 live price downloads succeeded. The final cached-live rerun used the corrected source and completed without a calculation exception.

## Verification limits

- A separate real-browser rendering check could not connect to this environment's isolated local server. A local Chromium installation attempt also failed because the browser download did not supply a valid archive. Pixel layout, native file-download prompts and physical canvas row clicks have **not** been verified in a browser. Streamlit script interactions, Plotly figure data, export bytes and server HTTP readiness were verified independently.
- Only Python 3.12 was executed here. Python 3.11+ is the declared supported range; a multi-version and Windows/macOS execution matrix was not run.
- The complete live universe with every quote available could not be verified under Yahoo's current rate limits. Partial availability is reported explicitly and has deterministic regression coverage.
- Historical membership, archived point-in-time price vintages, alternative authenticated data providers, non-MA indicators, transaction-cost/portfolio backtesting and automated trading are not supplied. Historical screens use current constituents and retrospectively adjusted price history, with the documented bias labels.

## Direct dependency versions used

| Package | Version |
| --- | --- |
| streamlit | 1.66.1 |
| pandas | 3.1.0 |
| numpy | 2.5.4 |
| yfinance | 1.7.0 |
| plotly | 7.1.0 |
| scipy | 1.17.0 |
| pyarrow | 26.0.0 |
| pandas-market-calendars | 5.6.0 |
| pytest | 9.2.0 |

Exact direct dependency versions are also recorded in constraints-tested.txt. See README.md for installation, controls, formula definitions, caching policy and operational limits.

## Double-click launcher update

Added START_WINDOWS.bat, START_MAC.command, bootstrap.py and START_HERE.txt.
The shared bootstrap created a fresh private environment, installed the declared
dependencies and started Streamlit; HTTP readiness returned 200. A subsequent
smoke run verifies setup reuse. Mac shell syntax and Python compilation/lint
were checked. Native Windows and macOS double-click behavior and automatic
browser opening remain unverified in this environment. Python 3.11+ must be
installed once before using either launcher.

## Risk and performance update — November 1, 2026

Version 1.1.0 adds performance settings, a dedicated stock panel, comparison
across custom lookbacks, annualized/daily Sharpe, Sortino, excess-return beta
and alpha, volatility, downside deviation, drawdown, Calmar, information ratio,
tracking error, correlation, regression R-squared, CAGR and return statistics.
The benchmark uses the existing incremental cache; settings are saved in JSON.
Exports include the metrics, settings, source dates, observation counts and
benchmark history. The chart grid can rank these metrics at a chosen horizon.

### Executed verification

- Complete suite: **120 tests passed in 43.83 seconds**, including all 78
  original cases and 42 new parameterized mathematical and UI cases.
- Mathematical cases use independently specified means, variances, exact
  beta/alpha relationships and compounded returns. Coverage includes effective
  annual risk-free conversion, custom Sortino targets, downside normalization
  over all days, negative beta/alpha, constant returns, missing or insufficient
  stock/benchmark history, same-date alignment, rolling/scalar agreement,
  historical no-lookahead, JSON compatibility, cache invalidation and exports.
- Streamlit interaction tests cover custom horizons/benchmarks/rates/targets,
  metric selection, explicit Apply behavior, no repeated price downloads for
  rate changes, downloading only a new benchmark, disabled analytics, missing
  benchmarks, performance charts, grid ranking and invalid-input recovery.
- Live Yahoo retrieval and the CLI completed for AAPL, MSFT and BRK-B, plus
  SPY as the benchmark, with screening date January 16, 2024. All three had
  finite 63/126/252-return Sharpe, 252-return beta and annualized alpha. These
  were historical data downloads; no full 503-stock live risk run is claimed.
- A synthetic **503-stock** screen, with all three default risk horizons and
  complete benchmark data, took **6.380 seconds** excluding acquisition.
  All 503 stocks had nonmissing Sharpe values at 63/126/252 returns and
  nonmissing 252-return beta and alpha.
- Updated Streamlit process readiness returned HTTP 200 from its health
  endpoint. Python compilation and Ruff checks passed.

Native Windows/Mac launcher behavior and pixel-level browser rendering remain
unverified here. Streamlit widget/script interactions, Plotly figure creation,
server readiness and exported bytes were checked. Historical statistics use
current constituents and retrospectively adjusted data, as described in README.
The risk-free input is an explicit constant annual assumption, not a live rate.

## UI polish update — November 1, 2026

Version 1.1.1 applies a shared light/navy/teal design, a branded workspace
header and sidebar, clearer summary cards, focused builder tabs, compact
Overview/Trend details/Risk comparison/Custom table views, friendly column
labels, grouped export controls and consistent Plotly chart styling. Detailed
calculation audits remain expandable, and all analytical controls are retained.
No screening or risk/return formulas changed.

Verification completed:

- Full suite: **121 tests passed in 44.48 seconds**.
- The new table-view interaction test switches views and verifies that risk
  horizons and MA details remain available without replacing the applied run.
- Existing interactions cover rules, groups, presets, risk settings, grid
  pagination, charts and exports. Chart tests retain exact highlighted dates,
  values, observations and acceleration windows.
- Focused table-view and risk-settings checks were repeated after the final
  header-format adjustments.
- Ruff, Python compilation and updated Streamlit HTTP readiness succeeded.
- The separate cloud browser could not reach the isolated local server
  (connection refused), so pixel-level visual review and mobile rendering
  remain unverified. Native chart controls and responsive styling are provided;
  interaction checks use Streamlit's script/widget test runtime.
