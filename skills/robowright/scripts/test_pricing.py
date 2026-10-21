#!/usr/bin/env python3
"""Tests for pricing.py, the one loader every report prices through, written from the accounting
brief's U2 behaviors file before the loader existed.

    python3 skills/robowright/scripts/test_pricing.py

pricing.py is loaded by path. Every test but one writes a synthetic pricing file into a scratch
directory and passes its path to load(), and every staleness test passes its own `today`, so no
test depends on the real date or on the shipped pricing.json. The one exception,
ShippedFileTests, reads the shipped skills/robowright/pricing.json on purpose: it is the check
that the file holds the six rows the three copied price tables held.

The pricing file (Language → pricing file):

    {"updated_at": "YYYY-MM-DD", "source": "…", "default": <row>,
     "models": {"<id prefix>": <row>, …}}      row = {input, output, cache_read, cache_write_5m, cache_write_1h}

USD per million tokens. Rows below are synthetic and distinct in every field, so a crossed wire
between two rows shows in any rate compared.
"""

import contextlib
import datetime
import importlib.util
import io
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

HERE = Path(__file__).resolve().parent
SHIPPED_PRICING = HERE.parent / "pricing.json"


def load_pricing():
    spec = importlib.util.spec_from_file_location("pricing", HERE / "pricing.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


PRICING = load_pricing()

LONGER = "claude-opus-5-5"
SHORTER = "claude-opus-5"
LONGER_ROW = {"input": 4.0, "output": 20.0, "cache_read": 0.2, "cache_write_5m": 5.0, "cache_write_1h": 8.0}
SHORTER_ROW = {"input": 5.0, "output": 25.0, "cache_read": 0.5, "cache_write_5m": 6.25, "cache_write_1h": 10.0}
DEFAULT_ROW = {"input": 7.0, "output": 35.0, "cache_read": 0.7, "cache_write_5m": 8.75, "cache_write_1h": 14.0}
UPDATED_AT = "2026-09-24"


class PricingCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name).resolve()

    def tearDown(self):
        self.tmp.cleanup()

    # ------------------------------------------------------------ given

    def given_pricing(self, models, updated_at=UPDATED_AT, default=DEFAULT_ROW):
        """A pricing file with `models` written in the order given — JSON object order is file order."""
        path = self.dir / "pricing.json"
        path.write_text(json.dumps({"updated_at": updated_at, "source": "sample price page",
                                    "default": default, "models": models}, indent=2) + "\n")
        return path

    def given_shorter_listed_first(self):
        return self.given_pricing({SHORTER: SHORTER_ROW, LONGER: LONGER_ROW})

    def given_longer_listed_first(self):
        return self.given_pricing({LONGER: LONGER_ROW, SHORTER: SHORTER_ROW})

    # ------------------------------------------------------------ when

    def load_quietly(self, path):
        """load(path), with what it wrote to stderr."""
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            prices = PRICING.load(path)
        return prices, err.getvalue()


# ------------------------------------------------------------ R1 · the longest matching prefix wins, whatever the key order

class PrefixMatchTests(PricingCase):
    def test_the_longer_prefix_wins__when_it_is_listed_after_the_shorter_one(self):
        """claude-opus-5 is a prefix of claude-opus-5-5; a first-match loader over this order prices every Opus 5.5 request at Opus 5 rates (D9, hotspot: "the test with the keys reversed")."""
        prices = PRICING.load(self.given_shorter_listed_first())

        self.assertEqual(prices.rates("claude-opus-5-5"), LONGER_ROW)

    def test_the_longer_prefix_wins__when_it_is_listed_before_the_shorter_one(self):
        """The order the three copied tables relied on must still price Opus 5.5 at its own row (D9: "regardless of key order")."""
        prices = PRICING.load(self.given_longer_listed_first())

        self.assertEqual(prices.rates("claude-opus-5-5"), LONGER_ROW)

    def test_a_dated_id_takes_the_row_of_its_longest_matching_prefix(self):
        """Usage records carry dated API ids; a loader that needs an exact key prices every dated id at the default row (Language: "<id prefix>")."""
        prices = PRICING.load(self.given_shorter_listed_first())

        self.assertEqual(prices.rates("claude-opus-5-5-20260901"), LONGER_ROW)

    def test_an_id_only_the_shorter_prefix_matches_takes_the_shorter_row(self):
        """claude-opus-5-20260101 does not start with claude-opus-5-5; picking the longest key without checking it matches prices Opus 5 as Opus 5.5 (D9)."""
        prices = PRICING.load(self.given_longer_listed_first())

        self.assertEqual(prices.rates("claude-opus-5-20260101"), SHORTER_ROW)


