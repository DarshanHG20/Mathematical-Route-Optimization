"""Five-page, local-only Food Delivery TSP application."""

from csv import writer
from html import escape
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from io import StringIO
import json
from math import fsum
from pathlib import Path
import re
import time
from urllib.parse import parse_qs, urlencode, urlsplit

from analytics import daily_matrix_summaries, dataset_inventory, order_characteristics_file
from dataset_loader import PREFIX, SCENARIO_LABELS, DatasetError, days, load, summary
from solver import solve, verify


BASE = Path(__file__).resolve().parent
TYPES = SCENARIO_LABELS
MAX_REQUEST_BYTES = 100_000
MAX_PLANNER_STOPS = 60
MAX_PLACE_NAME_LENGTH = 80
KARNATAKA_PLACE_SUGGESTIONS = (
    "Bengaluru", "Mysuru", "Mangaluru", "Hubballi", "Belagavi", "Kalaburagi",
    "Shivamogga", "Tumakuru", "Davanagere", "Ballari", "Vijayapura", "Udupi",
    "Hassan", "Mandya", "Kolar", "Chitradurga", "Raichur", "Bidar",
    "Chikkamagaluru", "Madikeri", "Chamarajanagar", "Karwar", "Gadag",
    "Bagalkote", "Ramanagara", "Chikkaballapura", "Yadgir", "Koppal", "Hampi",
)
NAV_LINKS = (
    ("home", "/", "Overview"),
    ("data", "/dataset", "Dataset Explorer"),
    ("plan", "/planner", "Route Planner"),
    ("results", "/results", "Results"),
    ("analytics", "/analytics", "Analytics & Reports"),
)


def template(name, **data):
    source = (BASE / "templates" / name).read_text(encoding="utf-8")
    values = {key.upper(): str(value) for key, value in data.items()}
    return re.sub(r"{{([A-Z_]+)}}", lambda match: values.get(match.group(1), ""), source)


def navigation(active):
    links = []
    for key, url, label in NAV_LINKS:
        cls = ' class="active" aria-current="page"' if key == active else ""
        links.append(f'<a{cls} href="{url}">{escape(label)}</a>')
    return "".join(links)


def option_list(entries, current):
    return "".join(
        f'<option value="{escape(str(value), quote=True)}"'
        f'{" selected" if str(value) == str(current) else ""}>'
        f"{escape(str(label))}</option>"
        for value, label in entries
    )


def metric_cards(items):
    return "".join(
        f'<article class="metric"><span>{escape(str(label))}</span>'
        f"<strong>{escape(str(value))}</strong></article>"
        for label, value in items
    )


def formatted(value, digits=2):
    if value is None:
        return "—"
    rounded = round(float(value), digits)
    return str(int(rounded)) if rounded.is_integer() else f"{rounded:.{digits}f}".rstrip("0").rstrip(".")


def unit_label(kind, matrix=None):
    if kind != "distance":
        return "workbook units"
    if matrix is None or matrix.sheet_name == "distance_km":
        return "km"
    return "workbook units"


def _valid_day(value, fallback=None):
    choices = days()
    try:
        day = int(value)
    except (TypeError, ValueError):
        day = fallback
    if day not in choices:
        day = fallback if fallback in choices else (choices[0] if choices else None)
    return day


def _require_day(value):
    try:
        day = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("Choose an available dataset day.") from exc
    if day not in days():
        raise ValueError(f"Dataset Day {day} is not available.")
    return day


def _valid_kind(value):
    return value if value in TYPES else "distance"


def _require_kind(value):
    if value not in TYPES:
        raise ValueError("Choose one of the available optimization scenarios.")
    return value


def _first(form, key, default=""):
    value = form.get(key, default)
    return value[0] if isinstance(value, list) and value else (default if value is None else value)


def _selected_stops(form):
    if "stops" in form:
        values = form.get("stops", [])
        return values if isinstance(values, list) else [values]
    if "stop" in form:
        values = form.get("stop", [])
        return values if isinstance(values, list) else [values]
    combined = _first(form, "stops_csv", "")
    return combined.split(",") if combined else []


