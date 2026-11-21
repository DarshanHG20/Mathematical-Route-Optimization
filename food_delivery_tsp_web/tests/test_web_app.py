from http.client import HTTPConnection
from pathlib import Path
import sys
from threading import Thread
from types import ModuleType
import unittest
from urllib.parse import urlencode

PROJECT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_DIR))

# Web-route tests use injected matrices. This keeps HTTP and rendering tests
# runnable even when the optional Excel reader has not been installed yet.
try:
    import openpyxl  # noqa: F401
except ModuleNotFoundError:
    openpyxl_stub = ModuleType("openpyxl")
    openpyxl_stub.load_workbook = lambda *_args, **_kwargs: None
    sys.modules["openpyxl"] = openpyxl_stub

import web_app
from dataset_loader import Matrix, summary


NODES = (101, 205, 307, 409)
BASE_VALUES = (
    (0.0, 4.0, 6.0, 7.0),
    (4.0, 0.0, 3.0, 5.0),
    (6.0, 3.0, 0.0, 4.0),
    (7.0, 5.0, 4.0, 0.0),
)
FIXTURES = {
    (day, kind): Matrix(
        day,
        kind,
        NODES,
        tuple(tuple(value + (0 if i == j else scenario_index * 2) for j, value in enumerate(row)) for i, row in enumerate(BASE_VALUES)),
        "distance_km" if kind == "distance" and day >= 4 else "FixtureSheet",
        f"fixture_day_{day}_{kind}.xlsx",
    )
    for day in range(1, 10)
    for scenario_index, kind in enumerate(("distance", "mostlikely", "optimistic", "pessimistic"))
}


def fixture_load(day, kind):
    if (int(day), kind) not in FIXTURES:
        raise FileNotFoundError("The requested fixture matrix is missing.")
    return FIXTURES[(int(day), kind)]


def fixture_summaries():
    records = []
    for day in range(1, 10):
        matrices = {kind: summary(fixture_load(day, kind)) for kind in web_app.PREFIX}
        records.append({"day": day, "nodes": len(NODES), "matrices": matrices})
    return tuple(records)


def fixture_inventory():
    return {
        "days": 9,
        "matrix_files": 36,
        "matrix_counts": {"distance": 9, "mostlikely": 9, "optimistic": 9, "pessimistic": 9},
        "nodes_min": 4,
        "nodes_max": 4,
        "day_numbers": list(range(1, 10)),
    }


