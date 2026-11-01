"""Current membership discovery with source timestamps and an explicit stale-cache fallback."""
from dataclasses import dataclass
from datetime import datetime, timezone
from io import StringIO
import json
from pathlib import Path
import re

import pandas as pd
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

WIKIPEDIA = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"
CSV_MIRROR = "https://raw.githubusercontent.com/datasets/s-and-p-500-companies/main/data/constituents.csv"


def provider_symbol(symbol: str) -> str:
    """Yahoo uses BRK-B and BF-B, while constituent lists use BRK.B and BF.B."""
    value = symbol.strip().upper().replace(".", "-")
    if not re.fullmatch(r"[\^A-Z0-9][A-Z0-9^=_-]{0,24}", value):
        raise ValueError(f"Invalid ticker symbol: {symbol!r}")
    return value


def parse_tickers(text: str) -> list[str]:
    return list(dict.fromkeys(provider_symbol(t) for t in re.split(r"[\s,;]+", text.strip()) if t))


def custom_universe(tickers: list[str]) -> pd.DataFrame:
    return pd.DataFrame([{
        "ticker": provider_symbol(t), "symbol": t.strip().upper(),
        "company": t.strip().upper(), "sector": "Unspecified", "industry": "",
    } for t in tickers]).drop_duplicates("ticker").reset_index(drop=True)


def http_session() -> requests.Session:
    session = requests.Session()
    session.headers["User-Agent"] = "MovingAverageResearch/1.0 (personal research dashboard)"
    retry = Retry(total=2, backoff_factor=0.7, status_forcelist=(429, 500, 502, 503, 504),
                  allowed_methods=("GET",), respect_retry_after_header=False)
    session.mount("https://", HTTPAdapter(max_retries=retry))
    return session


def normalize_constituents(raw: pd.DataFrame) -> pd.DataFrame:
    aliases = {
        "Symbol": "symbol", "Security": "company", "GICS Sector": "sector",
        "GICS Sub-Industry": "industry", "Name": "company", "Sector": "sector",
    }
    result = raw.rename(columns=aliases).copy()
    required = {"symbol", "company", "sector"}
    if not required <= set(result):
        raise ValueError("Constituent source has an unexpected schema")
    if "industry" not in result:
        result["industry"] = ""
    result["ticker"] = result["symbol"].astype(str).map(provider_symbol)
    result = result[["ticker", "symbol", "company", "sector", "industry"]].fillna("")
    result = result.drop_duplicates("ticker").reset_index(drop=True)
    if not 400 <= len(result) <= 650:
        raise ValueError(f"Unexpected S&P 500 constituent count: {len(result)}")
    return result


@dataclass
class UniverseSnapshot:
    frame: pd.DataFrame
    retrieved_at: str
    source: str
    warning: str = ""


class UniverseService:
    def __init__(self, directory: str | Path):
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)
        self.path = self.directory / "constituents.json"

    def get(self, force: bool = False) -> UniverseSnapshot:
        cached = None
        if self.path.exists():
            try:
                data = json.loads(self.path.read_text())
                frame = pd.DataFrame(data["records"])
                if not {"ticker", "symbol", "company", "sector", "industry"} <= set(frame):
                    raise ValueError("Invalid constituent cache")
                cached = UniverseSnapshot(frame, data["retrieved_at"], data["source"])
                age = (datetime.now(timezone.utc) - datetime.fromisoformat(cached.retrieved_at)).total_seconds()
                if age < 24 * 3600 and not force:
                    return cached
            except (ValueError, KeyError, TypeError):
                cached = None
        errors = []
        session = http_session()
        for url in (WIKIPEDIA, CSV_MIRROR):
            try:
                response = session.get(url, timeout=(5, 20))
                response.raise_for_status()
                if url == WIKIPEDIA:
                    tables = pd.read_html(StringIO(response.text))
                    raw = next(t for t in tables if "Symbol" in t and "Security" in t)
                else:
                    raw = pd.read_csv(StringIO(response.text))
                frame = normalize_constituents(raw)
                stamp = datetime.now(timezone.utc).isoformat()
                payload = {"records": frame.to_dict("records"), "retrieved_at": stamp, "source": url}
                temp = self.path.with_suffix(".tmp")
                temp.write_text(json.dumps(payload))
                temp.replace(self.path)
                return UniverseSnapshot(frame, stamp, url)
            except (requests.RequestException, ValueError, StopIteration) as exc:
                errors.append(f"{url}: {exc}")
        if cached:
            cached.warning = "Membership refresh failed; using the dated cached snapshot. " + " | ".join(errors)
            return cached
        raise RuntimeError("Unable to retrieve current S&P 500 membership. Use custom tickers or demo mode. "
                           + " | ".join(errors))
