# Verification report

Original release verification date: October 31, 2026 (America/New_York). Python 3.12.14.

**Latest complete release (version 1.2.7): 217 tests passed in 206.71 seconds.**
Ruff, Python compilation and launcher HTTP readiness also passed.

Earlier release results below are retained as history. The audit findings and
remaining limits are described in [AUDIT_REPORT.md](AUDIT_REPORT.md).

## Audit release — November 1, 2026

Version 1.2.6 fixes incomplete cache replacement, missing adjustment-check
overlap, mixed partial price rows, malformed cache metadata, inconsistent
threshold comparisons, relationship-first default ranking and progress cleanup
on errors. Results now carry stock and benchmark acquisition issues/timestamps.
Backtest evidence and experiment plans record the executing application version.

- Before fixes, the baseline suite passed **196 tests**, but the first ten new
  audit regression cases all failed. Sixteen audit cases are now included.
- Final full suite: **212 passed, one upstream warning, in 184.47 seconds**.
  The warning comes from Streamlit's deprecated Pandas `DataFrame.drop(inplace=)`
  call during a row-deletion test. That workflow passed; third-party source was
  not modified. Command: `python -m pytest -q` with an external temporary folder.
- Ruff and compilation of the application package and launchers passed.
- Live Yahoo downloads returned 21 bars each for AAPL, MSFT and SPY for
  January 2–31, 2024. Independent SMA5 and EMA5 calculations matched. Reopening
  those files with downloads blocked made zero price-download calls. Fresh
  Wikipedia membership retrieval returned 503 securities.
- The synthetic 503-stock screen analyzed every history, including all three
  default risk windows. Calculation took 6.586 seconds; cached loading took
  2.478 seconds with zero repeat provider calls. All 503 had finite 252-return
  beta. This check excludes networking and uses fictional returns.
- The actual launcher server path using the existing virtual environment
  returned HTTP 200 and `ok` from Streamlit's health endpoint, then stopped its
  test process. No fresh installation or native browser opening is claimed by
  this audit's smoke check.
- Runtime: Python 3.12. The current direct versions are in
  `constraints-tested.txt`; SciPy is now 1.18.1. Other listed direct versions
  match the original table below.

The audit did not repeat a full live 503-stock price acquisition. Native
Windows/macOS double-click behavior and browser/mobile pixel layout remain
unverified. See the audit report for data limitations and guidance on repairing
previously truncated caches or rerunning affected historical rankings.

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
- No historical constituent feed, archived point-in-time price vintages, alternative authenticated data provider, non-MA indicator or automated trading is bundled. Version 1.2 adds user-supplied membership intervals and a cost-aware daily-bar portfolio simulator, documented below. Fixed-current-universe studies retain survivorship-bias labels.

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

## Research platform update — November 1, 2026

Version 1.2.0 adds automatic successful-screen snapshots, comparisons against
earlier saved dates, rule state changes, saved-date streaks, multi-date cohort
comparisons, long-only next-open portfolio simulation with costs, training
neighborhood/subperiod checks, frozen user-declared holdouts, an experiment
ledger, historical membership CSV support, and weighted-basket concentration,
sector exposure, stock correlations and portfolio risk statistics.

### Executed verification

- Full suite: **149 tests passed in 102.88 seconds**. All existing screening,
  cache, mathematical, chart, risk, export and dashboard cases remain passing.
- **24 new deterministic numerical/storage tests** cover effective membership
  boundaries, removed members and source persistence, overlapping/invalid CSV
  intervals, stable definition hashes, daily snapshot comparison and distinct-date
  streaks, immutable ledger copies, causal per-date signals, historical universe
  changes, next-open adjustment and exact holding horizons, costs, missing data,
  unknown signals, empty qualifier/control/universe dates, failed-screen exits,
  end liquidation, cash-only curves, frozen-rule evaluation and changed-price
  rejection, training-only trials, aligned weighted returns, cash/sector weights,
  HHI/effective holdings, correlations and variance contributions.
- **Four additional Streamlit interaction cases** exercise history across dates,
  basket calculation and settings changes, cohort comparisons, portfolio trades,
  all eight training robustness rows, freeze/evaluate after draft edits, and
  historical-membership selection before/after a removal date. Downloads are
  constructed during these script/widget workflows. Existing single-date
  forward research and applied-screen clipping remain covered.
- A final focused run of the numerical suite was performed after adding
  reproducibility metadata to backtest/basket download archives. Ruff and Python
  compilation also passed after that addition.