class TestLocalWebRequests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.originals = {
            "days": web_app.days,
            "load": web_app.load,
            "summary": web_app.summary,
            "dataset_inventory": web_app.dataset_inventory,
            "daily_matrix_summaries": web_app.daily_matrix_summaries,
            "order_characteristics_file": web_app.order_characteristics_file,
        }
        web_app.days = lambda: list(range(1, 10))
        web_app.load = fixture_load
        web_app.summary = summary
        web_app.dataset_inventory = fixture_inventory
        web_app.daily_matrix_summaries = fixture_summaries
        web_app.order_characteristics_file = lambda: None
        cls.server = web_app.ThreadingHTTPServer(("127.0.0.1", 0), web_app.Handler)
        cls.thread = Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=2)
        for key, value in cls.originals.items():
            setattr(web_app, key, value)

    def request(self, method, path, values=None):
        connection = HTTPConnection("127.0.0.1", self.server.server_port, timeout=5)
        body = urlencode(values or {}, doseq=True) if method == "POST" else None
        headers = {"Content-Type": "application/x-www-form-urlencoded"} if body is not None else {}
        connection.request(method, path, body, headers)
        response = connection.getresponse()
        status, content = response.status, response.read()
        content_type = response.getheader("Content-Type", "")
        disposition = response.getheader("Content-Disposition", "")
        connection.close()
        return status, content.decode("utf-8"), content_type, disposition

    def test_all_five_application_pages_are_served(self):
        pages = {
            "/": "Food Delivery Route Optimizer",
            "/dataset": "Inspect the source matrices",
            "/planner": "Build a delivery route",
            "/results": "Optimization outcome",
            "/analytics": "Measured data across all days",
        }
        for path, marker in pages.items():
            with self.subTest(path=path):
                status, content, _, _ = self.request("GET", path)
                self.assertEqual(status, 200)
                self.assertIn(marker, content)
                self.assertNotIn("{{", content)

    def test_dataset_explorer_shows_fixture_values_and_download_link(self):
        status, content, _, _ = self.request("GET", "/dataset?day=1&matrix=distance")
        self.assertEqual(status, 200)
        self.assertIn("Validated source workbook", content)
        self.assertIn("<td data-value=\"4\">4</td>", content)
        self.assertIn("/download/matrix?day=1&amp;matrix=distance", content)
        self.assertIn('id="matrix-search"', content)

    def test_planner_uses_source_identifiers_and_submits_node_indexes(self):
        status, content, _, _ = self.request("GET", "/planner?day=2&matrix=mostlikely")
        self.assertEqual(status, 200)
        for index in range(1, len(NODES) + 1):
            self.assertIn(f"Location {index}", content)
        self.assertIn('name="stops" value="1"', content)
        self.assertIn('name="depot"', content)
        self.assertIn('name="depot_name"', content)
        self.assertIn('name="place_name_1"', content)
        self.assertIn('value="Bengaluru"', content)
        self.assertNotIn("Node 101", content)
        self.assertIn("Held-Karp", content)

    def test_post_returns_optimal_tour_legs_and_verification(self):
        values = {
            "day": "1", "matrix": "distance", "depot": "0", "depot_name": "Bengaluru",
            "stops": ["1", "2", "3"], "place_name_1": "Mysuru", "place_name_2": "Mangaluru",
            "place_name_3": "Hubballi",
        }
        status, content, _, _ = self.request("POST", "/results", values)
        self.assertEqual(status, 200)
        self.assertIn("Mathematically optimal", content)
        self.assertIn("18<span>workbook units</span>", content)
        self.assertIn("Bengaluru", content)
        self.assertIn("Mysuru", content)
        self.assertIn("Every selected stop is visited exactly once", content)
        self.assertIn("Download route CSV", content)
        self.assertIn("Compare scenario costs", content)
        self.assertEqual(content.count('class="best-row"'), 1)

    def test_place_names_cover_the_depot_and_each_selected_stop(self):
        values = {
            "day": "1",
            "matrix": "distance",
            "depot": "0",
            "depot_name": "Main Kitchen",
            "stops": ["1", "2"],
            "place_name_1": "City Market",
            "place_name_2": "College",
        }
        status, content, _, _ = self.request("POST", "/results", values)
        self.assertEqual(status, 200)
        for place in ("Main Kitchen", "City Market", "College"):
            self.assertIn(place, content)
        self.assertNotIn("Node ", content)
        self.assertIn("depot_name=Main+Kitchen", content)
        self.assertIn("place_name_1=City+Market", content)

        query = urlencode(
            {
                "day": "1",
                "matrix": "distance",
                "depot": "0",
                "depot_name": "Main Kitchen",
                "stop": ["1", "2"],
                "place_name_1": "City Market",
                "place_name_2": "College",
            },
            doseq=True,
        )
        status, csv_content, _, _ = self.request("GET", f"/download/route?{query}")
        self.assertEqual(status, 200)
        self.assertIn("Main Kitchen", csv_content)
        self.assertIn("City Market", csv_content)
        self.assertIn("College", csv_content)
        self.assertNotIn("Node ", csv_content)

    def test_place_names_are_escaped_in_results(self):
        values = {
            "day": "1",
            "matrix": "distance",
            "depot": "0",
            "depot_name": "<script>alert(1)</script>",
            "stops": ["1"],
            "place_name_1": "Market",
        }
        status, content, _, _ = self.request("POST", "/results", values)
        self.assertEqual(status, 200)
        self.assertNotIn("<script>alert(1)</script>", content)
        self.assertIn("&lt;script&gt;", content)

    def test_backend_rejects_empty_stops_and_depot_duplication(self):
        empty = {"day": "1", "matrix": "distance", "depot": "0", "stops": []}
        status, content, _, _ = self.request("POST", "/results", empty)
        self.assertEqual(status, 200)
        self.assertIn("Select at least one delivery location", content)
        duplicate = {"day": "1", "matrix": "distance", "depot": "0", "stops": ["0"]}
        status, content, _, _ = self.request("POST", "/results", duplicate)
        self.assertEqual(status, 200)
        self.assertIn("The depot cannot also be a delivery stop", content)
        missing_names = {"day": "1", "matrix": "distance", "depot": "0", "stops": ["1"]}
        status, content, _, _ = self.request("POST", "/results", missing_names)
        self.assertEqual(status, 200)
        self.assertIn("Enter the actual Karnataka place name", content)
        invalid_scenario = {"day": "1", "matrix": "made-up", "depot": "0", "stops": ["1"]}
        status, content, _, _ = self.request("POST", "/results", invalid_scenario)
        self.assertEqual(status, 200)
        self.assertIn("Choose one of the available optimization scenarios", content)
        invalid_day = {"day": "99", "matrix": "distance", "depot": "0", "stops": ["1"]}
        status, content, _, _ = self.request("POST", "/results", invalid_day)
        self.assertEqual(status, 200)
        self.assertIn("Dataset Day 99 is not available", content)

    def test_missing_matrix_file_has_a_clear_explorer_message(self):
        original_load = web_app.load

        def missing(day, kind):
            if int(day) == 9 and kind == "pessimistic":
                raise FileNotFoundError("The pessimistic workbook for Day 9 is missing.")
            return original_load(day, kind)

        web_app.load = missing
        try:
            status, content, _, _ = self.request("GET", "/dataset?day=9&matrix=pessimistic")
        finally:
            web_app.load = original_load
        self.assertEqual(status, 200)
        self.assertIn("Dataset unavailable", content)
        self.assertIn("pessimistic workbook for Day 9 is missing", content)

    def test_analytics_compares_measured_summaries_and_same_tour_costs(self):
        path = "/analytics?day=1&matrix=distance&depot=0&depot_name=Bengaluru&stop=1&place_name_1=Mysuru&stop=2&place_name_2=Mangaluru&stop=3&place_name_3=Hubballi"
        status, content, _, _ = self.request("GET", path)
        self.assertEqual(status, 200)
        self.assertIn("Distance averages by day", content)
        self.assertIn("Same tour across scenarios", content)
        self.assertIn("Same tour, evaluated against this measured matrix", content)
        self.assertIn("No order-characteristics workbook", content)

    def test_matrix_and_route_csv_exports(self):
        status, content, content_type, disposition = self.request("GET", "/download/matrix?day=1&matrix=distance")
        self.assertEqual(status, 200)
        self.assertIn("text/csv", content_type)
        self.assertIn("From / To,101,205,307,409", content)
        self.assertIn('attachment; filename="day_1_distance.csv"', disposition)
        status, content, content_type, _ = self.request("GET", "/download/route?day=1&matrix=distance&depot=0&depot_name=Bengaluru&stop=1&place_name_1=Mysuru&stop=2&place_name_2=Mangaluru&stop=3&place_name_3=Hubballi")
        self.assertEqual(status, 200)
        self.assertIn("text/csv", content_type)
        self.assertIn("Food Delivery Route Optimizer result", content)
        self.assertIn("TOTAL", content)
        status, content, _, disposition = self.request("GET", "/download/analytics?day=1")
        self.assertEqual(status, 200)
        self.assertIn("Day,Nodes,Matrix", content)
        self.assertIn('attachment; filename="matrix_analytics_day_1.csv"', disposition)

    def test_html_escapes_untrusted_node_identifiers(self):
        matrix = Matrix(1, "distance", ("Depot", "<script>alert(1)</script>"), ((0.0, 2.0), (2.0, 0.0)))
        rendered = web_app._planner_nodes(matrix, "Depot", set())
        self.assertNotIn("<script>alert(1)</script>", rendered)
        self.assertIn("&lt;script&gt;", rendered)


if __name__ == "__main__":
    unittest.main()
