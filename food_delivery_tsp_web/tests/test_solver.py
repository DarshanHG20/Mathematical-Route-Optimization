from dataclasses import dataclass
from math import isclose
from pathlib import Path
import sys
import unittest

PROJECT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_DIR))
from solver import Result, solve, verify


@dataclass
class FixtureMatrix:
    nodes: tuple
    values: tuple

    def cost(self, start, end):
        return self.values[self.nodes.index(start)][self.nodes.index(end)]

    def validate(self):
        if len(self.nodes) != len(self.values) or any(len(row) != len(self.nodes) for row in self.values):
            return False, "not square"
        if len(set(self.nodes)) != len(self.nodes):
            return False, "duplicate node"
        for i, row in enumerate(self.values):
            for j, value in enumerate(row):
                if value is None or value < 0 or (i == j and value != 0):
                    return False, "invalid edge"
        return True, "valid"

    @property
    def symmetric(self):
        return all(self.values[i][j] == self.values[j][i] for i in range(len(self.nodes)) for j in range(i + 1, len(self.nodes)))


def symmetric_fixture():
    return FixtureMatrix(
        (101, 205, 307, 409),
        (
            (0, 4, 6, 7),
            (4, 0, 3, 5),
            (6, 3, 0, 4),
            (7, 5, 4, 0),
        ),
    )


class TestTspSolver(unittest.TestCase):
    def test_exact_symmetric_solve_has_three_distinct_closed_tours(self):
        matrix = symmetric_fixture()
        result = solve(matrix, 101, [205, 307, 409])
        self.assertEqual(result.algorithm, "Exact enumeration")
        self.assertTrue(result.optimal)
        self.assertEqual(result.total, 18)
        self.assertEqual(result.tours_compared, 3)
        self.assertEqual(len(result.alternatives) + 1, 3)
        self.assertEqual(result.route, (101, 205, 307, 409, 101))
        self.assertTrue(all(verify(matrix, result, 101, [205, 307, 409]).values()))

    def test_asymmetric_solve_keeps_reverse_tours_distinct(self):
        matrix = FixtureMatrix(
            ("depot", "A", "B", "C"),
            (
                (0, 2, 9, 8),
                (7, 0, 3, 6),
                (4, 5, 0, 2),
                (3, 1, 7, 0),
            ),
        )
        result = solve(matrix, "depot", ["A", "B", "C"])
        self.assertFalse(matrix.symmetric)
        self.assertEqual(result.tours_compared, 6)
        self.assertEqual(len(result.alternatives) + 1, 6)
        self.assertTrue(all(verify(matrix, result, "depot", ["A", "B", "C"]).values()))
        forward = next(total for route, total in [(result.route, result.total), *result.alternatives] if route == ("depot", "A", "B", "C", "depot"))
        reverse = next(total for route, total in [(result.route, result.total), *result.alternatives] if route == ("depot", "C", "B", "A", "depot"))
        self.assertNotEqual(forward, reverse)

    def test_single_stop_is_a_valid_closed_tour(self):
        matrix = FixtureMatrix(("hub", "only"), ((0, 4), (6, 0)))
        result = solve(matrix, "hub", ["only"])
        self.assertEqual(result.route, ("hub", "only", "hub"))
        self.assertEqual(result.total, 10)
        self.assertTrue(all(verify(matrix, result, "hub", ["only"]).values()))

    def test_held_karp_solves_moderate_instance_exactly(self):
        nodes = tuple(range(17))
        values = tuple(tuple(0 if i == j else ((i * 17 + j * 11) % 29) + 1 for j in nodes) for i in nodes)
        matrix = FixtureMatrix(nodes, values)
        result = solve(matrix, 0, list(nodes[1:11]))
        self.assertEqual(result.algorithm, "Held-Karp dynamic programming")
        self.assertTrue(result.optimal)
        self.assertTrue(all(verify(matrix, result, 0, list(nodes[1:11])).values()))

    def test_large_instance_uses_labelled_heuristic_and_visits_every_stop(self):
        nodes = tuple(range(18))
        values = tuple(tuple(0 if i == j else abs(i - j) + 1 for j in nodes) for i in nodes)
        matrix = FixtureMatrix(nodes, values)
        result = solve(matrix, 0, list(nodes[1:17]))
        self.assertEqual(result.algorithm, "Nearest-neighbor with 2-opt")
        self.assertFalse(result.optimal)
        checks = verify(matrix, result, 0, list(nodes[1:17]))
        self.assertTrue(all(checks.values()))

    def test_rejects_missing_depot_and_no_stops(self):
        matrix = symmetric_fixture()
        with self.assertRaisesRegex(ValueError, "selected node"):
            solve(matrix, "unknown", [205])
        with self.assertRaisesRegex(ValueError, "at least one"):
            solve(matrix, 101, [])

    def test_rejects_depot_as_stop_and_duplicate_stops(self):
        matrix = symmetric_fixture()
        with self.assertRaisesRegex(ValueError, "depot"):
            solve(matrix, 101, [101])
        with self.assertRaisesRegex(ValueError, "unique"):
            solve(matrix, 101, [205, 205])

    def test_verifier_detects_a_tampered_total(self):
        matrix = symmetric_fixture()
        result = solve(matrix, 101, [205, 307, 409])
        tampered = Result(result.route, result.legs, result.total + 10, result.algorithm, result.optimal, result.alternatives)
        checks = verify(matrix, tampered, 101, [205, 307, 409])
        self.assertFalse(checks["The displayed total matches an independent sum"])


if __name__ == "__main__":
    unittest.main()
