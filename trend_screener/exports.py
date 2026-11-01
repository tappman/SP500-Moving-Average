"""Downloads without price-basis ambiguity."""
from io import BytesIO
import zipfile

import pandas as pd

from .engine import ScreenRun


def excel_bytes(table: pd.DataFrame) -> bytes:
    buffer = BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        table.to_excel(writer, sheet_name="Screen results", index=False)
    return buffer.getvalue()


def history_zip(run: ScreenRun, tickers: list[str] | None = None) -> bytes:
    buffer = BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("configuration.json", run.config.to_json())
        archive.writestr("README.txt",
                          f"Screen date: {run.screen_date}\n"
                          f"MA price basis: {run.config.price_source}\n"
                          "Raw OHLC and separately adjusted close are preserved.\n"
                          "Return columns are fractions, not percentages. Rule/table percentage metrics use percent units.\n"
                          "These histories end at the screen date; forward outcomes are excluded.\n")
        for ticker in tickers if tickers is not None else run.frames:
            archive.writestr(f"{ticker.replace('^', 'INDEX_')}.csv", run.frames[ticker].to_csv())
    return buffer.getvalue()