# ------------------------------------------------------------ R2 · an id no prefix matches takes the default row

class DefaultRowTests(PricingCase):
    def test_an_id_no_prefix_matches_takes_the_default_row(self):
        """A model released after the file was last updated is still priced, at the Owner's chosen fallback (D9: "uses the default row for an unknown id")."""
        prices = PRICING.load(self.given_shorter_listed_first())

        self.assertEqual(prices.rates("claude-sample-9"), DEFAULT_ROW)

    def test_a_key_that_appears_inside_the_id_but_does_not_start_it_is_no_match(self):
        """The keys are id prefixes; a substring match prices a vendor-wrapped id at a row it does not name (Language: "<id prefix>")."""
        prices = PRICING.load(self.given_shorter_listed_first())

        self.assertEqual(prices.rates("vendor-claude-opus-5-5"), DEFAULT_ROW)


# ------------------------------------------------------------ R3 · a missing or unreadable file gives no rates and says so once

class MissingFileTests(PricingCase):
    def test_every_rate_is_none__when_the_file_does_not_exist(self):
        """Without the file there is no honest price; a fallback rate would print a dollar figure nobody set (D9: "makes every USD figure null")."""
        prices, _ = self.load_quietly(self.dir / "nowhere" / "pricing.json")

        self.assertIsNone(prices.rates("claude-opus-5-5"))
        self.assertIsNone(prices.rates("claude-sample-9"))

    def test_has_no_as_of_date__when_the_file_does_not_exist(self):
        """A record written without the file carries price_as_of null; any date here would claim prices that were never read (§6: "pricing.json.updated_at, or null")."""
        prices, _ = self.load_quietly(self.dir / "nowhere" / "pricing.json")

        self.assertIsNone(prices.as_of)

    def test_says_so_in_exactly_one_stderr_line__however_many_ids_are_then_priced(self):
        """One line per load, not one per request — a transcript of thousands of requests must not bury the report (D9: "with one stderr line"; the line names the file, assumed Q4)."""
        missing = self.dir / "nowhere" / "pricing.json"
        err = io.StringIO()

        with contextlib.redirect_stderr(err):
            prices = PRICING.load(missing)
            for model in ("claude-opus-5-5", "claude-sonnet-5", "claude-sample-9"):
                prices.rates(model)

        lines = [line for line in err.getvalue().splitlines() if line.strip()]
        self.assertEqual(len(lines), 1, err.getvalue())
        self.assertIn(str(missing), lines[0])

    def test_every_rate_is_none_with_one_stderr_line__when_the_file_is_not_json(self):
        """A hand-edited file with a syntax slip is unreadable, not a crash in every report that prices (D9: "a missing or unreadable file")."""
        path = self.dir / "pricing.json"
        path.write_text('{"updated_at": "2026-09-24", "models": {\n')

        prices, err = self.load_quietly(path)

        self.assertIsNone(prices.rates("claude-opus-5-5"))
        self.assertIsNone(prices.as_of)
        self.assertEqual(len([line for line in err.splitlines() if line.strip()]), 1, err)

    def test_every_rate_is_none_with_one_stderr_line__when_the_json_has_the_wrong_shape(self):
        """An Owner's monthly hand edit that parses but mistypes the date or drops a rate is as unreadable as a syntax slip; a crash here loses every report's token facts (D9: "a missing or unreadable file"; gate U2 F1)."""
        good = {"updated_at": UPDATED_AT, "source": "s", "default": DEFAULT_ROW, "models": {SHORTER: SHORTER_ROW}}
        rateless = dict(SHORTER_ROW)
        del rateless["cache_write_1h"]
        shapes = {
            "mistyped date": dict(good, updated_at="2026-10-1"),
            "no updated_at": {k: v for k, v in good.items() if k != "updated_at"},
            "empty object": {},
            "a list": [good],
            "default missing a rate": dict(good, default=rateless),
            "a model row missing a rate": dict(good, models={SHORTER: rateless}),
            "models not an object": dict(good, models=[SHORTER_ROW]),
        }
        for name, table in shapes.items():
            with self.subTest(shape=name):
                path = self.dir / "pricing.json"
                path.write_text(json.dumps(table))

                prices, err = self.load_quietly(path)

                self.assertIsNone(prices.rates(SHORTER))
                self.assertIsNone(prices.as_of)
                self.assertFalse(prices.stale(datetime.date(2027, 1, 1)))
                self.assertEqual(len([line for line in err.splitlines() if line.strip()]), 1, err)

    def test_is_not_called_stale__when_the_file_does_not_exist(self):
        """The missing-file line is the one line a report prints about prices; a stale warning on top would make it two (D9 "one stderr line"; assumed Q6)."""
        prices, _ = self.load_quietly(self.dir / "nowhere" / "pricing.json")

        self.assertFalse(prices.stale(datetime.date(2027, 1, 1)))