- Larger synthetic study: **503 fictional stocks**, **250 study sessions**
  (January 3–December 29, 2023), three MA regression rules and a synthetic
  benchmark. Preparation including synthetic data generation took **3.279 s**.
  Twelve sampled signal dates and three holding horizons produced **18,108
  stock/horizon observation records** in **25.421 s**. The portfolio simulation
  then reused those already-computed review signals: **250 equity rows**, **100
  closed trades**, **0.224 s additional simulation time**. A 10-stock basket
  calculation also completed. These timings exclude real network acquisition;
  the simulated returns are not evidence of an investable strategy's performance.
- Updated Streamlit process: local `/_stcore/health` returned **HTTP 200** with
  body `ok`; the check process was terminated afterward.

### Remaining verification and data limits

No full live-market historical study, real historical-membership feed or
delisting-return dataset was retrieved or verified for this update. The new
research calculations were verified with deterministic synthetic data. Prior
release live-download checks above remain historical evidence of the provider
integration, not proof that every current ticker or study period is available.

Historical membership coverage is supplied and declared by the user. The app
does not validate a vendor's completeness or reconstruct security identities.
Missing held-position prices stop a backtest explicitly. Cohort gaps remain
unavailable. Costs are a daily-bar approximation; tax, impact, spread, liquidity,
shorting and order execution are not modeled. At version 1.2.0, frozen plans
stored definitions and price fingerprints. Version 1.2.1, below, additionally
preserves the loaded inputs; neither version reconstructs original historical
vendor price vintages. A declared holdout does not prove that a person never
examined those dates.

Pixel-level browser/mobile review and native Windows/Mac double-click behavior
remain unverified in this environment. New charts use the same shared styling;
Streamlit script/widget workflows, numerical results, file generation and local
server readiness were verified.

## Portable frozen studies — November 1, 2026

Version 1.2.1 closes the dependency between frozen holdout plans and the mutable
market-data cache. Freezing now saves the actual loaded price bars, fixed
universe and supplied membership intervals as a reusable Parquet/ZIP archive.
The saved plan records its whole-archive checksum, and each file has an internal
checksum. Atomic publication and a per-snapshot file lock preserve existing
archives when multiple processes save the same inputs. The manifest records
app, Python, pandas, NumPy and PyArrow versions.

**Historical research → Saved holdouts** is available without an applied screen
or newly loaded study. It evaluates the archived inputs, prepares a portable
bundle download, and restores bundles through an import button. Missing or
damaged inputs are errors, with no replacement market-data download. A verified
backup can repair a damaged snapshot. Legacy settings-only plans retain their
matching-loaded-data requirement. Imports create a separate ledger entry and
preserve originating-plan/source information.

### Executed verification

- Final complete suite: **168 tests passed in 115.02 seconds**. Ruff and Python
  compilation also passed on the final source.
- **19 new cases** cover exact price/universe/signal round trips, effective
  historical membership and missing observations, input archive reuse, frozen
  evaluation after changing live inputs and reopening storage, identical equity
  and trade results after bundle import into an empty application-data folder,
  metadata/container differences, missing archives, whole-file and internal
  checksum failures, backup repair, invalid configuration/split/format/metadata/
  nonfinite JSON, legacy plans and insufficient holdout sessions.
- The new Streamlit interaction case opens the dashboard with **no applied
  screen** and blocks both Yahoo and demo provider download methods. Saved
  evaluation produces equity/drawdown charts and the prepared bundle bytes
  without invoking either provider. The existing full research workflow also
  passes with the new freeze/evaluate path.
- Larger synthetic snapshot: **503 fictional stocks plus one benchmark**,
  **250 study sessions** with additional warm-up history. The archive was
  **11,982,213 bytes (11.427 MiB)**. Saving took **0.808 s**; restoration including
  causal indicator preparation took **4.642 s**. Reusing identical inputs took
  **0.081 s** and retained one archive. The restored price fingerprint matched.
  These are local timings and synthetic data, not live-market validation.
- Updated Streamlit process readiness: **HTTP 200**, body `ok`; the smoke-test
  process was terminated afterward.

Portability was tested between separate local application-data folders in the
same Python environment, not across a Windows/Mac/Linux or library-version
matrix. The native upload/download dialogs and pixel-level browser layout remain
unverified. Original provider vintage reconstruction and proof that a person
never examined the declared holdout remain unavailable; saved snapshots preserve
the data loaded by this app when frozen. Source/software version information is
recorded, while the bundle does not embed an executable software environment.

## Rule explanations and explicit price updates — November 1, 2026

