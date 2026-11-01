# MA Trend Lab

A Python and Streamlit dashboard for finding S&P 500 stocks whose simple or
exponential moving averages are rising. Build your rules with controls, run a
screen, then inspect the exact MA segment, regression fit and calculations.

## Open the app

1. Install [Python 3.11 or newer](https://www.python.org/downloads/). On Windows,
   enable **Add Python to PATH** during installation.
2. Download this repository with **Code → Download ZIP** and extract the whole ZIP.
3. Double-click **START_WINDOWS.bat** on Windows or **START_MAC.command** on macOS.
4. The first launch installs the packages and opens your browser. Later launches
   reuse that setup. Keep the launcher window open while using the dashboard.

These launchers require Python; a standalone executable is not included. First
setup needs Internet access. If macOS blocks the launcher, open the extracted
folder in Terminal and run `bash START_MAC.command`. Linux users can use the
manual setup below. Native Windows/macOS double-click behavior has not been
verified in the development environment.

<details>
<summary>Manual installation and startup</summary>

From the extracted project folder:

```bash
python -m venv .venv
```

Activate with `source .venv/bin/activate` on macOS/Linux or
`.venv\Scripts\activate` in Windows Command Prompt. Then:

```bash
python -m pip install -r requirements.txt
python -m streamlit run app.py
```

Use `python3` instead of `python` if required on macOS/Linux. On Windows,
`py -3 -m venv .venv` is another way to create the environment.
The browser address is usually http://localhost:8501. Stop with **Ctrl+C**.
Subsequent launches can use `python run_dashboard.py`; append
`--server.port 8502` if the normal port is occupied.

</details>

## Run your first screen

1. Select **Live Yahoo Finance** and **S&P 500 (current constituents)** in the
   sidebar, or **Synthetic demo (offline)** to try the app without downloads.
2. In **Build screen → Moving averages & trend rules**, add an MA row. Choose
   **SMA — Simple moving average** or **EMA — Exponential moving average**, any
   positive integer period, enabled status and chart visibility.
3. Expand its rule. For EMA7, keep **Auto**: a 6-observation regression,
   normalized slope **> 0**. Disable other conditions if you want only this rule.
4. Click **Run Screen**, then open **Results**. Draft edits apply only when run.
5. Tick stocks to collect several at once. Preview one or open **Stock explorer**
   and select the rule to highlight. The chart and calculation panel explain it.

The MA period determines the line; the trend lookback determines which portion
of that line is tested. A positive overall slope permits small daily declines.
Use Strictly increasing when every daily transition must rise.

## Auto and Custom EMA lookbacks

New EMA regression rules start in **Auto**. The suggestion changes when you edit
the EMA period. **Custom** unlocks the lookback so you can enter any valid window.
Existing saved rules retain their exact lookbacks in Custom mode. Each rule has
its own mode, and both mode and effective window are saved in presets.

Auto applies to normalized slope, raw slope and regression R-squared; other
methods retain manually editable windows. SMA windows remain Custom.

These are usability starting points, **not scientifically established optimal
lookbacks**. Short EMAs can remain noisy. Compare alternative windows in
historical research for your chosen holding period. Parameter-neighbor research
uses Custom for explicit lookback changes so Auto cannot undo the trial.

## What the dashboard includes

| Area | What you can do |
| --- | --- |
| Data settings | Select all current constituents, a sector, custom tickers, one stock, ^GSPC, or supplied historical membership. Choose latest close or a historical date and 3/6 months, 1/2/3/5/10 years or custom chart dates. |
| MA rules | Add arbitrary SMA/EMA periods and independent conditions. Duplicate, pause or remove rules; combine with AND/OR and nested groups. Disabling an MA pauses its dependent rules. |
| Risk settings | Compare custom daily-return windows, select a benchmark, annual risk-free rate, annualization and Sortino target. |
| Relationships | Compare any two MAs or price versus an MA; test alignment, recent bullish/bearish crossovers and changing separation. |
| Results | Sort results, choose columns, inspect rule/risk metrics, sector counts and data issues; download CSV or Excel. |
| Selected stocks | Additive stock checkboxes, persistent selections, named stock groups, ticker/CSV exports and group screening. |
| Stock explorer | Interactive adjusted-price/MA charts, selected-rule highlights and regression fits; inspect values, counts, slope and pass/fail. Compare Close, Adj Close and MAs with a downloadable CSV. |
| Chart grid | Compare 4/8/12/20 stocks per page with adjustable columns, highlights and ranking by rule metrics or risk statistics. |
| Saved presets | Five editable example screens; save, load, rename, delete, import and export JSON configurations. |
| Historical research | Separate forward outcomes, multi-date cohort comparisons, portfolio backtests, robustness checks, membership data and portable frozen holdouts. Each section has question-mark help. |
| Screen history | Automatic snapshots after successful screens; compare new/dropped matches, rule changes and streaks across saved dates. Delete one or multiple selected snapshots. |
| Portfolio concentration | Equal/custom weights, cash, sector exposure, effective holdings, correlations, variance contributions and hypothetical basket risk. |

The five example screens cover all MAs rising, bullish alignment, a smoothly
rising MA20, MA20 turning upward and an accelerating trend. All values are editable.
Downloads include results, configurations, historical OHLCV/returns/MAs, research
outcomes, portfolio trades, experiment records and frozen study bundles.

## Trend calculations

Question marks beside methods explain their formulas, units and worked examples.
All calculations use numbers, not chart-image analysis. An X-transition window
uses X+1 MA observations; an X-observation regression uses exactly X observations.

| Method | Calculation and interpretation |
| --- | --- |
| Net increase | MA today must exceed MA X sessions earlier, plus your percentage-change condition. Intermediate dips are allowed. |
| Net percentage change | `100 × (MA_today / MA_X_sessions_ago − 1)`, compared with your threshold. |
| Strictly increasing | Every one of the last X daily MA changes must be strictly positive; flat days fail. |
| Regression slope | Ordinary least squares against observation positions 0…X−1. Raw slope is price units/session; normalized slope is `100 × raw slope / mean(MA window)`, in percent/session. |
| Mostly rising | Count positive transitions or their percentage. Optional consistency filters can accompany slope rules. |
| R-squared | How closely the MA follows its regression line. Undefined for a constant line; it does not establish upward direction by itself. |
| Acceleration | Compare two consecutive equal-length percentage-change or regression windows. Threshold units are percentage points or percentage points/session. Optional positive-current/previous conditions apply. |
| Turning up | Compare current regression slope with its value a chosen number of sessions earlier, with minimum positive slope and optional consecutive confirmation. |
| Smoothness | Positive/downward counts, longest rising streak and maximum peak-to-trough MA decline over the selected window. |
| Relationships | Percentage difference between two lines, crossovers within X transitions, or change in their absolute percentage separation. |

Missing values never pass by default. In an OR group, another independently
passing condition can suffice; unavailable branches do not become true. Empty
groups are ignored. Threshold comparisons treat nonzero values within relative
1e-10 as equal, with zero absolute tolerance so tiny signed slopes retain direction.

## Sharpe and other risk metrics

Sharpe metric cards and results/risk comparison columns have question-mark help with the formula,
actual return window, annualization and assumed risk-free rate. Metric cards use
labels such as **Annualized Sharpe — 252 daily returns, 0% annual risk-free rate**.
Labels describe the applied screen, not pending draft edits.

For N daily simple returns from N+1 consecutive adjusted closes:

```text
r = adjusted_close_today / adjusted_close_previous_session − 1
rf_daily = (1 + annual_risk_free_percent / 100)^(1/A) − 1
Daily Sharpe = mean(r − rf_daily) / sample_std(r − rf_daily, ddof=1)
Annualized Sharpe = Daily Sharpe × sqrt(A)
```

A defaults to 252 sessions/year. The risk-free rate is a user assumption,
defaulting to 0%, rather than a downloaded Treasury rate. Missing observations
or zero volatility make the ratio unavailable. Annualization does not correct
for serial correlation. Risk calculations always use adjusted simple returns,
regardless of the chart basis or simple/log return display setting.

Other metrics include Sortino, volatility, downside deviation, drawdown, Calmar,
CAGR, information ratio, tracking error, correlation and benchmark regression
R-squared. Sortino divides mean return above its selected target by downside
root-mean-square over **all** window days, then multiplies by sqrt(A).
Beta is the daily excess-return regression slope; alpha is its daily intercept
multiplied by A (and 100 for percent). Alpha is arithmetic annualization, not CAGR.
Drawdown magnitude is positive. Undefined denominators remain unavailable.

To compare with Yahoo, match the date, frequency, price basis, window, EMA seed,
benchmark and rate assumptions. Yahoo's published 5Y Monthly beta differs from a
configurable daily beta. Yahoo chart/ratio parity is not guaranteed. Live checks
have matched downloaded Close/Adj Close with direct Yahoo responses and MA/risk
results with independent arithmetic. Retrospective adjusted values may change.

## Cached prices and data updates

- **Run Screen** checks saved prices first and downloads only missing histories
  or date ranges. Changing rules alone reuses loaded data and indicators.
- **Saved prices only** prevents all price downloads, including missing ranges.
- **Update prices & run** explicitly refreshes the recent 21 calendar days and
  repairs gaps. **Price update options → Full price history** requests the full
  saved span when you press that update button.
- Historical **Load study data** uses the same incremental cache, with separate
  **Use saved study prices only** and **Update study prices** controls.
- Price-activity panels list requested tickers, dates and reasons. A cache read
  is not reported as a download. Missing history on both ends uses separate
  requests rather than redownloading the saved middle.

Requests include overlap to check revised adjustments. A revision or missing
usable overlap can require full-span revalidation. Incomplete replacements are
rejected while saved history and its successful-download timestamp are retained.
Updates replace whole price rows; adjusted/unadjusted vintages are not spliced.
Errors and stock/benchmark acquisition timestamps appear in results/exports.
The provider retries failures and stops further requests after repeated completely
failed batches. Missing sessions are never forward-filled.

Prices are Parquet files. Raw provider OHLCV and separately adjusted close are
kept apart; MAs default to adjusted close and can explicitly use Close instead.
SMA gives equal weight over N prices; EMA uses span N, `adjust=False`, resets
after missing prices and includes warm-up history (at least five EMA periods).
Simple and log return display are supported. Charts can be shorter than warm-up.
The default screening date is the latest completed NYSE session, including
holidays/early closes and a 15-minute post-close delay.

Current constituents come from Wikipedia, with an Open Knowledge mirror fallback
and a separately dated 24-hour membership cache. BRK.B/BF.B normalize to
BRK-B/BF-B. Explicit ticker aliases route to a provider symbol; they do not splice
different securities. Alias changes create a separate cache identity.

## Historical research

Screen indicators and rules only see prices through the selected date. Forward
outcomes are separate and never feed historical screening conditions.

- **Single-date outcomes:** adjusted close-to-close 5/20/60-session returns for
  matches or all screened stocks. Downloads stop at the longest needed horizon.
- **Outcome comparison:** repeat rules on sampled historical dates; compare
  qualifiers, valid nonqualifiers, sector controls and benchmark. Entries use
  next open; selected holding horizons and per-side costs apply. Overlapping
  observations are dependent; cohort averages are not one compounded portfolio.
- **Portfolio backtest:** long-only, next-open entries, fractional shares, position
  caps, review schedules, ranking, holding periods, fees/slippage and cash yield.
  Existing holdings drift. Fixed-period exits/final liquidation use closes.
  Missing held-position prices stop the simulation rather than invent a sale.
- **Robustness:** neighboring parameters, chronological training slices, recorded
  experiments and user-declared holdouts. Trying many settings can overfit.
- **Membership data:** upload intervals with included start and excluded end,
  source and declared coverage. A template is included in `examples/` and the UI.
- **Saved holdouts:** freeze actual inputs, rules and membership; export/import
  checksum-verified bundles and evaluate archived inputs without new downloads.
  Inputs freeze data, not the executing software version.

History snapshots save successful screen results automatically. Comparisons use
matching rule/universe definitions and a strictly earlier screen date. Streaks
count saved distinct dates and may skip sessions. Confirmed deletion removes
selected snapshots/comparison dates, retaining prices, presets, applied results
and frozen research. Download snapshots before deleting if you need backups.

**Past studies using today's constituents have survivorship bias.** No verified
historical membership feed, delisting-return dataset or point-in-time price
archive is bundled. User-supplied membership completeness is not certified.
Yahoo adjusts history retrospectively. Taxes, market impact, capacity, liquidity,
shorting and real order execution are not modeled. Declared holdouts do not prove
that their dates were never inspected. Trend/acceleration metrics are descriptive,
not forecasts. This is a research tool, with no automated trading.

## Saving, updating and troubleshooting

Keep **.screener/** when replacing application files. It stores price caches,
local presets, stock selections/groups, history, experiment records, membership
and frozen inputs. Set **SCREENER_HOME** to another writable folder if desired.
Download the updated repository, replace application files and reopen the app;
retain that data folder. Launchers reinstall dependencies if requirements change.

If downloads fail, inspect data diagnostics; saved prices may remain usable but
an update can be incomplete. Try again later after Yahoo throttling, or work in
saved-only/demo mode. Missing latest-session data is unavailable, not replaced
with a stale close. To repair previously truncated history, request the desired
earlier start and explicitly update full history for affected tickers.
Older relationship-first backtests from before 1.2.6 may need rerunning because
slope ranking was corrected. Calculation changes can affect archived-data reruns.

Local server startup, numerical formulas, cache behavior, exports and Streamlit
widget workflows have been checked in Python 3.12. Browser pixel layout, native
Windows/macOS startup and a multi-Python-version execution matrix remain
unverified. Yahoo availability across every constituent cannot be guaranteed.

## Source and optional command-line use

| Files | Purpose |
| --- | --- |
| app.py, run_dashboard.py | Dashboard entry points |
| bootstrap.py, START_* | Setup and double-click launchers |
| trend_screener/ | Data/cache, indicators, rules, risk, charts, research, presets and UI |
| presets/ | Five editable example screen configurations |
| examples/historical_membership_template.csv | Synthetic membership-format example |
| requirements.txt, pyproject.toml | Runtime dependencies and package metadata |

The repository contains runtime source and user instructions; development tests
and historical reports are omitted. Older versions remain in GitHub history.

Optional headless runs use the same engine:

```bash
python -m trend_screener.cli --demo --date 2024-01-16 --output demo.csv
python -m trend_screener.cli --tickers AAPL,MSFT --date 2024-01-16 --output results.csv
```

Use `--config presets/01_all_moving_averages_rising.json` for rules,
`--cache-dir` for storage and `--refresh` for a full refresh. Without `--tickers`
or `--demo`, the CLI uses current S&P 500 constituents. Explicit CLI flags choose
source/universe/date; loading JSON does not replay every sidebar control.