# ------------------------------------------------------------ R4 · every report quotes the file's date, and a file more than 30 days old is stale

class DateAndStalenessTests(PricingCase):
    def test_as_of_is_the_file_s_updated_at(self):
        """Every report prints `prices as of <updated_at>` and every record carries it as price_as_of; a date from anywhere else misdates every estimate (D2, §6)."""
        prices = PRICING.load(self.given_pricing({LONGER: LONGER_ROW}, updated_at="2026-09-10"))

        self.assertEqual(prices.as_of, "2026-09-10")

    def test_is_not_stale__at_30_days(self):
        """2026-09-24 to 2026-10-24 is 30 days — not "more than 30", so no warning yet; warning a day early trains the Owner to ignore it (Language: stale)."""
        prices = PRICING.load(self.given_pricing({LONGER: LONGER_ROW}, updated_at="2026-09-24"))

        self.assertFalse(prices.stale(datetime.date(2026, 10, 24)))

    def test_is_stale__at_31_days(self):
        """2026-09-24 to 2026-10-25 is 31 days; prices change often enough that a file this old is the warning's whole reason (D2, U2 row: "a warning when updated_at is 31 days old")."""
        prices = PRICING.load(self.given_pricing({LONGER: LONGER_ROW}, updated_at="2026-09-24"))

        self.assertTrue(prices.stale(datetime.date(2026, 10, 25)))

    def test_a_stale_file_still_prices(self):
        """Stale is a warning, not a refusal: the report keeps its estimate (Language: "every report still prices with it and prints one warning line")."""
        prices = PRICING.load(self.given_shorter_listed_first())

        self.assertTrue(prices.stale(datetime.date(2027, 1, 1)))
        self.assertEqual(prices.rates("claude-opus-5-5"), LONGER_ROW)


# ------------------------------------------------------------ R5 · the shipped file holds the six rows the copied tables held

