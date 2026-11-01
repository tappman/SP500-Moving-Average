"""Portable, checksummed input snapshots for reproducible frozen research.

These preserve the data loaded by the app, not an original historical vendor vintage.
No pickle, dynamic imports, archive extraction or provider calls are used when loading.
"""
from __future__ import annotations

from datetime import date, datetime, timezone
from io import BytesIO
import hashlib
import json
from pathlib import Path
import re
import sys
from uuid import uuid4
import zipfile

from filelock import FileLock
import numpy as np
import pandas as pd
import pyarrow as pa

from . import __version__
from .membership import MembershipHistory
from .models import ScreenConfig
from .studies import StudyEngine

FORMAT_VERSION = 1


def _sha(data):
    return hashlib.sha256(data).hexdigest()


def _json(value):
    return json.dumps(value, sort_keys=True, allow_nan=False).encode("utf-8")


def _parquet(frame):
    buffer = BytesIO()
    frame.to_parquet(buffer, index=True)
    return buffer.getvalue()


class SnapshotStore:
    def __init__(self, directory):
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)

    def path(self, identifier):
        if not isinstance(identifier, str) or not re.fullmatch(r"[a-f0-9]{64}", identifier):
            raise ValueError("Invalid study snapshot identifier")
        return self.directory / (identifier + ".zip")

    def _unpack(self, raw, descriptor=None):
        try:
            if descriptor and _sha(raw) != descriptor["sha256"]:
                raise ValueError("Study snapshot checksum mismatch; original inputs were not loaded")
            with zipfile.ZipFile(BytesIO(raw)) as archive:
                names = archive.namelist()
                if len(names) != len(set(names)):
                    raise ValueError("Study snapshot contains duplicate file names")
                manifest = json.loads(archive.read("manifest.json"))
                if manifest["format_version"] != FORMAT_VERSION:
                    raise ValueError("Unsupported study snapshot format")
                identity, files = manifest["identity"], manifest["files"]
                identifier = _sha(_json(identity))
                if descriptor and identifier != descriptor["id"]:
                    raise ValueError("Study snapshot identity differs from its frozen plan")
                if set(names) != {"manifest.json", *files}:
                    raise ValueError("Study snapshot files do not match the manifest")
                payloads = {}
                for name, check in files.items():
                    data = archive.read(name)
                    if _sha(data) != check["sha256"] or len(data) != check["bytes"]:
                        raise ValueError(f"Study snapshot file checksum mismatch: {name}")
                    payloads[name] = data
                if _sha(payloads["universe.parquet"]) != identity["universe_sha256"]:
                    raise ValueError("Study universe differs from the saved identity")
            checked = {"id": identifier, "sha256": _sha(raw), "bytes": len(raw),
                       "created_at": manifest["created_at"], "format_version": FORMAT_VERSION,
                       "software": manifest.get("software", {})}
            _json(checked)
            return manifest, payloads, checked
        except (zipfile.BadZipFile, KeyError, TypeError, AttributeError, json.JSONDecodeError, UnicodeError) as exc:
            raise ValueError(f"Invalid study snapshot: {exc}") from exc

    def read(self, descriptor):
        path = self.path(descriptor["id"])
        if not path.exists():
            raise ValueError("Saved price snapshot is missing. Import its frozen study bundle to restore it. "
                             "New market data was not substituted.")
        raw = path.read_bytes()
        self._unpack(raw, descriptor)
        return raw

    def save(self, engine: StudyEngine, source=None):
        universe = _parquet(engine.universe)
        identity = {"format_version": FORMAT_VERSION, "start": str(engine.start), "end": str(engine.end),
                    "price_fingerprint": engine.fingerprint, "universe_sha256": _sha(universe),
                    "membership_digest": engine.membership.digest if engine.membership else None,
                    "source": source or {}}
        identifier = _sha(_json(identity))
        path = self.path(identifier)
        if path.exists():
            manifest, _, descriptor = self._unpack(path.read_bytes())
            if manifest["identity"] != identity:
                raise ValueError("Existing study snapshot has an inconsistent identity")
            return descriptor
        payloads = {"universe.parquet": universe}
        prices = {}
        for ticker, frame in sorted(engine.prices.items()):
            name = "prices/" + _sha(ticker.encode()) + ".parquet"
            prices[ticker] = name
            payloads[name] = _parquet(frame)
        membership = None
        if engine.membership:
            m = engine.membership
            membership = {"coverage_start": str(m.coverage_start), "coverage_end": str(m.coverage_end),
                          "source": m.source}
            payloads["membership.csv"] = m.to_csv().encode("utf-8")
        manifest = {"format_version": FORMAT_VERSION, "created_at": datetime.now(timezone.utc).isoformat(),
                    "software": {"app": __version__, "python": sys.version.split()[0], "pandas": pd.__version__,
                                 "numpy": np.__version__, "pyarrow": pa.__version__},
                    "identity": identity, "prices": prices, "membership": membership,
                    "files": {name: {"sha256": _sha(data), "bytes": len(data)}
                              for name, data in payloads.items()}}
        output = BytesIO()
        with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
            archive.writestr("manifest.json", _json(manifest))
            for name, data in payloads.items():
                archive.writestr(name, data)
        raw = output.getvalue()
        with FileLock(str(path) + ".lock", timeout=30):
            if path.exists():
                saved, _, descriptor = self._unpack(path.read_bytes())
                if saved["identity"] != identity:
                    raise ValueError("Existing study snapshot has an inconsistent identity")
                return descriptor
            self._atomic_write(path, raw)
        return {"id": identifier, "sha256": _sha(raw), "bytes": len(raw),
                "created_at": manifest["created_at"], "format_version": FORMAT_VERSION,
                "software": manifest["software"]}

    @staticmethod
    def _atomic_write(path, raw):
        temp = path.with_suffix("." + uuid4().hex + ".tmp")
        try:
            temp.write_bytes(raw)
            temp.replace(path)
        finally:
            temp.unlink(missing_ok=True)

    def decode(self, raw, descriptor, config: ScreenConfig):
        manifest, payloads, checked = self._unpack(raw, descriptor)
        try:
            identity = manifest["identity"]
            universe = pd.read_parquet(BytesIO(payloads["universe.parquet"]))
            prices = {ticker: pd.read_parquet(BytesIO(payloads[name])) for ticker, name in manifest["prices"].items()}
            membership = None
            if manifest["membership"]:
                m = manifest["membership"]
                membership = MembershipHistory.from_csv(
                    payloads["membership.csv"].decode("utf-8"), date.fromisoformat(m["coverage_start"]),
                    date.fromisoformat(m["coverage_end"]), m["source"])
            engine = StudyEngine(prices, universe, config, date.fromisoformat(identity["start"]),
                                 date.fromisoformat(identity["end"]), membership)
            if engine.fingerprint != identity["price_fingerprint"]:
                raise ValueError("Restored price fingerprint differs from the saved snapshot; "
                                 "the data or library representation changed")
            if (membership.digest if membership else None) != identity["membership_digest"]:
                raise ValueError("Restored membership differs from the saved source")
            return engine, checked
        except (KeyError, TypeError, AttributeError, OSError) as exc:
            raise ValueError(f"Could not restore study snapshot: {exc}") from exc

    def load(self, descriptor, config):
        return self.decode(self.read(descriptor), descriptor, config)[0]

    def import_snapshot(self, raw, descriptor, config):
        engine, checked = self.decode(raw, descriptor, config)
        path = self.path(checked["id"])
        with FileLock(str(path) + ".lock", timeout=30):
            if path.exists():
                existing = path.read_bytes()
                if _sha(existing) != checked["sha256"]:
                    # An input identity may have another valid container creation timestamp.
                    try:
                        _, _, previous = self._unpack(existing, {**checked, "sha256": _sha(existing)})
                        previous_engine, _ = self.decode(existing, previous, config)
                    except ValueError:
                        # A verified backup can repair a damaged archive without changing plan settings.
                        self._atomic_write(path, raw)
                    else:
                        engine, checked = previous_engine, previous
            else:
                self._atomic_write(path, raw)
        return engine, checked
