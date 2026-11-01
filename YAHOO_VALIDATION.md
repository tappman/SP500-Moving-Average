# Yahoo price and calculation validation — 1.2.7

Executed November 1, 2026 using daily AAPL and SPY history from January 3, 2023
through January 31, 2024 (271 bars each). These are historical sample values,
not current quotes. Yahoo can subsequently restate adjusted history.

The production YFinanceProvider downloaded separate Close and Adj Close fields.
A separate request to Yahoo's `/v8/finance/chart/{symbol}` endpoint retrieved
its quote.close and adjclose arrays. Dates were mapped in America/New_York.
Both production price columns agreed with the separate response for both
symbols at relative/absolute tolerance 1e-6. This checks field parsing and dates
against the underlying source, rather than assuming the provider's labels.

Independent arithmetic checked the final daily return, SMA20 and EMA20 against
the engine. SMA20 is the mean of the last 20 adjusted closes. EMA20 starts with
the first retrieved adjusted close and recursively applies weight 2/21 to each
new price and 19/21 to the preceding EMA. MA results agreed at relative tolerance
1e-12. These EMA values use all 271 retrieved observations.

| Symbol, January 31, 2024 | Close | Adj Close | Adjusted SMA20 | Adjusted EMA20 |
| --- | ---: | ---: | ---: | ---: |
| AAPL | 184.399994 | 182.178925 | 185.566145 | 187.323717 |
| SPY | 482.880005 | 467.578522 | 463.936732 | 465.419419 |

Independent NumPy calculations also reproduced AAPL's last 63 daily-return
metrics against SPY, with a zero risk-free assumption and annualization 252:

| Metric | Result |
| --- | ---: |
| Annualized Sharpe | 1.8302161345 |
| Daily-return beta | 1.2042521347 |
| Arithmetic annualized regression alpha (%) | -40.9070542954 |

Sharpe used mean return divided by sample standard deviation (ddof=1), times
sqrt(252). Beta used sample covariance / sample benchmark variance. Alpha used
(mean stock return minus beta times mean benchmark return) times 252 times 100.
The engine agreed at relative/absolute tolerance 1e-10.

These checks validate Yahoo **source prices and the app's stated formulas**.
They do not establish parity with every website chart or proprietary published
statistic. Match daily versus monthly data, completed session, history length,
Close versus Adj Close, EMA seed, benchmark, risk-free rate and annualization.
For example, [Yahoo's statistics page](https://finance.yahoo.com/quote/GOOGL/key-statistics/)
labels its beta as **5Y Monthly**; this app's configurable daily beta uses a
different sample. The website's exact chart EMA initialization was not verified.

The explorer now provides **Compare numbers with Yahoo Finance**, showing Close,
Adj Close and enabled MAs, plus a complete comparison CSV. A cached price vintage
may differ from a newer Yahoo response until explicitly updated. Source agreement
is not independent verification that Yahoo's own underlying data is error-free.