class ShippedFileTests(unittest.TestCase):
    def shipped_rates(self, model):
        env = {k: v for k, v in os.environ.items() if k not in ("ROBOWRIGHT_PRICING_FILE", "ROBOWRIGHT_PRICING_NOW")}
        with mock.patch.dict(os.environ, env, clear=True):
            return PRICING.load().rates(model)

    def test_sonnet_5_5_is_priced_at_its_own_cache_read_rate__not_the_sonnet_5_row_its_id_extends(self):
        """claude-sonnet-5 prefixes claude-sonnet-5-5, so without its own row every Sonnet 5.5 cache read, the largest token class, is priced at Sonnet 5's $0.20 instead of $0.10 (pricing page, 2026-10-12, footnote 2: 0.05x base)."""
        self.assertEqual(self.shipped_rates("claude-sonnet-5-5"),
                         {"input": 2.00, "output": 10.00, "cache_read": 0.10, "cache_write_5m": 2.50, "cache_write_1h": 4.00})

    def test_haiku_5_5_is_priced_at_its_short_prompt_tier__not_the_opus_5_default(self):
        """No key prefixes claude-haiku-5-5, so it fell to the Opus 5 default, about 50x its price; the row is the up-to-100K-prompt tier (pricing page, 2026-10-12), the flat schema holding one tier (Owner's call)."""
        self.assertEqual(self.shipped_rates("claude-haiku-5-5"),
                         {"input": 0.10, "output": 0.50, "cache_read": 0.01, "cache_write_5m": 0.125, "cache_write_1h": 0.20})

    def test_the_shipped_file_is_found_by_default_and_holds_the_current_rows(self):
        """The shipped file carries run-cost.py's six rows at the accounting base (:46-54), Sonnet 5.5 and Haiku 5.5 added 2026-10-12, and the Opus 5 fallback (:56), dated with a source — a slipped digit mis-prices every report (U2 row; default row assumed Q1)."""
        env = {k: v for k, v in os.environ.items() if k not in ("ROBOWRIGHT_PRICING_FILE", "ROBOWRIGHT_PRICING_NOW")}
        with mock.patch.dict(os.environ, env, clear=True):
            prices = PRICING.load()
        shipped = json.loads(SHIPPED_PRICING.read_text())

        self.assertEqual(prices.as_of, "2026-10-12")
        self.assertEqual(shipped["updated_at"], "2026-10-12")
        self.assertIsInstance(shipped["source"], str)
        self.assertTrue(shipped["source"].strip())
        self.assertEqual(shipped["models"], {
            "claude-opus-5-5": {"input": 4.00, "output": 20.00, "cache_read": 0.20, "cache_write_5m": 5.00, "cache_write_1h": 8.00},
            "claude-opus-5": {"input": 5.00, "output": 25.00, "cache_read": 0.50, "cache_write_5m": 6.25, "cache_write_1h": 10.00},
            "claude-fable-5-1": {"input": 10.00, "output": 50.00, "cache_read": 0.25, "cache_write_5m": 12.50, "cache_write_1h": 20.00},
            "claude-fable-5": {"input": 10.00, "output": 50.00, "cache_read": 1.00, "cache_write_5m": 12.50, "cache_write_1h": 20.00},
            "claude-sonnet-5-5": {"input": 2.00, "output": 10.00, "cache_read": 0.10, "cache_write_5m": 2.50, "cache_write_1h": 4.00},
            "claude-sonnet-5": {"input": 2.00, "output": 10.00, "cache_read": 0.20, "cache_write_5m": 2.50, "cache_write_1h": 4.00},
            "claude-haiku-5-5": {"input": 0.10, "output": 0.50, "cache_read": 0.01, "cache_write_5m": 0.125, "cache_write_1h": 0.20},
            "claude-haiku-4-5": {"input": 1.00, "output": 5.00, "cache_read": 0.10, "cache_write_5m": 1.25, "cache_write_1h": 2.00},
        })
        self.assertEqual(shipped["default"],
                         {"input": 5.00, "output": 25.00, "cache_read": 0.50, "cache_write_5m": 6.25, "cache_write_1h": 10.00})
        self.assertEqual(prices.rates("claude-fable-5-1-20260801"),
                         {"input": 10.00, "output": 50.00, "cache_read": 0.25, "cache_write_5m": 12.50, "cache_write_1h": 20.00})


if __name__ == "__main__":
    unittest.main()