def _chart_data(records, kind):
    values = []
    for row in records:
        stats = row["matrices"].get(kind)
        value = stats.get("avg") if isinstance(stats, dict) and "avg" in stats else None
        values.append({"label": f"Day {row['day']}", "value": value})
    return json.dumps(values, ensure_ascii=False)


def page_overview():
    inventory = dataset_inventory()
    node_range = "—"
    if inventory["nodes_min"] is not None:
        node_range = str(inventory["nodes_min"])
        if inventory["nodes_max"] != inventory["nodes_min"]:
            node_range += f"–{inventory['nodes_max']}"
    time_count = sum(inventory["matrix_counts"][kind] for kind in ("mostlikely", "optimistic", "pessimistic"))
    return template(
        "index.html",
        nav=navigation("home"),
        title="Food Delivery Route Optimizer",
        subtitle="Intelligent Delivery Route Optimization Using the Travelling Salesperson Problem.",
        metrics=metric_cards(
            [
                ("Dataset versions", inventory["days"]),
                ("Excel matrices", inventory["matrix_files"]),
                ("Distance / time matrices", f"{inventory['matrix_counts']['distance']} / {time_count}"),
                ("Delivery nodes by day", node_range),
            ]
        ),
        day_count=inventory["days"],
        matrix_count=inventory["matrix_files"],
    )


def _matrix_table(matrix):
    headings = "".join(f"<th scope=\"col\">{escape(str(node))}</th>" for node in matrix.nodes)
    rows = []
    for index, node in enumerate(matrix.nodes):
        cells = "".join(
            f'<td data-value="{escape(formatted(value), quote=True)}">{escape(formatted(value))}</td>'
            if value is not None
            else '<td class="invalid-cell" data-value="missing">Missing</td>'
            for value in matrix.values[index]
        )
        rows.append(f'<tr data-node="{escape(str(node), quote=True)}"><th scope="row">{escape(str(node))}</th>{cells}</tr>')
    return (
        '<div class="table-scroll"><table id="matrix-table" class="matrix-table">'
        f"<thead><tr><th scope=\"col\">From / To</th>{headings}</tr></thead>"
        f"<tbody>{''.join(rows)}</tbody></table></div>"
    )


def page_dataset(query):
    day = _valid_day(_first(query, "day", None))
    kind = _valid_kind(_first(query, "matrix", "distance"))
    day_options = option_list([(number, f"Day {number}") for number in days()], day)
    type_options = option_list([(key, label) for key, label in TYPES.items()], kind)
    stats_html = ""
    table_html = '<p class="empty-state">Choose a day and matrix to inspect its source values.</p>'
    heat = "[]"
    message = ""
    download = "#"
    if day is not None:
        download = "/download/matrix?" + urlencode({"day": day, "matrix": kind})
        try:
            matrix = load(day, kind)
            stats = summary(matrix)
            stats_html = metric_cards(
                [
                    ("Delivery nodes", stats["nodes"]),
                    ("Dimensions", f"{stats['dimensions'][0]} × {stats['dimensions'][1]}"),
                    ("Minimum off-diagonal", formatted(stats["min"])),
                    ("Maximum off-diagonal", formatted(stats["max"])),
                    ("Average off-diagonal", formatted(stats["avg"])),
                    ("Directionality", "Symmetric" if stats["symmetric"] else "Asymmetric"),
                ]
            )
            table_html = _matrix_table(matrix)
            message = (
                f"Validated source workbook: {Path(matrix.source_file).name}, sheet “{matrix.sheet_name}”. "
                "All values below are read from that workbook."
            )
            off_diagonal = [
                matrix.values[i][j]
                for i in range(min(30, len(matrix.nodes)))
                for j in range(min(30, len(matrix.nodes)))
                if i != j
            ]
            minimum = min(off_diagonal) if off_diagonal else 0
            maximum = max(off_diagonal) if off_diagonal else 0
            denominator = maximum - minimum or 1
            heat_values = [
                [
                    None
                    if matrix.values[i][j] is None
                    else round((matrix.values[i][j] - minimum) / denominator, 4)
                    for j in range(min(30, len(matrix.nodes)))
                ]
                for i in range(min(30, len(matrix.nodes)))
            ]
            heat = json.dumps(heat_values)
        except (OSError, ValueError) as exc:
            message = f"Dataset unavailable: {exc}"
            table_html = '<p class="empty-state">This workbook could not be validated, so its values cannot be used.</p>'

    unit_note = "Time units are not stated in the workbook; values are shown as recorded." if kind != "distance" else "Distance units are shown as km when the sheet is named distance_km; generic sheet names are reported in workbook units."
    return template(
        "dataset.html",
        nav=navigation("data"),
        days=day_options,
        types=type_options,
        message=escape(message),
        unit_note=escape(unit_note),
        stats=stats_html,
        table=table_html,
        heat=escape(heat, quote=True),
        download=escape(download, quote=True),
    )


