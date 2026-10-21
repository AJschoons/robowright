#!/usr/bin/env python3
"""
pricing.py — the one loader for skills/robowright/pricing.json, the Owner-maintained price table
every report estimates USD from.

    {"updated_at": "YYYY-MM-DD", "source": "…", "default": <row>, "models": {"<id prefix>": <row>, …}}
    row = {input, output, cache_read, cache_write_5m, cache_write_1h}, USD per million tokens

The file is $ROBOWRIGHT_PRICING_FILE, else the pricing.json beside this scripts directory. A model
id takes the row of its longest matching prefix, else `default`. A missing, unreadable or misshapen file
prints one stderr line and prices nothing: every rate and every USD figure is None, and the token
counts a report prints are untouched. $ROBOWRIGHT_PRICING_NOW (YYYY-MM-DD) stands in for today when
deciding whether the file is stale.
"""

import datetime
import json
import os
import sys
from pathlib import Path

DEFAULT_FILE = Path(__file__).resolve().parent.parent / "pricing.json"
STALE_AFTER_DAYS = 30


class Prices:
    def __init__(self, path, table):
        self.path = path
        self.table = table
        self.as_of = table["updated_at"] if table else None

    def rates(self, model):
        if not self.table:
            return None
        matches = [key for key in self.table["models"] if model.startswith(key)]
        if not matches:
            return self.table["default"]
        return self.table["models"][max(matches, key=len)]

    def usage_cost(self, model, usage):
        """USD for one usage record, or None without prices."""
        rates = self.rates(model)
        if rates is None:
            return None
        cost = usage.get("input_tokens", 0) * rates["input"] + usage.get("output_tokens", 0) * rates["output"]
        cost += usage.get("cache_read_input_tokens", 0) * rates["cache_read"]
        breakdown = usage.get("cache_creation") or {}
        if breakdown:
            cost += breakdown.get("ephemeral_5m_input_tokens", 0) * rates["cache_write_5m"]
            cost += breakdown.get("ephemeral_1h_input_tokens", 0) * rates["cache_write_1h"]
        else:
            cost += usage.get("cache_creation_input_tokens", 0) * rates["cache_write_5m"]
        return cost / 1_000_000

    def age_days(self, today=None):
        if today is None:
            pinned = os.environ.get("ROBOWRIGHT_PRICING_NOW")
            today = datetime.date.fromisoformat(pinned) if pinned else datetime.date.today()
        return (today - datetime.date.fromisoformat(self.as_of)).days

    def stale(self, today=None):
        if not self.table:
            return False
        return self.age_days(today) > STALE_AFTER_DAYS

    def as_of_line(self):
        return f"prices as of {self.as_of}" if self.as_of else "no pricing file read"

    def stale_warning(self):
        """The one line a report prints when the file is stale, else None."""
        if not self.stale():
            return None
        return (f"pricing: prices are stale — {self.path} was updated {self.as_of}, "
                f"{self.age_days()} days ago; USD figures are estimates at those rates")


RATES = ("input", "output", "cache_read", "cache_write_5m", "cache_write_1h")


def check_shape(table):
    """Raises ValueError unless `table` is a pricing file every report can price from."""
    if not isinstance(table, dict) or not isinstance(table.get("models"), dict):
        raise ValueError("not an object with a models object")
    datetime.date.fromisoformat(table.get("updated_at") if isinstance(table.get("updated_at"), str) else "")
    for name, row in [("default", table.get("default")), *table["models"].items()]:
        if not isinstance(row, dict) or not all(isinstance(row.get(rate), (int, float)) for rate in RATES):
            raise ValueError(f"row {name} lacks one of {', '.join(RATES)}")


def load(path=None):
    path = Path(path or os.environ.get("ROBOWRIGHT_PRICING_FILE") or DEFAULT_FILE)
    try:
        table = json.loads(path.read_text())
        check_shape(table)
    except (OSError, ValueError) as error:
        print(f"pricing: no prices read from {path} ({error.__class__.__name__}: {error}); every USD figure is null",
              file=sys.stderr)
        return Prices(path, None)
    return Prices(path, table)
