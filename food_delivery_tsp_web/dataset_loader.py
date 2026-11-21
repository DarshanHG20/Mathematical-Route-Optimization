"""Load and validate the labelled research matrices from Excel workbooks."""

from dataclasses import dataclass, field
from functools import lru_cache
from math import fsum, isclose, isfinite
from pathlib import Path
import re

from openpyxl import load_workbook


ROOT = Path(__file__).resolve().parent / "time_and_distance_matrices"
PREFIX = {
    "distance": "distance_matrix",
    "mostlikely": "time_matrix_mostlikely",
    "optimistic": "time_matrix_optimistic",
    "pessimistic": "time_matrix_pessimistic",
}
SCENARIO_LABELS = {
    "distance": "Distance optimization",
    "mostlikely": "Most likely travel time",
    "optimistic": "Optimistic travel time",
    "pessimistic": "Pessimistic travel time",
}
_DAY_FOLDER = re.compile(r"^day_(\d+)$")


class DatasetError(ValueError):
    """A workbook is missing, ambiguous, or fails matrix validation."""


@dataclass(frozen=True)
class Matrix:
    day: int
    kind: str
    nodes: tuple
    values: tuple
    sheet_name: str = ""
    source_file: str = ""
    _positions: dict = field(init=False, repr=False, compare=False)

    def __post_init__(self):
        object.__setattr__(self, "_positions", {node: i for i, node in enumerate(self.nodes)})

    def cost(self, start, end):
        try:
            return self.values[self._positions[start]][self._positions[end]]
        except KeyError as exc:
            raise ValueError(f"Unknown node identifier: {exc.args[0]}") from exc

    @property
    def symmetric(self):
        return all(
            isclose(self.values[i][j], self.values[j][i], rel_tol=1e-9, abs_tol=1e-9)
            for i in range(len(self.nodes))
            for j in range(i + 1, len(self.nodes))
            if self.values[i][j] is not None and self.values[j][i] is not None
        )

    def validate(self):
        if not self.nodes:
            return False, "The workbook has no column node identifiers."
        if len(set(self.nodes)) != len(self.nodes):
            return False, "Node identifiers are duplicated."
        if len(self.values) != len(self.nodes) or any(len(row) != len(self.nodes) for row in self.values):
            return False, "Row and column dimensions do not form a square matrix."
        for row_index, row in enumerate(self.values):
            for column_index, value in enumerate(row):
                if value is None:
                    return False, f"Missing value at {self.nodes[row_index]} → {self.nodes[column_index]}."
                if not isinstance(value, (int, float)) or not isfinite(value):
                    return False, f"Invalid numeric value at {self.nodes[row_index]} → {self.nodes[column_index]}."
                if value < 0:
                    return False, f"Negative value at {self.nodes[row_index]} → {self.nodes[column_index]}."
                if row_index == column_index and not isclose(value, 0.0, abs_tol=1e-9):
                    return False, f"The diagonal value for node {self.nodes[row_index]} must be zero."
        return True, "Valid labelled square matrix."


def days():
    """Return dataset day numbers found in the main dataset directory."""
    if not ROOT.exists():
        return []
    found = []
    for folder in ROOT.iterdir():
        match = _DAY_FOLDER.fullmatch(folder.name)
        if folder.is_dir() and match:
            found.append(int(match.group(1)))
    return sorted(set(found))


def matrix_path(day, kind):
    if kind not in PREFIX:
        raise DatasetError("Unknown matrix scenario.")
    if int(day) not in days():
        raise DatasetError(f"Dataset Day {day} is not available.")
    path = ROOT / f"day_{int(day)}" / f"{PREFIX[kind]}_{int(day)}.xlsx"
    if not path.is_file():
        raise FileNotFoundError(f"The {SCENARIO_LABELS[kind]} file for Day {day} is missing.")
    return path


def available_matrices(day):
    """Return existing scenario files for a day, including explicit missing entries."""
    result = {}
    for kind in PREFIX:
        try:
            result[kind] = matrix_path(day, kind)
        except (DatasetError, FileNotFoundError):
            result[kind] = None
    return result


def _is_blank(value):
    return value is None or (isinstance(value, str) and not value.strip())