def _planner_nodes(matrix, depot, selected):
    nodes = []
    for index, node in enumerate(matrix.nodes):
        checked = " checked" if node in selected else ""
        depot_attr = " data-depot-node=\"true\"" if node == depot else ""
        location_label = f"Location {index + 1}"
        nodes.append(
            f'<div class="node-option" data-node-label="{escape(location_label.casefold(), quote=True)}" '
            f'data-node-id="{escape(str(node), quote=True)}"{depot_attr}>'
            f'<label class="node-pick"><input type="checkbox" name="stops" value="{index}"{checked}>'
            f'<span>{location_label}</span></label>'
            f'<input class="place-name-input" type="text" name="place_name_{index}" maxlength="{MAX_PLACE_NAME_LENGTH}" required '
            f'placeholder="Enter a Karnataka place" list="karnataka-places" '
            f'aria-label="Place name for {location_label.lower()}" hidden disabled></div>'
        )
    return "".join(nodes)


def page_planner(query, error=""):
    current_day = _valid_day(_first(query, "day", None))
    kind = _valid_kind(_first(query, "matrix", "distance"))
    day_options = option_list([(number, f"Day {number}") for number in days()], current_day)
    type_options = option_list([(key, label) for key, label in TYPES.items()], kind)
    place_suggestions = "".join(
        f'<option value="{escape(place, quote=True)}"></option>' for place in KARNATAKA_PLACE_SUGGESTIONS
    )
    depot_options = ""
    stop_options = ""
    note = "Select a dataset and scenario to load its delivery locations."
    disabled = " disabled"
    if current_day is not None:
        try:
            matrix = load(current_day, kind)
            depot_options = option_list([(index, f"Location {index + 1}") for index, _node in enumerate(matrix.nodes)], 0)
            stop_options = _planner_nodes(matrix, matrix.nodes[0], set())
            disabled = ""
            note = (
                f"{len(matrix.nodes)} matrix locations are available. Choose the real Karnataka place for the depot and each selected stop. "
                f"Select up to {MAX_PLANNER_STOPS} delivery stops. "
                "Enumeration is exact through 9 stops; Held-Karp is exact through 15; larger tours use a labelled heuristic."
            )
        except (OSError, ValueError) as exc:
            note = f"Dataset unavailable: {exc}"

    return template(
        "planner.html",
        nav=navigation("plan"),
        days=day_options,
        types=type_options,
        day=current_day if current_day is not None else "",
        matrix=kind,
        depot_options=depot_options,
        stop_options=stop_options,
        place_suggestions=place_suggestions,
        note=escape(note),
        error=escape(error),
        disabled=disabled,
        max_stops=MAX_PLANNER_STOPS,
    )