Version 1.2.2 adds plain-language help for every trend/relationship method and
its controls, with visible calculation/examples, lookback and threshold units,
comparison meanings, group logic, optional consistency filters, reversal lag,
confirmation and acceleration requirements. The MA builder and rule choices
spell out Simple moving average and Exponential moving average while keeping
the existing SMA/EMA JSON and calculation identifiers. Latest-value relationship
rules explicitly disable their unused lookback control.

The earlier price cache already checked saved data first, but normal latest-date
runs could refresh recent bars after six hours. The generic loading label also
did not distinguish disk reads from actual provider calls. Normal Run Screen
and CLI requests now reuse complete saved histories without an age-triggered
refresh. Missing history can still download unless Saved prices only is selected.

The separate **Update prices & run** action refreshes recent prices and repairs
gaps, or explicitly redownloads the full cached span when that scope is selected.
It bypasses in-memory reuse and recent-download timestamps. The action is not
sticky: a later ordinary Run Screen uses saved data even if the full-history
update scope remains selected. Full-history revisions no longer trigger a second
identical full-span download. Actual provider attempts, symbols, ranges and
reasons are shown separately from cache reads.

### Executed verification

- Complete suite: **184 tests passed in 137.18 seconds**. Ruff and Python
  compilation passed on the final source.
- Streamlit tests exercise all **14 trend methods** and **four relationship
  methods**, checking the method controls' help fields and valid screen behavior.
  MA editor/selection tests verify full type names and canonical EMA/SMA codes.
- Provider-call regression tests cover unchanged normal runs, old download
  timestamps, cleared in-memory state, reopening the dashboard against the same
  disk cache, switching cache-only on/off, explicit recent and full updates,
  full-history scope followed by an ordinary Run Screen, and longer-history
  requests that fetch the older extension with overlap.
- Cache tests verify recent updates recheck exactly 21 calendar days, even
  immediately after a successful download; cache-only prevents the call; full
  refresh covers the complete cached span once even with adjusted-price revisions.
  Download diagnostics are empty on genuine saved-price reruns.
- Updated Streamlit readiness returned **HTTP 200**, body `ok`; the smoke-test
  process was stopped afterward.

These new download/caching checks use deterministic fake/demo providers to
verify exact call counts and ranges; no fresh live Yahoo download was claimed.
The S&P 500 membership list has a separate daily cache and is distinct from
price downloads. Native browser pixel layout remains unverified; the actual
Streamlit widget/script runtime, table configuration and chart creation are tested.

## Combined MA builder and stock groups — November 1, 2026

Version 1.2.3 places MA rows and their conditions together in **Moving averages
& trend rules**, followed by **Risk settings**, then optional **Relationships**.
New MA rows receive an editable trend condition. Disabling/removing an MA pauses
dependent conditions, including either side of relationships, and preserves their
parameters. Re-enabling/re-adding it resumes only automatically paused conditions;
manual disabling remains intact. A paused rule can also be reassigned to an
enabled MA. This state is saved in JSON without weakening engine validation.

Stable hidden MA row identities keep references correct when rows are edited,
deleted and added together. Rule references, label tokens and widget state update
on MA changes. Headers show the actual series and method, while rule identifiers
remain stable for exports and historical records. Preset MAs that have no trend
condition keep their existing behavior until explicitly edited/added.

The results table now uses **Select** checkboxes for additive stock selection.
A separate opt-in preview controls the single chart without replacing that
selection. **Selected stocks** provides persistent ticker selection, named groups,
CSV/ticker exports and a button to prepare a custom screening universe. Chart
grid can display current results for selected stocks, including nonmatches.
Tickers outside the applied universe remain selected with unavailable metrics;
selecting/loading a group does not download their prices automatically.

### Executed verification

- Complete final suite: **195 tests passed in 162.29 seconds**. Ruff and Python
  compilation passed. One upstream Streamlit/Pandas deprecation warning appeared
  during a data-editor row deletion; the interaction and resulting calculations
  passed. No third-party dependency source was modified.
- **11 new regression cases** cover dependent-rule pause/resume, relationship
  dependencies, preserved manual disabling and JSON state, complete-token name
  replacement, table-based MA disabling/re-enabling, simultaneous type/period
  changes and additions, deletion plus another row edit/addition in the same
  event, MA dropdown/name synchronization, combined tab order, paused-rule
  reassignment, ticker-based additive selection, local named-group persistence,
  invalid save preservation and group loading/deletion behavior.
- The interaction tests send serialized table-edit events through Streamlit's
  widget runtime, exercising actual edit processing and callbacks. They check
  successive stock checkbox selections, a different chart preview, table-view
  changes, saving/loading a group, selected-stock grid rendering, and screening
  that group while retaining selection.
