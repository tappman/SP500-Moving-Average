# MA Trend Lab — S&P 500 Moving Average Screener

A complete Python/Streamlit research application for finding stocks whose moving-average lines are rising over your chosen trading-day windows. Define arbitrary SMA/EMA periods, combine independent rules, and inspect the actual values and fitted trendlines that produced each result.

## Start the dashboard

**Double-click option:** extract the ZIP and open **START_WINDOWS.bat** on Windows
or **START_MAC.command** on Mac. Install Python 3.11+ once first. The launcher
creates the environment, installs packages on its first run, and opens the
dashboard in your browser automatically. Later launches reuse the setup.
See **START_HERE.txt**. These are launch scripts; a standalone EXE/Mac app is
not bundled. Native Windows/Mac double-click behavior has not been verified here.

The manual setup below is also available.

Install **Python 3.11 or newer**, extract this project, and open a terminal in the extracted **sp500-trend-screener** folder.

**macOS / Linux**

~~~bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python -m streamlit run app.py
~~~

**Windows Command Prompt**

~~~bat
py -3 -m venv .venv
.venv\Scripts\activate
python -m pip install -r requirements.txt
python -m streamlit run app.py
~~~

**Windows PowerShell** can use the virtual environment directly:

~~~powershell
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m streamlit run app.py
~~~

Streamlit prints a local browser address, normally http://localhost:8501. Keep the terminal open. Stop with **Ctrl+C**. On subsequent launches, activate the same environment and run:

~~~bash
python run_dashboard.py
~~~

For an occupied port, use:

~~~bash
python run_dashboard.py --server.port 8502
~~~

Installation needs Internet access. Once installed, **Synthetic demo (offline)** runs the entire dashboard without external data or API keys. Live data additionally needs Yahoo Finance and a constituent source. The optional constraints-tested.txt records exact direct dependencies used in the Python 3.12 verification environment; requirements.txt allows compatible versions for other supported Python releases.

## First screen: MA20 rising over 10 observations

1. In the sidebar choose **Live Yahoo Finance** and **S&P 500 (current constituents)**. For an immediate offline trial, choose **Synthetic demo (offline)**.
2. In **Build screen → Moving averages & trend rules**, add/edit MA rows. Each has type, period, enabled status and chart visibility. SMA7, SMA37, EMA63 and SMA300 are valid examples. Newly added MAs receive an editable rising-slope condition underneath them. There is no preset-period or rule-count restriction.
3. Keep SMA20 enabled. In the same combined tab, disable the two other MAs or disable/remove their individual conditions.
4. Expand the SMA20 rule below its MA heading. Choose **Regression: normalized slope**, **10 observations**, comparison **>**, threshold **0**.
5. Click **Run Screen**, then open **Results**.
6. Tick **Select** beside result stocks to collect several at once. To inspect one, enable **Preview a stock below the table** and choose its ticker, or use **Stock explorer**. Select a rule to highlight. The shaded segment, dashed regression fit and information panel explain exactly why it passed. Previewing does not change your stock collection.
7. Change a threshold and run again. Loaded prices and unchanged indicators are reused.

Each trend-rule control has a help tooltip. The selected method also shows its
calculation and an example beside the settings, with separate explanations for
lookback, comparison, threshold units, reversal/acceleration options and optional
consistency filters. The MA type selector spells out **SMA — Simple moving
average** and **EMA — Exponential moving average**. Saved JSON and calculation
columns keep the stable `SMA`/`EMA` codes, such as `SMA20` and `EMA20`.

For “MA20 increased on at least 8 of the last 10 days,” choose **Positive transition count**, lookback **10**, comparison **>=**, threshold **8**. This requires **11 MA observations**. Combine it with a positive-slope rule, or use the regression rule's **Also require mostly rising** control.

## Dashboard features