def _resolve_node(matrix, value):
    try:
        index = int(value)
    except (TypeError, ValueError):
        index = -1
    if 0 <= index < len(matrix.nodes):
        return matrix.nodes[index]
    matches = [node for node in matrix.nodes if str(node) == str(value)]
    if len(matches) == 1:
        return matches[0]
    raise ValueError(f"Selected node identifier is invalid or ambiguous: {value}")


def _clean_place_name(value):
    name = " ".join(str(value or "").split())
    if not name:
        raise ValueError("Enter the actual Karnataka place name for the depot and every selected stop.")
    if len(name) > MAX_PLACE_NAME_LENGTH:
        raise ValueError(f"Place names must be {MAX_PLACE_NAME_LENGTH} characters or fewer.")
    return name


def _place_name_map(form, matrix, depot, stops):
    names = {depot: _clean_place_name(_first(form, "depot_name", ""))}
    for node in stops:
        index = matrix.nodes.index(node)
        names[node] = _clean_place_name(_first(form, f"place_name_{index}", ""))
    normalized = [name.casefold() for name in names.values()]
    if len(set(normalized)) != len(normalized):
        raise ValueError("Give the depot and each selected stop a distinct place name.")
    return names


def _display_node(node, place_names):
    name = place_names.get(node)
    if not name:
        raise ValueError("Enter a place name for the depot and every selected stop.")
    return name


def _append_place_name_params(pairs, matrix, depot, stops, place_names):
    pairs.append(("depot_name", place_names.get(depot, "")))
    for node in stops:
        pairs.append((f"place_name_{matrix.nodes.index(node)}", place_names.get(node, "")))


def _tour_url(day, kind, matrix, depot, stops, place_names=None):
    pairs = [("day", day), ("matrix", kind), ("depot", matrix.nodes.index(depot))]
    pairs.extend(("stop", matrix.nodes.index(stop)) for stop in stops)
    _append_place_name_params(pairs, matrix, depot, stops, place_names or {})
    return "/download/route?" + urlencode(pairs)


def _analytics_url(day, kind, matrix, depot, stops, place_names=None):
    pairs = [("day", day), ("matrix", kind), ("depot", matrix.nodes.index(depot))]
    pairs.extend(("stop", matrix.nodes.index(stop)) for stop in stops)
    _append_place_name_params(pairs, matrix, depot, stops, place_names or {})
    return "/analytics?" + urlencode(pairs)


def _route_flow(route, place_names):
    parts = []
    for index, node in enumerate(route):
        if index:
            parts.append('<span class="route-arrow" aria-hidden="true">→</span>')
        parts.append(f'<span class="route-node">{escape(_display_node(node, place_names))}</span>')
    accessible_route = " → ".join(_display_node(node, place_names) for node in route)
    return (
        f'<div class="route-flow" aria-label="{escape("Route sequence: " + accessible_route, quote=True)}">'
        + "".join(parts)
        + "</div>"
    )


