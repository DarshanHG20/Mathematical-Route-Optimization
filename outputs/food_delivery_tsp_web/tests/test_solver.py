from pathlib import Path
import sys
import unittest

PROJECT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_DIR))
from app import LOCATION_NAMES, SAMPLE_MATRIX_TEXT, parse_distance_matrix, solve_tsp, validate_location_names


class TestTspSolver(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.sample = parse_distance_matrix(SAMPLE_MATRIX_TEXT)

    def test_sample_minimum_route_and_distance(self):
        result = solve_tsp(self.sample)
        self.assertEqual(result["best_total"], 18)
        self.assertEqual(result["best_route"], (0, 1, 2, 3, 0))
        self.assertEqual([LOCATION_NAMES[i] for i in result["best_route"]], [
            "Restaurant", "City Market", "Bus Stand", "College", "Restaurant",
        ])

    def test_all_orders_and_three_distinct_tours_are_counted(self):
        result = solve_tsp(self.sample)
        self.assertEqual(result["permutation_count"], 6)
        self.assertEqual(result["unique_tour_count"], 3)
        self.assertEqual(len(result["tours"]), 3)
        self.assertEqual([tour["total"] for tour in result["tours"]], [18, 19, 21])

    def test_each_distinct_tour_has_the_expected_names_and_legs(self):
        result = solve_tsp(self.sample)
        rendered = [
            ([LOCATION_NAMES[index] for index in tour["route"]], tour["legs"], tour["total"])
            for tour in result["tours"]
        ]
        self.assertEqual(rendered, [
            (["Restaurant", "City Market", "Bus Stand", "College", "Restaurant"], [4, 3, 4, 7], 18),
            (["Restaurant", "City Market", "College", "Bus Stand", "Restaurant"], [4, 5, 4, 6], 19),
            (["Restaurant", "Bus Stand", "City Market", "College", "Restaurant"], [6, 3, 5, 7], 21),
        ])

    def test_best_route_starts_returns_and_visits_once(self):
        route = solve_tsp(self.sample)["best_route"]
        self.assertEqual(route[0], 0)
        self.assertEqual(route[-1], 0)
        self.assertEqual(sorted(route[1:-1]), [1, 2, 3])

    def test_independent_verification_passes(self):
        result = solve_tsp(self.sample)
        self.assertEqual(result["verified_total"], result["best_total"])
        self.assertTrue(all(result["checks"].values()))

    def test_accepts_the_valid_sample_matrix(self):
        self.assertEqual(self.sample, [
            [0, 4, 6, 7],
            [4, 0, 3, 5],
            [6, 3, 0, 4],
            [7, 5, 4, 0],
        ])

    def test_accepts_custom_unique_place_names(self):
        names = validate_location_names([" Depot West ", "Market", "Bus Stand", "Campus"])
        self.assertEqual(names, ["Depot West", "Market", "Bus Stand", "Campus"])

    def test_rejects_duplicate_custom_place_names(self):
        with self.assertRaisesRegex(ValueError, "unique"):
            validate_location_names(["Depot", "Market", "market", "Campus"])

    def test_rejects_blank_custom_place_name(self):
        with self.assertRaisesRegex(ValueError, "Enter a name"):
            validate_location_names(["Depot", "Market", "   ", "Campus"])

    def test_rejects_wrong_number_of_locations(self):
        with self.assertRaisesRegex(ValueError, "exactly 4 matrix rows"):
            parse_distance_matrix("0,1,2\n1,0,3\n2,3,0")

    def test_rejects_non_square_input(self):
        with self.assertRaisesRegex(ValueError, "Row 2 needs"):
            parse_distance_matrix("0,1,2,3\n1,0,3\n2,3,0,4\n3,4,4,0")

    def test_rejects_asymmetric_input(self):
        with self.assertRaisesRegex(ValueError, "symmetric"):
            parse_distance_matrix("0,1,2,3\n1,0,3,4\n4,3,0,5\n3,4,5,0")

    def test_rejects_negative_distance(self):
        with self.assertRaisesRegex(ValueError, "negative"):
            parse_distance_matrix("0,-1,2,3\n-1,0,3,4\n2,3,0,5\n3,4,5,0")

    def test_rejects_nonzero_diagonal(self):
        with self.assertRaisesRegex(ValueError, "diagonal must be zero"):
            parse_distance_matrix("1,1,2,3\n1,0,3,4\n2,3,0,5\n3,4,5,0")

    def test_rejects_non_numeric_distance(self):
        with self.assertRaisesRegex(ValueError, "not a number"):
            parse_distance_matrix("0,one,2,3\none,0,3,4\n2,3,0,5\n3,4,5,0")


if __name__ == "__main__":
    unittest.main()
