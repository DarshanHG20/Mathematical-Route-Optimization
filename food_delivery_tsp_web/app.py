"""Three-page, login-free Food Delivery TSP web app using Python's standard library.

Run: python app.py    Then open http://127.0.0.1:8000
"""
from html import escape
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from itertools import permutations
from math import factorial, fsum, isclose, isfinite
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

BASE_DIR = Path(__file__).resolve().parent
HOME_TEMPLATE = BASE_DIR / "templates" / "index.html"
INPUT_TEMPLATE = BASE_DIR / "templates" / "input.html"
RESULTS_TEMPLATE = BASE_DIR / "templates" / "results.html"
STYLESHEET = BASE_DIR / "static" / "style.css"

# Edit these four default names to change the sample places shown by the app.
LOCATION_NAMES = ["Restaurant", "City Market", "Bus Stand", "College"]
LOCATION_COUNT = len(LOCATION_NAMES)
PLACE_SUGGESTIONS = [
    "Restaurant", "City Market", "Bus Stand", "College", "Hospital",
    "Railway Station", "Shopping Centre", "School", "Office", "Park", "Airport",
]
SAMPLE_MATRIX_TEXT = """0,4,6,7
4,0,3,5
6,3,0,4
7,5,4,0"""
MAX_PLACE_NAME_LENGTH = 50
MAX_BODY_BYTES = 20_000


def validate_location_names(names):
    """Return four trimmed, unique names for the depot and delivery locations."""
    if len(names) != LOCATION_COUNT:
        raise ValueError(f"Enter exactly {LOCATION_COUNT} place names.")
    cleaned = [str(name).strip() for name in names]
    for index, name in enumerate(cleaned, start=1):
        if not name:
            raise ValueError(f"Enter a name for place {index}.")
        if len(name) > MAX_PLACE_NAME_LENGTH:
            raise ValueError(f"Place {index} must be {MAX_PLACE_NAME_LENGTH} characters or fewer.")
    if len({name.casefold() for name in cleaned}) != LOCATION_COUNT:
        raise ValueError("Place names must be unique.")
    return cleaned


def parse_distance_matrix(text):
    """Parse and validate comma-separated rows of a symmetric distance matrix."""
    rows = [line.strip() for line in text.splitlines() if line.strip()]
    if len(rows) != LOCATION_COUNT:
        raise ValueError(f"Enter exactly {LOCATION_COUNT} matrix rows, one for each place above.")
    matrix = []
    for row_number, row in enumerate(rows, start=1):
        cells = [cell.strip() for cell in row.split(",")]
        if len(cells) != len(rows):
            raise ValueError(f"Row {row_number} needs {len(rows)} comma-separated values.")
        parsed = []
        for col_number, cell in enumerate(cells, start=1):
            try:
                value = float(cell)
            except ValueError as exc:
                raise ValueError(f"Value at row {row_number}, column {col_number} is not a number.") from exc
            if not isfinite(value):
                raise ValueError("Distances must be finite numbers.")
            parsed.append(value)
        matrix.append(parsed)
    validate_distance_matrix(matrix)
    return matrix


def validate_distance_matrix(matrix):
    size = len(matrix)
    if size != LOCATION_COUNT:
        raise ValueError(f"The matrix must contain exactly {LOCATION_COUNT} places.")
    if any(len(row) != size for row in matrix):
        raise ValueError("The distance matrix must be square.")
    for i in range(size):
        for j in range(size):
            value = matrix[i][j]
            if not isfinite(value):
                raise ValueError("Distances must be finite numbers.")
            if value < 0:
                raise ValueError("Distances cannot be negative.")
            if i == j and not isclose(value, 0.0, abs_tol=1e-9):
                raise ValueError("The diagonal must be zero (distance to the same place).")
            if not isclose(value, matrix[j][i], rel_tol=1e-9, abs_tol=1e-9):
                raise ValueError("This solver expects a symmetric matrix: d(i,j) must equal d(j,i).")


def format_distance(value):
    rounded = round(value, 2)
    return str(int(round(rounded))) if isclose(rounded, round(rounded), abs_tol=1e-9) else f"{rounded:.2f}".rstrip("0").rstrip(".")