def _node(value):
    if isinstance(value, bool):
        return str(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    return str(value).strip()


def _as_cost(value, row_label, column_label):
    if _is_blank(value) or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if not isfinite(number) or number < 0:
        return None
    return number


def _read_sheet(ws, day, kind, source_file):
    rows = list(ws.iter_rows(values_only=True))
    header_index = None
    header_start = None
    header_end = None

    # The supplied files use different sheet names and some have large formatted
    # areas. Find the first row containing a consecutive set of column labels.
    for row_index, row in enumerate(rows[:20]):
        nonempty = [i for i, value in enumerate(row[1:], start=1) if not _is_blank(value)]
        if len(nonempty) < 2:
            continue
        start, end = nonempty[0], nonempty[-1]
        if nonempty != list(range(start, end + 1)):
            continue
        labels = tuple(_node(row[i]) for i in range(start, end + 1))
        if len(set(labels)) != len(labels):
            continue
        header_index, header_start, header_end = row_index, start, end
        break

    if header_index is None:
        raise DatasetError(f"Sheet '{ws.title}' has no continuous row of unique column labels.")

    nodes = tuple(_node(rows[header_index][i]) for i in range(header_start, header_end + 1))
    records = {}
    for row_number, row in enumerate(rows[header_index + 1 :], start=header_index + 2):
        label = row[0] if row else None
        selected_values = [row[i] if i < len(row) else None for i in range(header_start, header_end + 1)]
        has_matrix_data = any(not _is_blank(value) for value in selected_values)

        # Ignore completely blank rows, including rows retained only by Excel formatting.
        if _is_blank(label):
            if has_matrix_data:
                raise DatasetError(f"Sheet '{ws.title}' has matrix values but no row label at Excel row {row_number}.")
            continue

        node = _node(label)
        if node in records:
            raise DatasetError(f"Sheet '{ws.title}' repeats row identifier {node} at Excel row {row_number}.")
        values = tuple(_as_cost(value, node, nodes[i]) for i, value in enumerate(selected_values))
        records[node] = values

    missing_rows = [node for node in nodes if node not in records]
    extra_rows = [node for node in records if node not in set(nodes)]
    if missing_rows or extra_rows:
        details = []
        if missing_rows:
            details.append("missing row labels: " + ", ".join(map(str, missing_rows[:8])))
        if extra_rows:
            details.append("unexpected row labels: " + ", ".join(map(str, extra_rows[:8])))
        raise DatasetError("Matrix row and column identifiers differ (" + "; ".join(details) + ").")

    values = tuple(records[node] for node in nodes)
    matrix = Matrix(day, kind, nodes, values, ws.title, str(source_file))
    valid, message = matrix.validate()
    if not valid:
        raise DatasetError(message)
    return matrix


@lru_cache(maxsize=36)
def load(day, kind):
    """Load a validated matrix once and cache it for subsequent page requests."""
    try:
        day = int(day)
    except (TypeError, ValueError) as exc:
        raise DatasetError("Dataset day must be an integer.") from exc
    path = matrix_path(day, kind)
    try:
        workbook = load_workbook(path, read_only=True, data_only=True)
    except Exception as exc:
        raise DatasetError(f"Could not read workbook {path.name}: {exc}") from exc
    try:
        errors = []
        for sheet in workbook.worksheets:
            try:
                return _read_sheet(sheet, day, kind, path)
            except DatasetError as exc:
                errors.append(f"{sheet.title}: {exc}")
        raise DatasetError("No valid matrix was found. " + " ".join(errors))
    finally:
        workbook.close()


def summary(matrix):
    """Summarize valid off-diagonal dataset values without counting self-routes."""
    edges = [
        matrix.values[i][j]
        for i in range(len(matrix.nodes))
        for j in range(len(matrix.nodes))
        if i != j and matrix.values[i][j] is not None
    ]
    return {
        "nodes": len(matrix.nodes),
        "dimensions": (len(matrix.nodes), len(matrix.nodes)),
        "min": min(edges) if edges else None,
        "max": max(edges) if edges else None,
        "avg": fsum(edges) / len(edges) if edges else None,
        "directed_edges": len(edges),
        "symmetric": matrix.symmetric,
        "sheet": matrix.sheet_name,
    }