| Area | Controls and behavior |
| --- | --- |
| Data settings | Current S&P 500, sector, custom tickers, one stock, or ^GSPC benchmark; 3/6 months, 1/2/3/5/10 years, custom dates; latest or historical session; MA price basis; simple/log returns |
| MA builder + trend rules | Combined tab; add/delete rows, arbitrary SMA/EMA periods, automatic new conditions, dependent-rule pausing/resuming and synchronized names |
| Trend rules | Independent MA, method, lookback, operator, threshold, enabled status; duplicate/remove controls |
| Boolean groups | Root AND/OR and nested AND/OR groups; configurable parents; cycles rejected; empty groups ignored |
| Relationships | Any MA pair or price/MA comparison; bullish/bearish alignment helper; recent crossovers; widening/narrowing absolute separation |
| Results | Sortable/selectable table, visible-column controls, per-rule metrics, counts, diagnostics, sector breadth and comparisons |
| Selected stocks | Additive row checkboxes, persistent ticker selection, named groups, selected-result CSV, group tickers, group screening and selected-stock chart grid |
| Stock explorer | Interactive Plotly hover/zoom/legend, short/long/custom MA views, exact analyzed segments, fitted trendlines and calculation audit |
| Chart grid | 4/8/12/20 charts per page, 1–4 columns, rule-specific ranking/highlights; only one requested page is drawn |
| Presets | Five editable examples; save/load/rename/delete local presets; import/export JSON including data settings |
| Downloads | Displayed/all results CSV, Excel, per-stock OHLCV/return/MA CSV, all-stock historical ZIP, JSON configuration |
| Historical research | Causal screens ending at the selected session; separate opt-in 5/20/60-session forward outcomes |
| Screen history | Automatic local snapshots on successful runs; new/dropped qualifiers, unavailable data, changed rules and streaks across saved dates |
| Research lab | Multi-date cohort/control comparisons, cost-aware portfolio simulation, fixed parameter neighbors, chronological slices, portable frozen holdouts and trial ledger |
| Portfolio concentration | Equal/custom weights, cash, sector exposure, effective holdings, stock correlations, variance contributions and hypothetical basket risk |

Grid sorting supports normalized slope, MA change, R-squared, longest rising streak or recent stock return. Select the ranking rule so comparisons use the same window. The table's rank_* convenience columns use the first valid enabled non-price rule; each rule also has its own detailed columns.

Edits remain drafts until **Run Screen**. Old results keep their applied configuration, and a banner indicates pending changes. A failed run displays its error and retains the last completed screen.

### Workspace layout

The builder has three tabs in order: **Moving averages & trend rules**,
**Risk settings**, then **Relationships**. Each MA has its conditions directly
below the shared MA table, with an **Add condition** button for additional
independent conditions. Universe and date controls stay in the sidebar, and
**Run Screen** stays above the workspace.

Disabling or removing an MA automatically pauses its dependent conditions,
including relationships referencing that line. Re-enabling/re-adding the MA
resumes only conditions that were paused automatically. Conditions you disabled
manually stay disabled. You can also reassign a paused condition to an enabled
MA. Saved JSON preserves the pause state. Hiding a line with **Show on charts**
only changes the chart; it does not disable a condition.

Changing an MA type/period updates rule references, name tokens and selector
values together. Stable row identities prevent deleting one row from attaching
another row's rules to the wrong MA. Rule headers always show the actual current
series and method. Imported/example MAs used only for charting or relationships
do not acquire extra trend conditions unless you add them.

**Relationships** is optional: it compares two lines, such as SMA5 above SMA20,
or a recent crossover from below to above. It does not measure one line's upward
slope. Leave it empty if you only want rising-line filters.

### Collecting and separating stocks

In **Results**, tick the **Select** checkbox on any number of rows. No Ctrl/Shift
selection is required. Previewing a chart, sorting, changing table columns/views,
or running another screen does not replace the ticker selection. **Select all
shown** adds the visible population; **Clear stock selection** clears it.

Open **Selected stocks** to remove individual tickers, save/replace named groups,
load/delete groups, download selected results as CSV or export a group's tickers.
**Use selected stocks as the screening universe** prepares a custom-ticker draft;
click Run Screen to apply it. In **Chart grid → Grid stocks**, choose **Selected
stocks** to compare selected stocks present in the current applied screen,
including nonmatches. Other selected tickers remain in the group with blank
current metrics until screened; their data is not downloaded automatically.

Selections/groups persist locally under `.screener/collections/` or
`SCREENER_HOME/collections/` and are excluded from Git. They reopen without a
new screen or provider request. Keep that directory when moving installations.
Named groups and chart focus are separate: switching the preview never removes
earlier selected stocks.

Results open in a compact **Overview**. Switch to **Trend details** or **Risk
comparison** for more metrics, or use **Custom**. **Choose visible columns**
retains access to every available field, and **Export & download** contains CSV,
Excel and historical archives. These views change presentation; they keep the
same applied screen and exports.