def _render_result(form):
    day = _require_day(_first(form, "day", None))
    kind = _require_kind(_first(form, "matrix", "distance"))
    depot_token = _first(form, "depot", "")
    stop_tokens = _selected_stops(form)
    if len(stop_tokens) > MAX_PLANNER_STOPS:
        raise ValueError(f"Select no more than {MAX_PLANNER_STOPS} delivery stops.")
    matrix = load(day, kind)
    depot = _resolve_node(matrix, depot_token)
    stops = [_resolve_node(matrix, token) for token in stop_tokens]
    started = time.perf_counter()
    result = solve(matrix, depot, stops)
    elapsed_ms = (time.perf_counter() - started) * 1000
    checks = verify(matrix, result, depot, stops)
    all_verified = all(checks.values())
    place_names = _place_name_map(form, matrix, depot, stops)

    leg_rows = "".join(
        f"<tr><td>{escape(_display_node(start, place_names))} <span class=\"table-arrow\">→</span> "
        f"{escape(_display_node(end, place_names))}</td>"
        f"<td>{formatted(cost)} {unit_label(kind, matrix)}</td></tr>"
        for start, end, cost in result.legs
    )
    tours = [(result.route, result.total)] + list(result.alternatives)
    tour_row_parts = []
    for rank, (route, total) in enumerate(tours, start=1):
        row_class = ' class="best-row"' if rank == 1 else ""
        route_label = " → ".join(escape(_display_node(node, place_names)) for node in route)
        tour_row_parts.append(
            f"<tr{row_class}><td>{rank}</td>"
            f"<td>{route_label}</td>"
            f"<td>{formatted(total)} {unit_label(kind, matrix)}</td></tr>"
        )
    tour_rows = "".join(tour_row_parts)
    if not result.alternatives:
        alternative_note = (
            "Only one distinct closed tour exists for this selection."
            if result.optimal and result.tours_compared == 1
            else "Alternative tours were not enumerated for this solve size."
        )
        tour_rows = (
            f"<tr class=\"best-row\"><td>1</td><td>{' → '.join(escape(_display_node(node, place_names)) for node in result.route)}</td>"
            f"<td>{formatted(result.total)} {unit_label(kind, matrix)}</td></tr>"
            f'<tr><td colspan="3" class="muted">{escape(alternative_note)}</td></tr>'
        )
    check_rows = "".join(
        f'<li class="{"pass" if passed else "fail"}"><span aria-hidden="true">{"✓" if passed else "!"}</span>'
        f"{escape(label)}</li>"
        for label, passed in checks.items()
    )
    status = "Verified" if all_verified else "Verification failed"
    quality = "Mathematically optimal" if result.optimal else "Heuristic; optimality is not guaranteed"
    notes = ""
    if result.tours_compared:
        notes = f"{result.tours_compared:,} distinct closed tours compared."
    comparison_url = _analytics_url(day, kind, matrix, depot, stops, place_names)
    download_url = _tour_url(day, kind, matrix, depot, stops, place_names)
    return template(
        "results.html",
        nav=navigation("results"),
        error="" if all_verified else "The independent verification did not pass; review the checks below.",
        day=day,
        scenario=escape(TYPES[kind]),
        depot=escape(_display_node(depot, place_names)),
        stops=len(stops),
        elapsed=formatted(elapsed_ms, 1),
        status=status,
        algorithm=escape(result.algorithm),
        quality=escape(quality),
        total=formatted(result.total),
        unit=unit_label(kind, matrix),
        route=_route_flow(result.route, place_names),
        legs=leg_rows,
        alternatives=tour_rows,
        checks=check_rows,
        notes=escape(notes),
        download=escape(download_url, quote=True),
        analytics=escape(comparison_url, quote=True),
    )


def page_results(form=None):
    if not form:
        return template(
            "results.html",
            nav=navigation("results"),
            error="",
            day="—",
            scenario="—",
            depot="—",
            stops="—",
            elapsed="—",
            status="Awaiting a route",
            algorithm="—",
            quality="Plan a route first",
            total="—",
            unit="",
            route='<p class="empty-state">Choose a dataset, depot and delivery locations in the Route Planner.</p>',
            legs="",
            alternatives='<tr><td colspan="3" class="muted">No route has been calculated yet.</td></tr>',
            checks='<li class="muted">Verification appears after a route is calculated.</li>',
            notes="",
            download="#",
            analytics="#",
        )
    try:
        return _render_result(form)
    except (OSError, ValueError, KeyError) as exc:
        return template(
            "results.html",
            nav=navigation("results"),
            error=escape(str(exc)),
            day=escape(_first(form, "day", "—")),
            scenario=escape(TYPES.get(_first(form, "matrix", "distance"), "—")),
            depot=escape(_first(form, "depot_name", "—")),
            stops=len(_selected_stops(form)),
            elapsed="—",
            status="Route not calculated",
            algorithm="—",
            quality="Correct the planner selection and try again.",
            total="—",
            unit="",
            route='<p class="empty-state">No route is available until the selection is valid.</p>',
            legs="",
            alternatives='<tr><td colspan="3" class="muted">No tours were calculated.</td></tr>',
            checks="",
            notes="",
            download="#",
            analytics="#",
        )