def solve_tsp(matrix):
    """Compare all tours, keeping one direction from each reverse pair."""
    validate_distance_matrix(matrix)
    delivery_places = tuple(range(1, len(matrix)))
    permutation_count = factorial(len(delivery_places))
    tours = []
    # For symmetric distances, first < last keeps one route from each reverse pair.
    for order in permutations(delivery_places):
        if order[0] >= order[-1]:
            continue
        route = (0,) + order + (0,)
        legs = [matrix[route[i]][route[i + 1]] for i in range(len(route) - 1)]
        tours.append({"route": route, "legs": legs, "total": fsum(legs)})
    if not tours:
        raise ValueError("No complete route could be generated.")
    minimum = min(tour["total"] for tour in tours)
    optimal = [tour for tour in tours if isclose(tour["total"], minimum, rel_tol=1e-9, abs_tol=1e-9)]
    best = optimal[0]
    verified_total = sum(matrix[best["route"][i]][best["route"][i + 1]] for i in range(len(best["route"]) - 1))
    checks = {
        "depot": best["route"][0] == 0 and best["route"][-1] == 0,
        "visits": sorted(best["route"][1:-1]) == list(delivery_places),
        "total": isclose(verified_total, minimum, rel_tol=1e-9, abs_tol=1e-9),
        "routes": len(tours) * 2 == permutation_count,
    }
    return {
        "best_route": best["route"], "best_total": minimum, "best_legs": best["legs"],
        "verified_total": verified_total, "permutation_count": permutation_count,
        "unique_tour_count": len(tours), "optimal_tour_count": len(optimal),
        "checks": checks, "tours": sorted(tours, key=lambda x: (x["total"], x["route"])),
    }


def _template(path):
    return path.read_text(encoding="utf-8")


def _place_order(names):
    return " &rarr; ".join(escape(name) for name in names)


def render_home_page():
    return _template(HOME_TEMPLATE).replace("{{PLACE_ORDER}}", _place_order(LOCATION_NAMES))


def render_input_page(matrix_text=SAMPLE_MATRIX_TEXT, place_names=None, error_message=""):
    names = list(place_names or LOCATION_NAMES)
    names = (names + LOCATION_NAMES[len(names):LOCATION_COUNT])[:LOCATION_COUNT]
    place_inputs = []
    for index, name in enumerate(names):
        kind = "depot" if index == 0 else "delivery place"
        place_inputs.append(
            f'<div class="place-field"><label for="place_{index}">Place {index + 1} ({kind})</label>'
            f'<input id="place_{index}" name="place_{index}" type="text" list="place-suggestions" '
            f'maxlength="{MAX_PLACE_NAME_LENGTH}" required '
            f'value="{escape(str(name), quote=True)}"></div>'
        )
    suggestions = "".join(f'<option value="{escape(name, quote=True)}"></option>' for name in PLACE_SUGGESTIONS)
    error = ""
    if error_message:
        error = '<div class="alert" role="alert"><strong>Check your places and matrix:</strong> ' + escape(error_message) + "</div>"
    template = _template(INPUT_TEMPLATE)
    return (template.replace("{{PLACE_INPUTS}}", "\n".join(place_inputs))
            .replace("{{PLACE_SUGGESTIONS}}", suggestions)
            .replace("{{PLACE_ORDER}}", _place_order(names))
            .replace("{{MATRIX_VALUE}}", escape(matrix_text))
            .replace("{{ERROR_BLOCK}}", error))


def render_results(result, matrix, names):
    names = validate_location_names(names)
    labels = names
    route = " &rarr; ".join(escape(labels[i]) for i in result["best_route"])
    html = f"""
    <section class="panel results" id="results" aria-live="polite">
      <div class="section-heading"><div><p class="eyebrow">OPTIMAL TOUR</p><h2>Shortest route found</h2></div><span class="status-pill">Verified</span></div>
      <div class="answer-card"><div class="answer-distance">{format_distance(result['best_total'])}<span> km</span></div><div class="answer-route">{route}</div></div>
      <div class="stats-grid"><div class="stat"><span>Delivery orders checked</span><strong>{result['permutation_count']}</strong></div><div class="stat"><span>Distinct tours compared</span><strong>{result['unique_tour_count']}</strong></div><div class="stat"><span>Optimal tour(s)</span><strong>{result['optimal_tour_count']}</strong></div></div>
      <h3>Best route, leg by leg</h3><div class="table-wrap"><table><thead><tr><th>Leg</th><th>Distance lookup</th><th>Distance</th></tr></thead><tbody>
    """
    for i, distance in enumerate(result["best_legs"]):
        start, end = escape(labels[result["best_route"][i]]), escape(labels[result["best_route"][i + 1]])
        html += f"<tr><td>{start} &rarr; {end}</td><td>d({start}, {end})</td><td>{format_distance(distance)} km</td></tr>"
    html += f"<tr class=\"total-row\"><td colspan=\"2\">Total route distance</td><td>{format_distance(result['best_total'])} km</td></tr></tbody></table></div>"
    html += "<h3>Manual comparison of distinct tours</h3><p class=\"muted\">Each row adds consecutive legs, including the return to the depot. Reverse directions have the same distance for a symmetric matrix, so each pair is listed once.</p>"
    html += "<div class=\"table-wrap\"><table><thead><tr><th>#</th><th>Tour</th><th>Leg-by-leg sum (km)</th><th>Total (km)</th></tr></thead><tbody>"
    for number, tour in enumerate(result["tours"], start=1):
        path = " &rarr; ".join(escape(labels[i]) for i in tour["route"])
        addition = " + ".join(format_distance(value) for value in tour["legs"])
        row_class = " class=\"optimal-row\"" if isclose(tour["total"], result["best_total"], rel_tol=1e-9, abs_tol=1e-9) else ""
        html += f"<tr{row_class}><td>{number}</td><td>{path}</td><td>{addition}</td><td><strong>{format_distance(tour['total'])}</strong></td></tr>"
    html += "</tbody></table></div><h3>Verification checks</h3><div class=\"check-grid\">"
    descriptions = {
        "depot": "Route starts and ends at the depot",
        "visits": "Every delivery place is visited exactly once",
        "total": "Winning total independently recalculated",
        "routes": "All distinct tours compared; reverse duplicates removed",
    }
    for key, description in descriptions.items():
        passed = result["checks"][key]
        badge, class_name = ("PASS", "pass") if passed else ("FAIL", "fail")
        html += f"<div class=\"check-item\"><span class=\"check-badge {class_name}\">{badge}</span><span>{escape(description)}</span></div>"
    return html + "</div></section>"


