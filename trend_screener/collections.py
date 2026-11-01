"""Local named stock groups, independent of chart focus and screening filters."""
import hashlib
import json
from pathlib import Path
from uuid import uuid4

from filelock import FileLock

from .universe import provider_symbol


def clean_tickers(values):
    return list(dict.fromkeys(provider_symbol(t) for t in values))


def apply_selection_edits(selected, row_tickers, edits):
    selected = list(selected)
    for position, fields in edits.items():
        i = int(position)
        if not 0 <= i < len(row_tickers) or "Select" not in fields:
            continue
        ticker = row_tickers[i]
        if fields["Select"] and ticker not in selected:
            selected.append(ticker)
        elif not fields["Select"] and ticker in selected:
            selected.remove(ticker)
    return clean_tickers(selected)


class StockGroups:
    def __init__(self, directory):
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)
        self.path = self.directory / "stock_groups.json"

    def read(self):
        if not self.path.exists():
            return {"selected": [], "groups": {}}
        data = json.loads(self.path.read_text(encoding="utf-8"))
        return {"selected": clean_tickers(data["selected"]),
                "groups": {str(k): clean_tickers(v) for k, v in data["groups"].items()}}

    def change(self, *, selected=None, save_name=None, delete_name=None):
        with FileLock(str(self.path) + ".lock", timeout=30):
            data = self.read()
            if selected is not None:
                data["selected"] = clean_tickers(selected)
            if save_name is not None:
                name = str(save_name).strip()
                if not name:
                    raise ValueError("Enter a stock group name")
                if not data["selected"]:
                    raise ValueError("Select at least one stock before saving a group")
                data["groups"][name] = data["selected"].copy()
            if delete_name is not None:
                data["groups"].pop(delete_name, None)
            temp = self.path.with_suffix("." + uuid4().hex + ".tmp")
            try:
                temp.write_text(json.dumps(data, indent=2), encoding="utf-8")
                temp.replace(self.path)
            finally:
                temp.unlink(missing_ok=True)
            return data


def selection_signature(tickers):
    return hashlib.sha256(json.dumps(list(tickers)).encode()).hexdigest()[:12]