Price and performance charts share a light navy-and-teal theme, readable
tooltips and consistent spacing. The selected rule's chart header separates its
pass/fail result from its numerical measurements. **Calculation details** expands
the complete audit underneath each stock chart. Native zoom, pan, legend,
selection and image-download controls remain available. Styling uses system
fonts and local assets, with no font downloads.

## Mathematical definitions

### Risk and performance analytics

Open **Build screen → Risk settings → Risk & performance settings** to enable these metrics,
choose lookbacks and select columns. Then click **Run Screen**. The **Risk &
performance** tab compares the selected stock across every lookback and offers
rolling metric charts, growth of 100, drawdown and a per-stock CSV download.
The results table, Excel, CSV and chart-grid sorting also include these metrics.

- Defaults are **63, 126 and 252 daily returns**. Enter any integer lookbacks
  of at least 2, separated by commas. An N-return window requires **N+1 consecutive
  adjusted closes** ending on the screening session.
- Both **annualized Sharpe** and **unannualized daily Sharpe** are available.
  Select the daily version in the metrics selector to show it alongside the
  annualized version. Shorter and longer lookbacks can be compared side by side.
- The default benchmark is **SPY**, an adjusted ETF proxy. You can choose
  **^GSPC**, **QQQ** or a custom provider ticker. ^GSPC is a price index and does
  not include reinvested dividends. Ticker aliases also apply to benchmarks;
  the actual provider symbol is recorded in the exported results.
- The **annual risk-free assumption defaults to 0%**. This is a configurable
  assumption, not a live Treasury quote. Sortino can use this rate as its target
  or a separately specified annual minimum acceptable return.
- **252 trading sessions per year** is the default annualization assumption.
  All performance statistics use **adjusted daily simple returns**, independently
  of the MA price basis and simple/log daily-return display choice.

Let r be the stock's daily simple return, b the benchmark's return, A the
selected sessions per year and N the number of returns. For an annual
effective risk-free assumption R entered in percent, the daily rate is
f = (1 + R/100)^(1/A) − 1. The Sortino target T is converted to daily target m
the same way. Standard deviations below use the sample convention (N−1).

| Metric | Calculation and units |
| --- | --- |
| Daily Sharpe | mean(r−f) / standard_deviation(r−f) |
| Annualized Sharpe | Daily Sharpe × sqrt(A) |
| Annualized Sortino | mean(r−m) × sqrt(A) / sqrt(mean(min(r−m, 0)²)); downside mean includes **all N days** |
| Annualized volatility | standard_deviation(r) × sqrt(A) × 100, in percent |
| Annualized downside deviation | sqrt(mean(min(r−m, 0)²)) × sqrt(A) × 100 |
| Beta | OLS slope of (r−f) against (b−f), with an intercept; covariance / benchmark variance |
| Daily regression alpha | mean(r−f) − beta × mean(b−f), displayed ×100 in percent |
| Annualized regression alpha | Daily intercept × A ×100; **arithmetic annualization**, not CAGR |
| Return-regression R-squared | Squared stock/benchmark return correlation; distinct from MA-trend R² |
| Total adjusted return | (final adjusted close / starting adjusted close − 1) ×100 |
| CAGR | ((final / starting adjusted close)^(A/N) − 1) ×100; per assumed trading year |
| Annualized mean return | mean(r) × A ×100; an arithmetic measure, separate from CAGR |
| Maximum drawdown magnitude | Largest adjusted-price peak-to-trough loss inside this window, as positive percent |
| Calmar | CAGR / maximum drawdown magnitude, using the same window |
| Annualized tracking error | standard_deviation(r−b) × sqrt(A) ×100 |
| Annualized information ratio | mean(r−b) × sqrt(A) / standard_deviation(r−b) |
| Active total return | Stock total return minus benchmark total return, in percentage points |
| Positive daily returns | Percentage of the N daily stock returns that are strictly positive |

Stock and benchmark returns use the **same dates**. Missing observations are
never dropped to manufacture a shorter sample or filled with old prices.
If benchmark prices are incomplete, stock-only metrics can still be shown;
beta, alpha and other benchmark-dependent values remain unavailable. If the
stock window is incomplete, its risk metrics remain unavailable.
Zero-volatility, zero-downside and zero-drawdown ratios are also unavailable;
they are not displayed as zero or infinity. The detail panel explains missing
metrics. Numerical denominator values at or below 1e-12 in daily-return units
are treated as zero to avoid floating-point artifacts.