def render_results_page(matrix, place_names, illustrative=False):
    names = validate_location_names(place_names)
    result = solve_tsp(matrix)
    if illustrative:
        note = "Illustrative sample distances only; not actual map measurements or Swiggy/Zomato data."
    else:
        note = "The calculation uses the place names and distances submitted on the previous page; no map service is queried."
    template = _template(RESULTS_TEMPLATE)
    return (template.replace("{{RESULT_BLOCK}}", render_results(result, matrix, names))
            .replace("{{DATA_NOTE}}", escape(note)))


class RouteHandler(BaseHTTPRequestHandler):
    server_version = "FoodDeliveryTSP/1.1"

    def send_content(self, status, body, content_type="text/html; charset=utf-8"):
        data = body.encode("utf-8") if isinstance(body, str) else body
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        path = urlsplit(self.path).path
        if path in ("/", "/index.html"):
            return self.send_content(200, render_home_page())
        if path == "/input":
            return self.send_content(200, render_input_page())
        if path == "/results":
            matrix = parse_distance_matrix(SAMPLE_MATRIX_TEXT)
            return self.send_content(200, render_results_page(matrix, LOCATION_NAMES, illustrative=True))
        if path == "/static/style.css":
            try:
                return self.send_content(200, STYLESHEET.read_bytes(), "text/css; charset=utf-8")
            except OSError:
                return self.send_content(500, "Stylesheet could not be loaded.", "text/plain; charset=utf-8")
        if path == "/favicon.ico":
            return self.send_content(204, b"", "image/x-icon")
        return self.send_content(404, "Page not found.", "text/plain; charset=utf-8")

    def do_POST(self):
        if urlsplit(self.path).path != "/results":
            return self.send_content(404, "Page not found.", "text/plain; charset=utf-8")
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            return self.send_content(400, "Invalid request length.", "text/plain; charset=utf-8")
        if length <= 0 or length > MAX_BODY_BYTES:
            return self.send_content(400, "Request is empty or too large.", "text/plain; charset=utf-8")
        form = parse_qs(self.rfile.read(length).decode("utf-8", errors="replace"), keep_blank_values=True)
        names = [form.get(f"place_{index}", [""])[0] for index in range(LOCATION_COUNT)]
        matrix_text = form.get("matrix", [""])[0]
        try:
            names = validate_location_names(names)
            matrix = parse_distance_matrix(matrix_text)
            page = render_results_page(matrix, names)
        except ValueError as exc:
            page = render_input_page(matrix_text, names, error_message=str(exc))
        return self.send_content(200, page)

    def log_message(self, fmt, *args):
        return  # quiet local classroom server


def main():
    host, port = "127.0.0.1", 8000
    server = ThreadingHTTPServer((host, port), RouteHandler)
    print(f"Food Delivery TSP is running at http://{host}:{port}")
    print("Press Ctrl+C to stop.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nServer stopped.")
    finally:
        server.server_close()


if __name__ == "__main__":
    # Keep the original classroom helpers importable; launch the integrated app.
    from web_app import main as upgraded_main
    upgraded_main()
