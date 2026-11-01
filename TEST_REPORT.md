# Verification report

Verification date: October 31, 2026 (America/New_York). Python 3.12.14.

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
