import json
import tempfile
import unittest
from pathlib import Path

import pandas as pd

from insightpilot.config import ROOT
from insightpilot.ingestion import (
    LOADERS,
    clean,
    get_schema,
    ingest_directory,
    ingest_file,
    load_file,
    profile,
    register_loader,
    snake,
)


class IngestionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())

    def test_snake_case_headers(self):
        self.assertEqual(snake("Order ID"), "order_id")
        self.assertEqual(snake("  Refund Amount ($) "), "refund_amount")
        self.assertEqual(snake("***"), "column")

    def test_loads_every_supported_format(self):
        frame = pd.DataFrame({"A Col": [1, 2], "B": ["x", "y"]})
        (self.tmp / "f.csv").write_text(frame.to_csv(index=False))
        (self.tmp / "f.tsv").write_text(frame.to_csv(index=False, sep="\t"))
        (self.tmp / "f.json").write_text(json.dumps({"records": frame.to_dict("records")}))
        (self.tmp / "f.jsonl").write_text("\n".join(json.dumps(r) for r in frame.to_dict("records")))
        frame.to_excel(self.tmp / "f.xlsx", index=False)
        for name in ("f.csv", "f.tsv", "f.json", "f.jsonl", "f.xlsx"):
            loaded = load_file(self.tmp / name)
            self.assertEqual(len(loaded), 2, name)
            self.assertEqual(list(clean(loaded)[0].columns), ["a_col", "b"], name)

    def test_pipe_delimited_text_loader(self):
        path = self.tmp / "pipe.txt"
        path.write_text("id|name\n1|Asha\n2|Ravi\n")
        loaded = clean(load_file(path))[0]
        self.assertEqual(loaded.to_dict("records"), [{"id": 1, "name": "Asha"}, {"id": 2, "name": "Ravi"}])

    def test_parquet_loader(self):
        path = self.tmp / "data.parquet"
        pd.DataFrame({"id": [1, 2], "name": ["Asha", "Ravi"]}).to_parquet(path, index=False)
        loaded = clean(load_file(path))[0]
        self.assertEqual(loaded.to_dict("records"), [{"id": 1, "name": "Asha"}, {"id": 2, "name": "Ravi"}])

    def test_unsupported_format_is_rejected(self):
        with self.assertRaises(ValueError):
            load_file(self.tmp / "notes.pdf")

    def test_register_new_format(self):
        path = self.tmp / "data.psv"
        path.write_text("id|name\n1|Asha\n2|Ravi\n")
        register_loader(".psv", lambda p: pd.read_csv(p, sep="|"))
        try:
            self.assertEqual(len(load_file(path)), 2)
        finally:
            LOADERS.pop(".psv", None)

    def test_clean_removes_empty_duplicates_and_parses_dates(self):
        frame = pd.DataFrame({
            "Order Date": ["2025-01-05", "2025-01-05", None, "05/02/2025"],
            "Region ": [" North ", " North ", None, "South"],
            "Region": [1, 1, None, 2],
        })
        cleaned, notes = clean(frame)
        self.assertEqual(notes["empty_rows_removed"], 1)
        self.assertEqual(notes["duplicates_removed"], 1)
        self.assertEqual(len(cleaned), 2)
        self.assertEqual(list(cleaned.columns), ["order_date", "region", "region_2"])
        self.assertEqual(cleaned["region"].tolist(), ["North", "South"])
        self.assertTrue(all(len(v) == 10 for v in cleaned["order_date"]))

    def test_profile_flags_negative_and_missing(self):
        frame = pd.DataFrame({"qty": [1, -2, 3, 4], "note": ["a", None, None, None]})
        report = profile(frame)
        text = " ".join(report["issues"])
        self.assertIn("qty: contains negative values", text)
        self.assertIn("note", text)

    def test_profile_reports_inferred_types_null_percent_and_duplicates(self):
        report = profile(pd.DataFrame({"qty": [1, 1, None, 4], "label": ["x", None, None, "y"]}))
        qty, label = report["columns"]
        self.assertEqual(qty["null_pct"], 25.0)
        self.assertEqual(qty["duplicate_count"], 1)
        self.assertEqual(label["null_pct"], 50.0)
        self.assertEqual(label["inferred_type"], "string")

    def test_ingest_sample_directory_into_sqlite(self):
        db = self.tmp / "t.db"
        reports = ingest_directory(ROOT / "data" / "sample", db)
        self.assertEqual({r["table"] for r in reports}, {"sales", "returns", "targets"})
        schema = get_schema(db)
        self.assertIn("revenue", [c["name"] for c in schema["sales"]])
        self.assertIn("refund_amount", [c["name"] for c in schema["returns"]])

    def test_ingest_file_replaces_table(self):
        path = self.tmp / "t.csv"
        path.write_text("a,b\n1,2\n")
        db = self.tmp / "t.db"
        ingest_file(path, db)
        path.write_text("a,b\n1,2\n3,4\n")
        self.assertEqual(ingest_file(path, db)["rows"], 2)


if __name__ == "__main__":
    unittest.main()