def _chart(data, title, unit):
    return (
        f'<section class="chart-card"><div class="chart-heading"><h3>{escape(title)}</h3>'
        f'<span>{escape(unit)}</span></div><div class="bar-chart" data-series="{escape(data, quote=True)}" '
        f'aria-label="{escape(title)} chart"></div></section>'
    )


def _route_comparison(query, selected_day):
    if "depot" not in query or not _selected_stops(query):
        return '<p class="empty-state">Calculate a route in the planner to compare that same tour across the distance and travel-time matrices.</p>'
    kind = _require_kind(_first(query, "matrix", "distance"))
    depot_token = _first(query, "depot", "")
    stop_tokens = _selected_stops(query)
    try:
        base_matrix = load(selected_day, kind)
        depot = _resolve_node(base_matrix, depot_token)
        stops = [_resolve_node(base_matrix, token) for token in stop_tokens]
        place_names = _place_name_map(query, base_matrix, depot, stops)
        base_result = solve(base_matrix, depot, stops)
        route = base_result.route
        rows = []
        for scenario, label in TYPES.items():
            try:
                matrix = load(selected_day, scenario)
                total = fsum(matrix.cost(a, b) for a, b in zip(route, route[1:]))
                rows.append(
                    f"<tr><td>{escape(label)}</td><td>{formatted(total)} {unit_label(scenario, matrix)}</td>"
                    f"<td>{'Same tour, evaluated against this measured matrix'}</td></tr>"
                )
            except (OSError, ValueError, KeyError):
                rows.append(f'<tr><td>{escape(label)}</td><td>Unavailable</td><td>Matrix or node is missing</td></tr>')
        tour = " → ".join(escape(_display_node(node, place_names)) for node in route)
        return (
            f'<p class="small">Selected tour: <strong>{tour}</strong>. The route is optimized for '
            f'{escape(TYPES[kind])}; other columns price that identical sequence using their own matrix.</p>'
            '<div class="table-scroll"><table><thead><tr><th>Scenario matrix</th><th>Tour cost</th><th>Interpretation</th></tr></thead>'
            f"<tbody>{''.join(rows)}</tbody></table></div>"
        )
    except (OSError, ValueError, KeyError) as exc:
        return f'<p class="empty-state">Route comparison unavailable: {escape(str(exc))}</p>'