- A fresh AppTest session reloads saved selected tickers/groups with both Yahoo
  and demo provider download methods blocked. No applied screen or download is
  needed to reopen the selection. Existing price-cache tests remain passing.
- Updated Streamlit readiness returned **HTTP 200**, body `ok`; the smoke-test
  process was stopped afterward.

No new live Yahoo download or native browser pixel review was performed for this
update. Physical table clicks/sorting and platform dialogs remain unverified in
a browser; serialized widget edits, resulting table values, persistent storage,
Plotly creation and calculation workflows were verified in the local runtime.

## Detailed selected-method tooltips — November 1, 2026

Version 1.2.4 replaces the generic Trend method question-mark text with a detailed
explanation of the selected method. Each tooltip includes its purpose, formula,
lookback convention, threshold units, numerical worked example, comparison
examples, interpretation and relevant limits. All 14 trend methods and four
relationship methods are covered. Existing visible explanations remain available.

The tooltip reads the pending selector value so it changes on the same rerun
as the user's selection, rather than one interaction later. Each rule has its
own selector/help state.

Verification: **19 focused Streamlit tests passed in 35.30 seconds**, comprising
the 14 trend-method cases, four relationship cases and an additional immediate
switching/independent-rule case. Checks assert that the actual widget help has
the selected method's title, calculation, worked example and interpretation
sections immediately after selection. The switching case also verifies that
another rule's help and the applied screen remain unchanged. Ruff and Python
compilation passed. This tooltip-only update did not rerun the full numerical
suite; the previous full 195-test result above is retained with its version.

Physical browser hover/popup layout was not verified; these checks exercise the
actual Streamlit script/widget help payload. No new live-market retrieval was
performed for this update.

## Top screening status area — November 1, 2026

Version 1.2.5 reserves a status container directly below the workspace header,
before the Run Screen/Update buttons and tabs. Screening runs render their
download/analysis progress, completion messages and errors into that container.
Execution still occurs after draft controls are collected.

Two focused Streamlit checks passed in 7.47 seconds: normal runs/filter changes
with cached-data reuse, and invalid risk-input recovery preserving the applied
screen. A separate offline AppTest verified the actual status container precedes
the run toolbar in the main layout and contains the completion message. Ruff and
Python compilation passed. No new numerical-suite or native-browser pixel check
was performed for this layout-only update.


## Research cache controls and Yahoo validation — version 1.2.7

Historical research uses the shared cache. Missing history at both ends now
produces separate requests instead of downloading the saved middle. Ordinary
study loading has no routine refresh; saved-only mode blocks downloads, and
Update study prices explicitly refreshes/retries. Activity shows exact requested
ranges and reasons. Single-date outcomes request only through the maximum
60-session horizon instead of all intervening dates through today.

All six research tabs now have explanatory question-mark headings. Saved screen
history supports confirmed deletion of one or several chosen snapshots without
removing prices, presets, applied results, experiments or frozen inputs.
The explorer includes a raw/adjusted/MA comparison table and downloadable CSV.

Executed checks:

- Final complete suite: **217 passed in 206.71 seconds**, with the same upstream
  Streamlit/Pandas row-deletion deprecation warning recorded above.
- Cache/calendar/audit regressions: **41 passed in 14.52 seconds**.
- Final focused research and forward workflows: **six passed in 26.12 seconds**.
  New tests verify two separate missing-edge requests, zero repeated study
  requests, no downloads under saved-only mode, explicit updates, the help
  payload for every research tab, targeted snapshot deletion/updated comparisons,
  preserved experiments/applied results, and a 60-session forward download cap
  with cached reuse on repetition.
- Live production Yahoo retrieval and separate direct Yahoo chart responses
  agreed on 271 Close/Adj Close values per symbol for AAPL and SPY. Independently
  calculated adjusted SMA20, EMA20, daily returns, 63-return Sharpe, beta and
  annualized alpha matched the engine. See [YAHOO_VALIDATION.md](YAHOO_VALIDATION.md)
  for exact inputs, outputs, tolerances and comparison limits. The website's
  proprietary chart/ratio methodology was not established as identical.
- Ruff and Python compilation passed. The existing-environment launcher started
  Streamlit, received HTTP 200 with body `ok`, and stopped the test process.

Native Windows/Mac and browser pixel verification limits from prior releases
remain. Live source checks used two symbols, not the whole S&P 500. Historical
membership and retrospective-adjustment limits remain unchanged.
