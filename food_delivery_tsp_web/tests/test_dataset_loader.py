from importlib.util import find_spec
from pathlib import Path
import sys
import tempfile
from types import ModuleType
import unittest
from unittest.mock import patch

PROJECT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_DIR))

OPENPYXL_AVAILABLE = find_spec("openpyxl") is not None
if not OPENPYXL_AVAILABLE:
    openpyxl_stub = ModuleType("openpyxl")
    openpyxl_stub.load_workbook = lambda *_args, **_kwargs: None
    sys.modules["openpyxl"] = openpyxl_stub

import dataset_loader
from dataset_loader import DatasetError, Matrix


class FakeSheet:
    title = "Research matrix"

    def __init__(self, rows):
        self.rows = rows

    def iter_rows(self, values_only=False):
        return iter(self.rows)


class TestWorkbookMatrixParsing(unittest.TestCase):
    def test_finds_headers_ignores_formatted_blank_rows_and_aligns_labels(self):
        sheet = FakeSheet(
            [
                (None, 10, 20, 30),
                (20, 4, 0, 7),
                (10, 0, 4, 6),
                (30, 6, 7, 0),
                (None, None, None, None),
                (None, None, None, None),
            ]
        )
        matrix = dataset_loader._read_sheet(sheet, 1, "distance", "fixture.xlsx")
        self.assertEqual(matrix.nodes, (10, 20, 30))
        self.assertEqual(matrix.values, ((0.0, 4.0, 6.0), (4.0, 0.0, 7.0), (6.0, 7.0, 0.0)))
        self.assertTrue(matrix.symmetric)

    def test_rejects_duplicate_or_mismatched_row_labels(self):
        duplicate = FakeSheet([(None, 1, 2), (1, 0, 4), (1, 4, 0)])
        with self.assertRaisesRegex(DatasetError, "repeats row identifier"):
            dataset_loader._read_sheet(duplicate, 1, "distance", "fixture.xlsx")
        missing = FakeSheet([(None, 1, 2, 3), (1, 0, 4, 5), (2, 4, 0, 6)])
        with self.assertRaisesRegex(DatasetError, "identifiers differ"):
            dataset_loader._read_sheet(missing, 1, "distance", "fixture.xlsx")

    def test_invalid_and_missing_costs_are_not_replaced_with_zero(self):
        missing = FakeSheet([(None, 1, 2), (1, 0, None), (2, 3, 0)])
        invalid = FakeSheet([(None, 1, 2), (1, 0, "closed"), (2, 3, 0)])
        for sheet in (missing, invalid):
            with self.subTest(sheet=sheet):
                with self.assertRaisesRegex(DatasetError, "Missing value"):
                    dataset_loader._read_sheet(sheet, 1, "distance", "fixture.xlsx")


@unittest.skipUnless(OPENPYXL_AVAILABLE, "Install requirements.txt to read the Excel workbooks.")
class TestRealResearchMatrices(unittest.TestCase):
    def test_all_nine_days_and_all_four_workbooks_load(self):
        self.assertEqual(dataset_loader.days(), list(range(1, 10)))
        for day in range(1, 10):
            for kind in dataset_loader.PREFIX:
                with self.subTest(day=day, kind=kind):
                    matrix = dataset_loader.load(day, kind)
                    valid, message = matrix.validate()
                    self.assertTrue(valid, message)
                    self.assertEqual(matrix.day, day)
                    self.assertEqual(matrix.kind, kind)
                    self.assertGreater(len(matrix.nodes), 1)
                    self.assertEqual(len(matrix.values), len(matrix.nodes))
                    self.assertTrue(all(len(row) == len(matrix.nodes) for row in matrix.values))
                    self.assertTrue(Path(matrix.source_file).is_file())

    def test_headers_and_row_identifiers_are_preserved(self):
        matrix = dataset_loader.load(1, "distance")
        self.assertEqual(matrix.nodes[0], 0)
        self.assertEqual(matrix.nodes[-1], 78)
        self.assertEqual(matrix.cost(0, 1), 17.9)
        self.assertEqual(matrix.values[1][0], 18.0)

    def test_summary_excludes_diagonal_and_reports_directionality(self):
        matrix = dataset_loader.load(1, "distance")
        stats = dataset_loader.summary(matrix)
        self.assertEqual(stats["nodes"], len(matrix.nodes))
        self.assertEqual(stats["directed_edges"], len(matrix.nodes) * (len(matrix.nodes) - 1))
        self.assertGreaterEqual(stats["min"], 0)
        self.assertGreaterEqual(stats["max"], stats["min"])
        self.assertGreater(stats["avg"], 0)

    def test_missing_workbook_is_reported_clearly(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "day_10").mkdir()
            with patch.object(dataset_loader, "ROOT", root):
                dataset_loader.load.cache_clear()
                with self.assertRaisesRegex(FileNotFoundError, "missing"):
                    dataset_loader.load(10, "distance")
        dataset_loader.load.cache_clear()

    def test_invalid_values_duplicates_and_nonzero_diagonal_are_rejected(self):
        cases = [
            (Matrix(1, "distance", (1, 2), ((0.0, None), (2.0, 0.0))), "Missing value"),
            (Matrix(1, "distance", (1, 2), ((0.0, -1.0), (2.0, 0.0))), "Negative value"),
            (Matrix(1, "distance", (1, 1), ((0.0, 0.0), (0.0, 0.0))), "duplicated"),
            (Matrix(1, "distance", (1, 2), ((1.0, 1.0), (2.0, 0.0))), "must be zero"),
        ]
        for matrix, message in cases:
            with self.subTest(message=message):
                valid, result = matrix.validate()
                self.assertFalse(valid)
                self.assertIn(message, result)


if __name__ == "__main__":
    unittest.main()