def page_analytics(query):
    records = daily_matrix_summaries()
    selected_day = _valid_day(_first(query, "day", None))
    rows = []
    for record in records:
        distance = record["matrices"].get("distance")
        distance_avg = distance.get("avg") if isinstance(distance, dict) else None
        times = [record["matrices"].get(key) for key in ("mostlikely", "optimistic", "pessimistic")]
        values = [item.get("avg") if isinstance(item, dict) else None for item in times]
        rows.append(
            f"<tr><th scope=\"row\">Day {record['day']}</th><td>{record['nodes'] if record['nodes'] is not None else '—'}</td>"
            f"<td>{formatted(distance_avg)}</td><td>{formatted(values[0])}</td>"
            f"<td>{formatted(values[1])}</td><td>{formatted(values[2])}</td></tr>"
        )

    selected_rows = ""
    selected_stats = '<p class="empty-state">Select a dataset day to see its measured node and edge summaries.</p>'
    if selected_day is not None:
        record = next((row for row in records if row["day"] == selected_day), None)
        selected_rows = option_list([(number, f"Day {number}") for number in days()], selected_day)
        if record:
            summaries = []
            for kind, label in TYPES.items():
                details = record["matrices"].get(kind)
                if not isinstance(details, dict) or "avg" not in details:
                    summaries.append(f"<tr><td>{escape(label)}</td><td colspan=\"4\">Unavailable or invalid</td></tr>")
                else:
                    summaries.append(
                        f"<tr><td>{escape(label)}</td><td>{details['nodes']}</td>"
                        f"<td>{formatted(details['min'])}</td><td>{formatted(details['max'])}</td>"
                        f"<td>{formatted(details['avg'])}</td></tr>"
                    )
            selected_stats = (
                f'<div class="table-scroll"><table><thead><tr><th>Matrix</th><th>Nodes</th>'
                f"<th>Minimum</th><th>Maximum</th><th>Average</th></tr></thead><tbody>{''.join(summaries)}</tbody></table></div>"
            )

    order_file = order_characteristics_file()
    if order_file is None:
        order_note = "No order-characteristics workbook or CSV is present in the project dataset folders. Weight, volume and service-time statistics are unavailable."
    else:
        order_note = f"Order-characteristics file found: {order_file.name}. Its fields are not used in route costs."
    data_export = "/download/analytics" + (f"?day={selected_day}" if selected_day is not None else "")
    return template(
        "analytics.html",
        nav=navigation("analytics"),
        rows="".join(rows),
        day_options=selected_rows,
        selected_stats=selected_stats,
        order_note=escape(order_note),
        distance_chart=_chart(_chart_data(records, "distance"), "Distance averages by day", "workbook units; km where labelled"),
        likely_chart=_chart(_chart_data(records, "mostlikely"), "Most likely travel-time averages", "workbook units / directed edge"),
        scenario_chart=(
            _chart(_chart_data(records, "optimistic"), "Optimistic travel-time averages", "workbook units / directed edge")
            + _chart(_chart_data(records, "pessimistic"), "Pessimistic travel-time averages", "workbook units / directed edge")
        ),
        route_comparison=_route_comparison(query, selected_day) if selected_day is not None else "",
        day=selected_day if selected_day is not None else "",
        export=escape(data_export, quote=True),
    )


def csv_matrix(matrix):
    output = StringIO()
    rows = writer(output)
    rows.writerow(["From / To", *matrix.nodes])
    for node, values in zip(matrix.nodes, matrix.values):
        rows.writerow([node, *values])
    return output.getvalue()


def csv_route(day, kind, depot, stops, place_names=None):
    matrix = load(day, kind)
    result = solve(matrix, depot, stops)
    checks = verify(matrix, result, depot, stops)
    place_names = place_names or {}
    output = StringIO()
    rows = writer(output)
    rows.writerow(["Food Delivery Route Optimizer result"])
    rows.writerow(["Dataset day", day])
    rows.writerow(["Scenario", TYPES[kind]])
    rows.writerow(["Algorithm", result.algorithm])
    rows.writerow(["Optimality", "Optimal" if result.optimal else "Heuristic; not guaranteed optimal"])
    rows.writerow(["Route", " -> ".join(_display_node(node, place_names) for node in result.route)])
    rows.writerow(["Verification passed", all(checks.values())])
    rows.writerow([])
    rows.writerow(["From", "To", f"Cost ({unit_label(kind, matrix)})"])
    for start, end, cost in result.legs:
        rows.writerow([_display_node(start, place_names), _display_node(end, place_names), cost])
    rows.writerow(["TOTAL", "", result.total])
    return output.getvalue()


def csv_analytics(day=None):
    output = StringIO()
    rows = writer(output)
    rows.writerow(["Day", "Nodes", "Matrix", "Minimum off-diagonal", "Maximum off-diagonal", "Average off-diagonal", "Symmetric"])
    for record in daily_matrix_summaries():
        if day is not None and record["day"] != day:
            continue
        for kind, label in TYPES.items():
            details = record["matrices"].get(kind)
            if isinstance(details, dict) and "avg" in details:
                rows.writerow([record["day"], details["nodes"], label, details["min"], details["max"], details["avg"], details["symmetric"]])
            else:
                rows.writerow([record["day"], record["nodes"], label, "", "", "", "Unavailable or invalid"])
    return output.getvalue()


