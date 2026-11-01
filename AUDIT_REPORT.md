# Functional and calculation audit — version 1.2.6

Audit date: November 1, 2026. Reviewed baseline: version 1.2.5, commit
`6c11e2e89beda0bd936ce3257f3dd8df98e7c69f`. The findings below are fixed in
version 1.2.6. This is a source review and executed regression audit, not a
guarantee that every possible provider response or platform interaction is covered.

## Findings and fixes

| Priority | Confirmed problem | Resulting behavior in 1.2.6 |
| --- | --- | --- |
| High | A truncated full-history response could replace a longer saved history. A reproducible case reduced 271 usable rows to five while retaining metadata claiming the full range. This affected both explicit full updates and corporate-action revision refreshes. | A full replacement must preserve every previously available saved price cell at its session. Incomplete replacements are rejected; saved history and its successful-download timestamp remain intact, with an explicit error. |
| High | A missing overlap could bypass adjustment-revision detection. Old adjusted prices with a factor of 1 and new prices with a factor of 0.8 could enter one history. Cell-level merging could also splice fields from incomplete rows. | No usable adjusted-price overlap triggers full-span revalidation. Incomplete full responses are rejected. Incremental updates replace whole usable rows, rather than combining missing price fields across downloads. |
| Medium | Malformed coverage dates or successful-download timestamps could abort a screen. Discarding only damaged metadata could also lead to replacing a long retained history with the shorter newly requested period. | Metadata and bar schema/index are checked per ticker. Usable bars are retained, and missing/bad metadata requires revalidation of their entire saved span. Other tickers continue without an unnecessary download. |
| Medium | Floating-point thresholds could disagree: a calculated 2% change could satisfy both `== 2` and `> 2`. An absolute equality tolerance could also classify a tiny nonzero slope as both zero and positive/negative. | All six operators consistently handle nonzero near-equality using relative tolerance 1e-10 and zero absolute tolerance. Positive/negative comparisons against zero retain their direction. |
| Medium | Relationship-first presets selected metrics from a one-observation relationship, leaving default slope-ranking columns empty even when later trend rules had valid slopes. Historical portfolio selection could consequently fall back to ticker order. | Shared metric selection prefers valid enabled trend rules with slope metrics. The screening engine and historical study engine use the same selection. Relationship metrics are only a fallback. |
| Low | Failed screen updates and failed research loads could leave the progress bar visible. | Both workflows clear progress in `finally` blocks. A failed update keeps the previously applied screen available. |

Data failures that retain saved history are now prominent in the top status area.
Result tables, CSV/Excel downloads and saved screen results include
`price_data_issue` and `last_price_download_utc`. With risk analytics enabled,
they also include `benchmark_data_issue` and `benchmark_last_download_utc`;
a benchmark-only failure therefore remains visible in exported stock results.
These download timestamps identify successful acquisition, not the latest session
date or proof that a vendor's values are correct.

## Review scope and executed checks

The review covered provider parsing and adjusted-price separation, constituent
and symbol handling, cache planning/replacement, indicator warm-up, MA/trend
formulas, rule comparisons and groups, relationship rules, ranking, risk metrics,
historical clipping, research signals/provenance, snapshots, launchers, and the
main dashboard workflows. Mathematical expectations were checked against
synthetic fixtures and manual calculations, not screenshots.

- Baseline: **196 tests passed** before these fixes. The first ten newly added
  audit regression cases all failed against that baseline, reproducing defects
  that the existing suite did not catch. The audit file now has 16 cases.
- Final release suite: **212 tests passed in 184.47 seconds**, with one upstream
  Streamlit/Pandas deprecation warning in a passing row-deletion test. Ruff and
  Python compilation passed. See [TEST_REPORT.md](TEST_REPORT.md) for commands,
  runtime versions and retained earlier verification results.
