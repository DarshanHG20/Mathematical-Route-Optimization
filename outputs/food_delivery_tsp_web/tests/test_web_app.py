from http.client import HTTPConnection
from pathlib import Path
import sys
from threading import Thread
import unittest
from urllib.parse import urlencode

PROJECT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_DIR))
from app import (
    LOCATION_NAMES,
    PLACE_SUGGESTIONS,
    SAMPLE_MATRIX_TEXT,
    STYLESHEET,
    RouteHandler,
    parse_distance_matrix,
    render_home_page,
    render_input_page,
    render_results_page,
)


class TestThreePageRendering(unittest.TestCase):
    def test_home_page_links_the_three_pages_without_login(self):
        page = render_home_page()
        self.assertIn("Plan a delivery loop in three steps", page)
        self.assertIn('href="/"', page)
        self.assertIn('href="/input"', page)
        self.assertIn('href="/results"', page)
        self.assertIn("Page 1 of 3", page)
        self.assertNotIn('name="password"', page)
        for name in LOCATION_NAMES:
            self.assertIn(name, page)

    def test_input_page_has_four_place_fields_and_local_suggestions(self):
        page = render_input_page()
        for index in range(4):
            self.assertIn(f'name="place_{index}"', page)
        self.assertIn('<datalist id="place-suggestions">', page)
        for suggestion in PLACE_SUGGESTIONS:
            self.assertIn(f'value="{suggestion}"', page)
        self.assertIn("Restaurant &rarr; City Market &rarr; Bus Stand &rarr; College", page)
        self.assertIn('action="/results"', page)
        self.assertIn("Page 2 of 3", page)

    def test_user_place_names_are_reflected_in_matrix_order_and_route(self):
        names = ["Depot West", "Central Market", "North Bus Stop", "Green College"]
        page = render_input_page(place_names=names)
        self.assertIn("Depot West &rarr; Central Market &rarr; North Bus Stop &rarr; Green College", page)
        matrix = parse_distance_matrix(SAMPLE_MATRIX_TEXT)
        result = render_results_page(matrix, names)
        self.assertIn("Depot West &rarr; Central Market &rarr; North Bus Stop &rarr; Green College &rarr; Depot West", result)

    def test_default_sample_result_shows_all_tours_and_totals(self):
        result = render_results_page(parse_distance_matrix(SAMPLE_MATRIX_TEXT), LOCATION_NAMES, illustrative=True)
        self.assertIn("Page 3 of 3", result)
        self.assertIn("not actual map measurements or Swiggy/Zomato data", result)
        expected_rows = [
            ("Restaurant &rarr; City Market &rarr; Bus Stand &rarr; College &rarr; Restaurant", "4 + 3 + 4 + 7", "18"),
            ("Restaurant &rarr; City Market &rarr; College &rarr; Bus Stand &rarr; Restaurant", "4 + 5 + 4 + 6", "19"),
            ("Restaurant &rarr; Bus Stand &rarr; City Market &rarr; College &rarr; Restaurant", "6 + 3 + 5 + 7", "21"),
        ]
        for route, addition, total in expected_rows:
            self.assertIn(route, result)
            self.assertIn(addition, result)
            self.assertIn(f"><strong>{total}</strong></td>", result)

    def test_input_escapes_place_names_and_validation_errors(self):
        page = render_input_page(place_names=["<script>", "Market", "Bus", "College"], error_message="Place names must be unique.")
        self.assertNotIn('value="<script>"', page)
        self.assertIn("&lt;script&gt;", page)
        self.assertIn('class="alert"', page)

    def test_stylesheet_is_present_and_responsive(self):
        css = STYLESHEET.read_text(encoding="utf-8-sig")
        self.assertIn(".site-nav", css)
        self.assertIn(".place-grid", css)
        self.assertIn("@media", css)


class TestLocalWebRequests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from http.server import ThreadingHTTPServer
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), RouteHandler)
        cls.thread = Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=2)

    def request(self, method, path, values=None):
        connection = HTTPConnection("127.0.0.1", self.server.server_port, timeout=3)
        body = urlencode(values or {}) if method == "POST" else None
        headers = {"Content-Type": "application/x-www-form-urlencoded"} if body is not None else {}
        connection.request(method, path, body, headers)
        response = connection.getresponse()
        status, content = response.status, response.read().decode("utf-8")
        connection.close()
        return status, content

    def test_get_serves_all_three_pages(self):
        expected_titles = {
            "/": "Page 1 of 3",
            "/input": "Page 2 of 3",
            "/results": "Page 3 of 3",
        }
        for path, marker in expected_titles.items():
            with self.subTest(path=path):
                status, content = self.request("GET", path)
                self.assertEqual(status, 200)
                self.assertIn(marker, content)

    def test_post_accepts_custom_names_and_valid_matrix(self):
        values = {f"place_{i}": name for i, name in enumerate(["Depot West", "Central Market", "North Bus Stop", "Green College"])}
        values["matrix"] = SAMPLE_MATRIX_TEXT
        status, content = self.request("POST", "/results", values)
        self.assertEqual(status, 200)
        self.assertIn("Depot West &rarr; Central Market &rarr; North Bus Stop &rarr; Green College &rarr; Depot West", content)
        self.assertIn("18<span> km</span>", content)

    def test_post_rejects_invalid_matrix_and_keeps_place_names(self):
        values = {f"place_{i}": name for i, name in enumerate(["My Depot", "Market", "Bus Stand", "College"])}
        values["matrix"] = "0,1\n1,0"
        status, content = self.request("POST", "/results", values)
        self.assertEqual(status, 200)
        self.assertIn('class="alert"', content)
        self.assertIn("exactly 4 matrix rows", content)
        self.assertIn('value="My Depot"', content)

    def test_post_rejects_duplicate_place_names(self):
        values = {f"place_{i}": name for i, name in enumerate(["Depot", "Market", "Market", "College"])}
        values["matrix"] = SAMPLE_MATRIX_TEXT
        status, content = self.request("POST", "/results", values)
        self.assertEqual(status, 200)
        self.assertIn("Place names must be unique", content)


if __name__ == "__main__":
    unittest.main()