class Handler(BaseHTTPRequestHandler):
    server_version = "FoodDeliveryRouteOptimizer/2.0"

    def reply(self, status, body, content_type="text/html; charset=utf-8", filename=None):
        data = body.encode("utf-8") if isinstance(body, str) else body
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "same-origin")
        if filename:
            self.send_header("Content-Disposition", f'attachment; filename="{filename}"')
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        url = urlsplit(self.path)
        query = parse_qs(url.query, keep_blank_values=True)
        if url.path in ("/", "/index.html"):
            return self.reply(200, page_overview())
        if url.path == "/dataset":
            return self.reply(200, page_dataset(query))
        if url.path == "/planner":
            return self.reply(200, page_planner(query))
        if url.path == "/results":
            return self.reply(200, page_results(query if "stop" in query or "stops" in query else None))
        if url.path == "/analytics":
            return self.reply(200, page_analytics(query))
        if url.path == "/static/style.css":
            try:
                return self.reply(200, (BASE / "static" / "style.css").read_bytes(), "text/css; charset=utf-8")
            except OSError:
                return self.reply(404, "Stylesheet not found.", "text/plain; charset=utf-8")
        if url.path == "/static/script.js":
            try:
                return self.reply(200, (BASE / "static" / "script.js").read_bytes(), "text/javascript; charset=utf-8")
            except OSError:
                return self.reply(404, "Script not found.", "text/plain; charset=utf-8")
        if url.path == "/download/matrix":
            try:
                day = _require_day(_first(query, "day", None))
                kind = _require_kind(_first(query, "matrix", "distance"))
                return self.reply(200, csv_matrix(load(day, kind)), "text/csv; charset=utf-8", f"day_{day}_{kind}.csv")
            except (OSError, ValueError) as exc:
                return self.reply(404, str(exc), "text/plain; charset=utf-8")
        if url.path == "/download/route":
            try:
                day = _require_day(_first(query, "day", None))
                kind = _require_kind(_first(query, "matrix", "distance"))
                depot_token = _first(query, "depot", "")
                stop_tokens = _selected_stops(query)
                matrix = load(day, kind)
                depot = _resolve_node(matrix, depot_token)
                stops = [_resolve_node(matrix, token) for token in stop_tokens]
                place_names = _place_name_map(query, matrix, depot, stops)
                return self.reply(200, csv_route(day, kind, depot, stops, place_names), "text/csv; charset=utf-8", f"route_day_{day}.csv")
            except (OSError, ValueError, KeyError) as exc:
                return self.reply(400, str(exc), "text/plain; charset=utf-8")
        if url.path == "/download/analytics":
            try:
                day = _require_day(_first(query, "day", None)) if "day" in query else None
            except ValueError as exc:
                return self.reply(400, str(exc), "text/plain; charset=utf-8")
            filename = f"matrix_analytics_day_{day}.csv" if day is not None else "matrix_analytics.csv"
            return self.reply(200, csv_analytics(day), "text/csv; charset=utf-8", filename)
        if url.path == "/favicon.ico":
            return self.reply(204, b"", "image/x-icon")
        return self.reply(404, "Page not found.", "text/plain; charset=utf-8")

    def do_POST(self):
        if urlsplit(self.path).path != "/results":
            return self.reply(404, "Page not found.", "text/plain; charset=utf-8")
        try:
            content_length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            return self.reply(400, "Invalid request length.", "text/plain; charset=utf-8")
        if content_length <= 0 or content_length > MAX_REQUEST_BYTES:
            return self.reply(400, "Request is empty or too large.", "text/plain; charset=utf-8")
        body = self.rfile.read(content_length).decode("utf-8", errors="replace")
        form = parse_qs(body, keep_blank_values=True)
        return self.reply(200, page_results(form))

    def log_message(self, _format, *args):
        return


def main():
    host, port = "127.0.0.1", 8000
    server = ThreadingHTTPServer((host, port), Handler)
    print(f"Food Delivery Route Optimizer is running at http://{host}:{port}")
    print("Press Ctrl+C to stop.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nServer stopped.")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