Annualization uses the conventional square-root scaling and does not correct
for serial correlation. Lookback, frequency, risk-free and benchmark choices
can produce different results from other platforms. These are statistics of
historical stock returns, **not a backtest of a moving-average trading strategy**
and not estimates of the probability that tomorrow's price will rise.

Risk metrics do not change which stocks pass the MA rules. Use the table to
sort metrics and the chart grid's performance lookback to rank matching stocks
by Sharpe, Sortino, alpha, beta, volatility or drawdown.

Enabling the default analytics can require more warm-up data than an MA-only
screen: the loader requests at least the largest risk lookback plus one close,
and downloads the benchmark once alongside the universe. This uses the same
incremental cache. Changing just rates, visible metrics or MA thresholds reuses
loaded prices. A new benchmark or a longer required history fetches the needed
data. Disabling analytics removes the benchmark request and risk warm-up
requirement. Existing saved configurations without a risk section load with
the editable defaults; saving now also preserves the risk settings.

Formula references: [William F. Sharpe, The Sharpe Ratio](https://web.stanford.edu/~wfsharpe/art/sr/sr.htm)
and [CFA Institute Research Foundation, Alternative Investments (downside-risk measures)](https://www.cfainstitute.org/sites/default/files/-/media/documents/book/rf-publication/2018/rf-v2018-n1-1.pdf).

### Moving-average rules

All windows count **NYSE sessions**, not calendar days. The calendar accounts for holidays, weekends, daylight saving and early closes. Latest mode uses a 15-minute publication buffer after the official close.

| Method | Exact definition |
| --- | --- |
| Net increase | MA[t] > MA[t−X], plus the selected percentage comparison; X transitions, X+1 observations |
| Percentage change | 100 × (MA[t]/MA[t−X] − 1), with any comparison; intermediate dips allowed |
| Strictly increasing | Every one of X daily differences is >0; flat or negative changes fail; true=1 |
| Regression | Fit y = intercept + slope × x, with x=0..X−1, to exactly X MA observations |
| Normalized slope | 100 × slope / mean(MA window), in percent per session; raw slope remains price units/session |
| R-squared | Squared correlation between session index and MA values; undefined for constant lines |
| Mostly increasing | Count or percentage of strictly positive differences over X transitions |
| Percentage acceleration | Latest X-transition MA percentage change minus the preceding X-transition change; boundary shared, 2X+1 observations |
| Slope acceleration | Current normalized slope minus previous normalized slope; consecutive non-overlapping X-observation windows, 2X observations |
| Turning up | Current normalized slope > minimum, previous slope evaluated L sessions ago <0 or optionally <=0; optional C positive evaluations ending today |
| Smoothness | Positive/downward/flat counts, positive percentage, R², maximum MA peak-to-trough decline and longest rising streak |
| Relative position | 100 × (left/right − 1); left is price or MA, right an MA; >0 means left is above |
| Bullish crossover | left−right changes from <=0 to >0 within X transitions; bearish reverses the inequalities |
| Separation change | Absolute relative-position percentage today minus its value X transitions ago |

**Units:** 1 means 1%, and 0.01 normalized slope means 0.01% per session. Acceleration differences use percentage points, not percentage growth of a slope. Optional positive-rate switches distinguish upward acceleration from falling more slowly. Turning-up thresholds are minimum normalized slopes; its comparison applies to the turning-up boolean against 1. Confirmation count must not exceed reversal lag.

A positive regression slope describes overall direction and does **not** imply uninterrupted daily increases. A recent crossover can have reversed since it happened; add a current-position rule to require the lines still to be in that order.

Maximum MA decline is 100 × max(1 − MA/cumulative_max(MA)) within the window, a nonnegative peak-to-trough magnitude. It is not the largest one-day loss. Longest streak counts transitions. Inclusive/equality comparisons tolerate floating-point roundoff with relative/absolute tolerance 1e-10; strict inequalities remain strict.

## Prices and returns

The default provider explicitly requests **auto_adjust=False, back_adjust=False**. It preserves provider Open/High/Low/Close/Volume and stores **Adj Close separately**. Yahoo's raw OHLC can already reflect splits; “raw” means the provider fields with auto adjustment disabled, not an immutable original tape.

MAs, price/MA comparisons and charts share the selected price basis. **Returns always use adjusted close**:

- Simple return: AdjClose[t]/AdjClose[t−X] − 1.
- Log return: ln(AdjClose[t]/AdjClose[t−X]).
- Historical CSV return columns are fractions. Results-table returns are percentages.
- If an alternate source supplies auto-adjusted bars, the normalizer explicitly preserves its close as adjusted close and leaves unavailable raw OHLC missing. It never silently substitutes Close for Adj Close.

SMA requires a full N-session window. EMA uses span=N, adjust=False, min_periods=N, seeded at the first valid observation. Warm-up covers the longest MA and all rule dependencies, including acceleration and reversal windows, with **5×period burn-in for EMA**. Finite EMA burn-in approximates an infinite-history EMA; a different history start can produce small seed differences.

Daily bars are aligned to expected NYSE sessions. Gaps remain NaN; prices are never forward-filled. SMA windows crossing gaps are unavailable. EMA resets after each gap. A missing latest session never substitutes an older close. IPOs and unavailable tickers are explicit diagnostics.

## Cache, membership and symbol changes

**Run Screen always checks saved prices first.** It reuses the in-memory data
when the request is unchanged, otherwise reads the local Parquet cache. It
downloads missing tickers/date ranges as needed, including additional MA warm-up
or a newly completed session. Saved complete histories are reused across app
restarts. Cache age alone no longer causes normal dashboard or CLI screens to
refresh prices; the previous automatic six-hour latest-mode refresh is removed.

- **Saved prices only (no downloads)** prevents price-provider calls, even when
  history is missing. Leaving it **unticked still uses saved prices first**; it
  merely allows missing ranges to download. Missing observations remain unavailable.
- **Update prices & run** is a separate, explicit one-click action. By default it
  refreshes the last **21 calendar days** up to the selected screening session,
  downloads missing histories/ranges, retries unavailable tickers and repairs
  saved gaps. Recent updates preserve older saved history.
- **Price update options → Update scope → Full price history** makes that update
  button redownload the entire cached span. Selecting this scope does not affect
  a normal Run Screen, and a completed update does not make later runs repeat it.
- Update is disabled while Saved prices only is selected. Results report whether
  the screen used saved prices without downloads or actually requested price
  data; **Price download activity** lists the symbols, date ranges and reasons.
  Reading from disk is no longer presented as a price download.

Missing-range extensions include a **14-calendar-day overlap** to check provider
corrections, so downloads are not always limited to strictly absent dates. When
both earlier and later history are missing, the loader may request their combined
contiguous span. The cache API still offers an opt-in `refresh_recent=True`
six-hour policy for explicit callers; normal dashboard/CLI flows do not enable it.

If overlapping close or adjusted-close values have been revised, the full cached span is refreshed to avoid mixing adjustment vintages. Failed refreshes retain old cache and report errors. Writes are atomic and protected by an inter-process writer lock. Requests are batched and retried; a circuit breaker stops new downloads after two entirely failed batches.

An explicitly requested full-history refresh already covers that span and does
not issue another identical full download simply because revised prices are found.

Cache and user presets live in **.screener/** beside the source project. Keep that folder to preserve them. Set **SCREENER_HOME** to another writable directory if desired. The five source example JSON files are in **presets/**.

Current membership comes from Wikipedia, with the Open Knowledge CSV mirror as fallback. Source and retrieval timestamp are displayed. Membership cache lasts 24 hours; failed refreshes can use an explicitly dated cached snapshot. Sector mode has **Load / refresh sectors**. Custom lists and the benchmark do not require the constituent source.

BRK.B and BF.B normalize to BRK-B and BF-B. **Ticker aliases / symbol changes** lets you route an old/displayed ticker to a different provider symbol and records provider_ticker in results. An alias uses the destination's history; it does not automatically splice different securities. Changing aliases changes the cache identity.

## Missing data and boolean decisions

Each rule is PASS, FAIL or UNAVAILABLE. Missing values never pass, even for a not-equal comparison. AND fails if a valid branch fails; otherwise an unavailable required branch makes the group unavailable. OR passes if a valid branch passes; otherwise an unavailable branch can prevent deciding the result.

“Analyzed” counts stocks with a decidable root expression. A stock can have a decided result and an unavailable non-decisive branch; inspect rules_unavailable. “Insufficient” counts undecidable overall expressions. Passing percentages use the requested universe as denominator. Rule metrics have stable ID prefixes; inspect/download the configuration to map IDs to rule names.

## Historical research and limitations

The engine clips prices at the screening date **before computing indicators**. Normal charts/exports also end there, even if the disk cache contains newer prices. Weekend/holiday requests resolve to the preceding completed session.

**Past screens using current constituents have survivorship bias.** No historical membership feed is supplied; version 1.2 adds support for a user-provided interval dataset. Yahoo adjusted history is retrospectively restated, rather than an archived point-in-time vintage. Corporate actions, security identifiers and source corrections can affect research; full refresh is appropriate for important comparisons.

Single-date forward outcomes remain a separate opt-in view with independent future-price input. They cannot feed screening rules or normal history exports. Incomplete horizons stay NA. The additional research views below provide separate cohort and portfolio models; they do not change live screening rules.

Yahoo Finance is an unofficial, rate-limited source. Full-universe requests can yield partial results. Ticker failures are displayed rather than interpreted as failed trends or replaced with invented prices. Wait and retry failed prices if limited. Check the provider's applicable use terms. Provider uptime, historical field availability and quote accuracy cannot be guaranteed.

No alternative authenticated data API, archived constituent dataset or point-in-time security master is bundled. **PriceProvider** is the replacement point for another API. No additional non-MA technical indicators or automated trading are included. Extremely large periods can exceed available history and are rejected/reported as insufficient.

### Screen history and changes

Every successful **Run Screen** saves the applied configuration and full result
table locally. Open **Screen history** to compare a snapshot with the most recent
saved **strictly earlier screening date** using the same definition. Changing an
MA, rule, group, universe, alias, price basis or membership source starts a new
definition; chart visibility, descriptive risk settings and names do not.

The table distinguishes newly/still/stopped qualifying stocks, unavailable
prices, and changes to universe membership, and lists rule state changes.
Repeated runs on one date do not create extra days in the streak. A streak counts
**consecutive saved distinct dates**, which may omit trading sessions; it does
not imply the stock qualified on unscreened days. No scheduled task or background
data download is enabled. Snapshot tables, changes and JSON settings can be exported.

### Historical membership CSV

Open **Historical research → Membership data** to upload intervals, declare the
coverage dates and describe the source. A synthetic template is downloadable in
the UI and included in `examples/historical_membership_template.csv`.

Required columns are `ticker,start_date,end_date`; optional columns are
`company,sector,industry`. Dates use `YYYY-MM-DD`. **Start is inclusive, end is
exclusive**; a blank end means still active. Overlapping intervals for one
normalized ticker are rejected. To record a sector change, close one interval
and begin a new interval on the same effective date. Include removed companies
and initial membership at the start of declared coverage, not just additions.

Choose **Historical membership CSV** in the sidebar for individual screens, or
as the study universe. Each date then uses its effective members, and multi-date
studies download the union including removed members. Requests outside declared
coverage fail explicitly. Coverage/source are user declarations, not independently
verified. Missing delisted prices, reused symbols, incomplete intervals, ticker
aliases and retrospectively adjusted data can still introduce bias. The program
does not splice security identities or invent delisting returns.

### Outcome comparisons over many dates

1. Apply a screen, then open **Historical research**.
2. In **Study data**, choose dates, a fixed applied universe or historical CSV,
   and benchmark; click **Load study data**. This reuses the normal incremental cache.
3. Open **Outcome comparison**, choose arbitrary positive holding horizons,
   sampling interval and combined per-side friction, then click
   **Compare historical outcomes**.

Signals use only the screening close and earlier observations. Unlike the older
single-date close-to-close view, these comparisons enter at the **next session's
adjusted open** and exit at the close of the Nth holding session. Adjusted open is
`raw_open × adjusted_close / raw_close` using that session's adjustment factor.
A combined cost fraction c per side gives `exit × (1−c) / (entry × (1+c)) − 1`.
Every holding-period close must exist; gaps and incomplete horizons stay missing.

Controls are stocks with valid **FAIL** signals, the chosen benchmark, and the
mean nonqualifier outcome in each qualifying stock's same-date sector. Unknown
signals are excluded explicitly, not assigned zero returns. The summary includes
coverage, sample sizes, median and 10th/90th percentiles. Mean comparisons give
each eligible sampled date equal weight; the detailed table retains every date
and stock, including unavailable outcomes. Same-sector comparisons can be absent
when no sector control exists. Overlapping outcomes and repeat stocks are
dependent observations; the app does not claim independent-trial significance.

### Portfolio backtester

Open **Portfolio backtest** after loading study data. Configure capital, maximum
positions, holding sessions, review interval, entry ranking, commission, slippage,
cash yield and optional failed-screen exits, then press **Run portfolio backtest**.

- Long-only fractional shares, no borrowing or shorting. Decisions occur at a
  scheduled review's **close** and trade at the **following open**.
- This is a **vacancy-filling** model. The new-position budget is prior-close NAV
  divided by maximum positions, capped by cash. Existing holdings drift; the
  model does not rebalance them to equal weights. Missing ranking metrics sort
  last, with ticker as a deterministic tie breaker.
- A holding period of N includes entry day as session one. It exits at the Nth
  session's close, or at study end. If enabled, a failed/unknown screen or removal
  from membership at a scheduled review triggers an exit at the next open.
- Commission and slippage apply to both sides: entry costs multiply price by
  `(1+slippage) × (1+commission)` and exit proceeds by
  `(1−slippage) × (1−commission)`. Idle cash uses an explicit constant annual yield.
- Missing entry opens cancel that entry with an order diagnostic. **Missing
  held-position opens/closes stop the experiment**. No forward-filled marks,
  synthetic liquidation or dropped delisted holding is used to manufacture a
  complete equity curve.
- The benchmark starts at the same first investable adjusted open, has the same
  side costs and liquidates at the final close. Missing benchmark data leaves
  dependent statistics unavailable. Portfolio Sharpe, CAGR, alpha, beta and
  drawdown come from the **portfolio equity curve**, not averages of stock ratios.

Equity, drawdown, every trade, orders, coverage and assumptions are downloadable.
This daily-bar approximation has no tax, borrow, capacity, volume participation,
market impact, spread model, order book, execution guarantee or point-in-time
price vintage. Retrospective adjustments are a total-return proxy; historical
adjusted levels are not literal tradeable cash prices.

### Robustness and declared holdouts

In **Robustness**, choose a training-end date and simulation assumptions.
**Run training robustness checks** evaluates the base, one MA period ±1, one
rule lookback ±1, and three chronological training slices. Invalid neighbors
are recorded as skipped; valid candidates and failures remain in the ledger.
All references to a perturbed MA are updated consistently. Results remain in
declared order; there is no automatic best-parameter selection. Slices reset
capital and liquidate at their own ends, so they are separate experiments.

**Freeze this plan for holdout** saves a copy of the applied rules, settings,
split, source information and an input snapshot containing the actual loaded
OHLCV/adjusted bars, fixed universe and supplied membership intervals. **Evaluate
frozen holdout** uses those saved inputs on dates strictly after the split, with
new next-open orders. Draft edits, a different current universe and later price-cache
updates do not replace the frozen inputs. Both training and holdout need at least
two trading sessions. Identical inputs reuse one archive across frozen plans.

Open **Historical research → Saved holdouts** after restarting, select the plan
and press **Evaluate saved holdout**. No applied screen, loaded study, provider
call or Internet price retrieval is needed. **Prepare frozen study download**
enables a ZIP containing the plan and complete input snapshot. In another
installation, use **Restore a frozen study bundle → Import frozen study** to
restore it, then evaluate using the same buttons. Imports preserve the declared
holdout/source information and record the originating plan; they create a new
local ledger entry without overwriting an existing plan.

Snapshots store per-file and whole-archive SHA-256 checksums, source metadata
and the app/Python/pandas/NumPy/PyArrow versions. Restoration verifies the price,
universe and membership inputs. Missing or damaged archives produce an error;
the app does not silently substitute new market data. Snapshots live under
`.screener/research/snapshots/` and are excluded from Git. Back up the full research
directory or export portable bundles before moving installations.

Plans created before version 1.2.1 have no archived price bars and retain their
original requirement for matching loaded study data. Their saved settings remain
available; freeze a new plan to capture a portable snapshot. The archive preserves
the prices loaded when you freeze, **not an original historical vendor vintage**.
Reproducing an older snapshot across substantially different library/app versions
may require its recorded environment, and the program rejects changed input
fingerprints. Its source code and software environment are recorded by version,
not embedded as an executable application in the bundle.

A declared holdout does **not** prove the historical period was unseen by you.
Repeated manual exploration, changing split dates and repeated tests can still
overfit. Every executed trial/evaluation and frozen plan is retained locally and
the complete experiment ledger, frozen JSON and new portable input bundles are downloadable. The app does
not calculate a probability of backtest overfitting or claim statistical validation.

### Portfolio concentration and correlations

Open **Risk & performance → Portfolio concentration**, choose matching or all
screened stocks, equal/custom nonnegative weights, and a return window, then
press **Calculate basket risk**. Stock weights may sum to at most 100%; the
remainder is cash. Zero-weight stocks are excluded from data requirements.

Every positive-weight stock must have the same N+1 complete adjusted closes.
The panel reports sector/cash weights, largest position, stock HHI, effective
holdings, stock-to-stock correlations, variance contributions, diversification
ratio and portfolio risk statistics. Stock HHI uses invested stock weights
normalized to one; effective holdings = 1/HHI. Variance contribution is
`w_i × (Cov × w)_i / (wᵀ Cov w)` and can be negative for a hedging position.
Diversification ratio is weighted standalone daily volatility divided by basket
daily volatility; constant-return cases remain undefined.

The hypothetical basket return is `Σ(w_i × stock_return_i) + cash × daily_RF`,
which assumes **daily target-weight rebalancing without trading costs**. It is a
diagnostic basket model, distinct from the backtest's drifting holdings. The
heatmap shows at most 40 stocks for readability; exports include the full matrix.

All snapshots, membership intervals and experiment records are stored under
`.screener/research/` (or `SCREENER_HOME/research`). They are local application
data and are excluded from Git. Back up that directory to retain history when
moving installations. Loading filters or opening panels alone does not download
study prices or execute simulations.

## CLI and tests

~~~bash
# Offline screen
python -m trend_screener.cli --demo --date 2024-01-16 --output demo-results.csv

# Live custom list
python -m trend_screener.cli --tickers "AAPL,MSFT,BRK.B" --output sample-results.csv

# Full current S&P 500 using an example JSON
python -m trend_screener.cli --config presets/01_all_moving_averages_rising.json

# Deterministic math, cache, export and dashboard interaction tests
python -m pytest -q
~~~

The CLI accepts **--cache-dir**, **--refresh**, **--date** and **--config**. Explicit CLI flags choose live/demo mode; a preset's sidebar settings do not override CLI flags. Normal tests make no live market requests. See **TEST_REPORT.md** for actual results and verification limits.

The independently specified datasets in **examples/synthetic_scenarios.json** include exact expected values, expressed as fractions where helpful. They cover uninterrupted rises/declines, dips, flat lines, opposing endpoint/slope directions and acceleration.

## Source organization

| Module | Responsibility |
| --- | --- |
| app.py, run_dashboard.py | Dashboard launchers |
| dashboard.py | Streamlit controls, state, results and downloads |
| models.py | Validated MA/rule/group configuration and JSON |
| builder.py, collections.py | MA/rule synchronization, preserved pause intent, named stock groups and ticker-based multi-selection |
| universe.py | Current membership, metadata and symbol normalization |
| providers.py, cache.py, calendar.py | Data abstraction, aliases, validation, Parquet cache and NYSE sessions |
| indicators.py, metrics.py | Causal MAs/returns and trend mathematics |
| risk.py, risk_dashboard.py | Validated risk settings, date-aligned performance calculations, rolling metrics and dashboard panels |
| rules.py, engine.py | Independent conditions, nested logic, indicator reuse and results |
| charts.py, exports.py | Auditable Plotly views and CSV/Excel/ZIP downloads |
| presets.py, presets/ | Editable built-in and local presets |
| research.py, cli.py, demo.py | Separate forward research, CLI and synthetic data |
| membership.py, history.py | Effective membership intervals, SQLite screen snapshots and experiment ledger |
| studies.py, robustness.py | Causal historical signals, cohorts, simulator, recorded training trials and frozen holdouts |
| snapshots.py | Atomic reusable Parquet input archives, checksums and offline restoration |
| portfolio.py, research_dashboard.py | Aligned weighted-basket risk, concentration and button-driven research UI |
| tests/ | Closed-form, adversarial, missing-data, cache and application interaction cases |

Python package modules live in **trend_screener/**.

API references: [yfinance](https://ranaroussi.github.io/yfinance/reference/api/yfinance.download.html), [Streamlit](https://docs.streamlit.io/develop/api-reference/data/st.dataframe), [pandas-market-calendars](https://pandas-market-calendars.readthedocs.io/en/latest/usage.html). Constituent fallback provenance: [Open Knowledge S&P 500 dataset](https://github.com/datasets/s-and-p-500-companies).