- New coverage includes full-refresh truncation, adjustment revisions, missing
  overlap, partially missing rows, four malformed metadata variants, retained
  full-span recovery, all threshold operators, benchmark-only diagnostics,
  screening/research ranking agreement, failure cleanup, and visible retained-data
  warnings. Future OHLC/adjusted prices multiplied by 1,000 leave earlier
  screen results, risk metrics and historical signals unchanged for both SMA37
  and EMA37.
- Live Yahoo sample: **AAPL, MSFT and SPY**, January 2–31, 2024, returned **21
  bars each**, with no reported retrieval errors. SMA5 matched a manual last-five
  arithmetic mean. EMA5 matched an independent recurrence with alpha = 2/6,
  initialized at the first retrieved adjusted close. This verifies the engine's
  stated same-window EMA convention; it is not a comparison with an external
  chart seeded from a longer history.
- Reopening that saved live sample with downloads blocked required **zero price
  downloads**. A fresh constituent retrieval returned **503 securities** from
  Wikipedia, timestamp `2026-11-01T07:17:00.233210+00:00`.
- A deterministic **503-stock synthetic screen**, with the three default MA
  rules, a benchmark and 63/126/252-return risk horizons, analyzed all 503
  histories; all had finite 252-return beta. Indicator/rule/risk calculation took
  approximately **6.586 seconds**; cached loading took **2.478 seconds**, with
  **zero repeat download calls**. The 190 qualifying fictional stocks are test
  results, not evidence of strategy performance. Timings exclude live networking.
- Actual Streamlit widget reruns exercise the primary builders, applied settings,
  charts, multi-stock selection/groups, exports, research and cache controls.
  The launcher also started the local Streamlit server and received **HTTP 200**
  with body `ok` from its health endpoint, then stopped the test process.

## What existing users should do

1. Update the source to 1.2.6 and keep the existing `.screener` folder, which
   contains cached prices, presets and saved research. Normal runs continue to
   use saved prices first; explicit updates remain separate actions.
2. If an earlier incomplete update has already shortened a ticker's cache, use
   **Price update options → Update scope → Full price history**, then
   **Update prices & run**, for the affected ticker. Request an earlier start if
   needed. This release prevents further loss; it cannot recreate deleted bars
   without a successful provider response.
3. Rerun earlier historical portfolio studies that used default slope ranking
   with relationship-first presets, including Strong Bullish Alignment. The
   corrected ranking can change holdings and returns. Also rerun work dependent
   on affected threshold boundaries or damaged price caches.
4. Frozen input archives preserve data and settings, not the executing Python
   implementation. New backtest evidence and experiment records include
   `app_version` so calculations can be associated with the software version.

## Remaining gaps and verification limits

- This audit downloaded a small live price sample and the constituent list; it
  did **not** acquire every current constituent's prices. Yahoo throttling,
  corrections and missing symbols remain operational constraints. Saved prices
  can be older than the vendor's current vintage until explicitly updated;
  the app exposes their dates and download issues.
- Past screens with today's membership retain **survivorship bias**. Membership
  intervals can be supplied by the user, but no verified historical membership,
  complete delisting returns or security-identity database is bundled. Current
  retrospectively adjusted history is not an archived point-in-time vendor feed.
- Native Windows/macOS double-click operation, physical browser/table clicks,
  hover layout and mobile pixels have not been verified here. Streamlit's actual
  script/widget runtime, Plotly data, generated downloads and local server
  readiness were verified. The launchers require Python 3.11+; a standalone
  executable with Python bundled is not supplied. The executed runtime here
  was Python 3.12.
- Research portfolios use daily bars and explicit cost assumptions. Taxes,
  execution impact, capacity, live orders and a complete delisting model are
  outside the implementation. User-declared holdouts cannot prove they were
  never inspected.
- The CLI takes its source/universe/date from explicit command-line options, as
  documented; loading rule JSON does not reproduce every sidebar setting by
  itself. It is an alternative execution interface, not the dashboard workflow.

No additional release-blocking defect was reproduced in the completed checks.
Future failures should still be investigated using their exact preset, dates,
provider diagnostics and software version.
