# Food Delivery Route Optimizer

A local five-page web application for exploring the supplied nine-day delivery research matrices and optimizing closed delivery tours with the Travelling Salesperson Problem (TSP). The planner calculates route costs from the selected Excel workbook and keeps its original location identifiers internal. Users assign Karnataka place names to the depot and selected stops; the workbooks do not include a verified identifier-to-place mapping.

## Problem statement

Given one starting depot, a selected set of delivery locations, and a distance or travel-time matrix, find a route that starts at the depot, visits every selected location exactly once, returns to the depot, and minimizes the selected matrix cost.

## Objectives

- Inspect measured distance and travel-time data for Day 1 through Day 9.
- Compare distance, most-likely time, optimistic time and pessimistic time scenarios.
- Optimize routes from a user-selected depot and delivery subset.
- Keep asymmetric costs directed throughout optimization and reporting.
- Independently verify route membership, closure, leg values and the displayed total.
- Export selected matrices and calculated routes as CSV.

## Technology stack

- **Backend:** Python 3.10 or later and the standard-library HTTP server, URL parsing, CSV, and TSP processing.
- **Excel data:** `openpyxl` 3.1 or later, below version 4.
- **Frontend:** HTML templates, CSS, and plain JavaScript. No external map or geocoding service is used.
- **Tests:** Python `unittest` with workbook fixtures and the supplied real workbooks.

## Project layout

```text
app.py                 Preserves the existing project helpers and launches the upgraded app
web_app.py             Five routes, HTML rendering, request validation and CSV exports
dataset_loader.py      Excel discovery, parsing, validation and cache
solver.py              Exact and heuristic TSP algorithms and independent verification
analytics.py           Measured matrix summaries and data availability checks
templates/             The five page templates plus the retained legacy input template
static/                Shared responsive styling and browser interactions
tests/                 Dataset, solver and web application tests
time_and_distance_matrices/  The original 36 Excel workbooks
```

## Application pages

1. **Overview (`/`)** — project summary, inventory counts, workflow, objectives, algorithm description and technology stack.
2. **Dataset Explorer (`/dataset`)** — day and matrix selection, source values, node and dimension statistics, min/max/average off-diagonal costs, directionality status, search, heatmap and CSV download.
3. **Route Planner (`/planner`)** — dataset/scenario selection, starting depot, required unique place names, Karnataka place suggestions, delivery-stop subset and validation before calculation. Original matrix IDs remain internal to the calculation.
4. **Results (`/results`)** — place-name route sequence and directed legs, total cost, algorithm and optimality label, computation time, tour comparison, independent checks and route CSV with place names only.
5. **Analytics & Reports (`/analytics`)** — day-wise matrix averages, selected-day summaries, same-tour scenario comparison, analytics CSV and order-characteristics availability.

## Dataset structure and integration

The application uses the workbooks already stored in `time_and_distance_matrices/day_1/` through `day_9/`:

```text
time_and_distance_matrices/
  day_1/
    distance_matrix_1.xlsx
    time_matrix_mostlikely_1.xlsx
    time_matrix_optimistic_1.xlsx
    time_matrix_pessimistic_1.xlsx
  ...
  day_9/
```

The loader selects workbooks by day and scenario. It reads the first usable labelled matrix in each workbook with `openpyxl` in read-only, cached-value mode. Sheet names differ between days, and some Excel files have large formatted blank areas; the loader ignores empty formatted rows, locates the continuous column-label row, reads row labels, aligns rows to the column identifier order, and validates a square matrix before the planner can use it. Missing, duplicate, mismatched, non-numeric, non-finite, negative or non-zero diagonal values are reported as validation errors. Missing values are never replaced with zero.

Dataset versions do not all have the same node count. The matrix identifiers are retained as stored in Excel. Matrix objects are cached for reuse by page requests; analytics summaries are cached after they are first calculated.

### Karnataka place names and matrix IDs

The research workbooks provide matrix location IDs, not Karnataka addresses, coordinates, or city names. The app does not guess that a particular row is Bengaluru, Mysuru, or another place. In the Route Planner:

- Choose the starting matrix location and enter its actual Karnataka place name.
- Select delivery locations; a place-name field appears for each selected location.
- Enter a unique name for the depot and every selected stop. Names are required and limited to 80 characters.
- The suggestion list includes Bengaluru, Mysuru, Mangaluru, Hubballi, Belagavi, Kalaburagi, Shivamogga, Tumakuru, Davanagere, Ballari, Vijayapura, Udupi, Hassan, Mandya, Kolar, Chitradurga, Raichur, Bidar, Chikkamagaluru, Madikeri, Chamarajanagar, Karwar, Gadag, Bagalkote, Ramanagara, Chikkaballapura, Yadgir, Koppal and Hampi. These are suggestions only; they are not mapped automatically to workbook rows.
- Route results, leg tables, tour comparisons and route CSVs display the supplied place names only. Matrix IDs remain internal for cost lookups. The Dataset Explorer continues to display source identifiers for inspection.

Use the research dataset's own location mapping, if available, when assigning names. Without that mapping, the optimizer still minimizes the selected matrix values, but the names are user-provided labels and cannot verify the real-world locations represented by those values.

The workbook inspection found complete square matrices with matching row and column labels in all 36 files. Each inspected matrix is asymmetric, so reverse travel costs are not treated as equal. Node counts vary by day:

| Day | Nodes per matrix |
| --- | ---: |
| 1 | 79 |
| 2 | 64 |
| 3 | 68 |
| 4 | 70 |
| 5 | 76 |
| 6 | 78 |
| 7 | 67 |
| 8 | 75 |
| 9 | 85 |

Day 4–Day 9 distance workbooks have a worksheet named `distance_km`, which identifies kilometres. The Day 1–Day 3 worksheets have generic Greek sheet names and do not state a distance unit; the UI reports those values as workbook units. The supplied time workbook labels do not state a time unit, so time values are also displayed in their recorded workbook units. Confirm any unstated units against the research source before using the numbers in a formal report.

The project contains the 36 day/scenario matrix workbooks. No separate order-characteristics table with `WEIGHT`, `VOLUME`, `SERVICE_TIME`, `EAT`, `LAT` or `TIME_WINDOW` fields was found in the project, so those statistics are reported as unavailable. The existing three-page solution PDF describes its own matrix as illustrative sample data and does not cite the nine-day research matrices. No research citation or source URL accompanies the matrix workbooks, so this project does not claim an attribution; add the original paper/dataset citation and confirm unspecified units when that source is available.

## Dataset preprocessing

- Preserve row and column node identifiers and matrix direction.
- Require the user to provide actual place names for the selected matrix locations because the workbooks contain IDs only and no verified Karnataka location mapping.
- Ignore trailing rows and columns that contain only Excel formatting.
- Reorder valid rows to match the labelled column order if the same identifiers appear in a different row order.
- Reject duplicate identifiers, missing matrix entries, negative or invalid costs, non-square label sets and non-zero diagonal values.
- Calculate measured summary statistics from off-diagonal values; route optimization uses every selected directed matrix edge.
- Keep missing scenario files visible as unavailable rather than substituting another scenario.

## TSP formulation

For depot `d`, selected delivery set `S`, and directed cost `c(i,j)` from the chosen matrix, the application solves:

```text
minimize  c(d, v1) + c(v1, v2) + ... + c(vn, d)
subject to each selected delivery node appearing exactly once,
           with the route starting and ending at d.
```

No symmetry is assumed. Reverse tours are collapsed only for symmetric matrices; asymmetric reverse tours remain distinct alternatives.

## Algorithms and optimality

- **Exact enumeration** is used through 9 delivery stops. For symmetric costs, one orientation from each reverse pair is compared. The result is mathematically optimal; the results table shows the shortest tour and up to 23 additional ranked tours.
- **Held–Karp dynamic programming** is used for 10–15 stops. It returns an exact optimum while avoiding factorial enumeration. Full alternative-tour enumeration is omitted at these sizes.
- **Nearest-neighbor followed by 2-opt** is used for 16 or more stops. It returns a valid heuristic route and is explicitly labelled as not guaranteed optimal.
- The planner allows up to 60 delivery stops. The solver has an additional 100-stop safety limit for direct requests.

All returned routes are checked independently: every selected stop appears once, the depot starts and ends the sequence, every leg has a valid matrix cost, and the displayed total agrees with a fresh sum of the route legs.

## Installation and execution

From the project directory:

```powershell
cd C:\mathsProject\food_delivery_tsp_web
$python310 = 'C:\Users\darsh\AppData\Local\Programs\Python\Python310\python.exe'
& $python310 -m pip install -r requirements.txt
& $python310 .\app.py
```

Open <http://127.0.0.1:8000>. This Python 3.10 installation should be the same one used to install the requirements. On Windows, `run.bat` changes to the project directory and starts the app with `py -3 app.py`; ensure that launcher uses an environment with `openpyxl` installed. Stop the server with `Ctrl+C`.

## Tests

Run the full suite with:

```powershell
$python310 = 'C:\Users\darsh\AppData\Local\Programs\Python\Python310\python.exe'
& $python310 -B -m unittest discover -s tests -v
```

The current suite has **27 tests**. It covers solver correctness and scale selection, all nine days and four scenarios, invalid and missing data, all five page routes, Karnataka place-name entry and HTML escaping, form validation, result verification and CSV exports. The suite has been run successfully with Python 3.10 against the supplied workbooks. Install the requirements before running the dataset and web tests.

## Screenshots

Add screenshots of the Overview, Dataset Explorer, Route Planner, Results and Analytics pages here after running the application locally.

## Limitations

- The application solves a single-vehicle TSP tour. It does not model multiple vehicles, capacities, time windows, traffic forecasts, geocoding or road-network changes.
- The workbook files do not contain a verified location-ID-to-Karnataka-place mapping. Users must assign the correct names; the place suggestions are not evidence that a matrix row represents that city.
- Travel-time units are not documented in the supplied workbook labels.
- The nine-day matrix source citation is absent from the workbooks and existing solution PDF; attribution and unspecified measurement units remain unverified.
- The larger-instance heuristic is valid but may not produce the globally shortest route.
- No order-characteristics dataset was supplied for weight, volume, service-time or time-window analytics.
- PDF report generation is not included; route, matrix and analytics data can be exported as CSV.

## Future enhancements

- Add the research paper citation, attribution and confirmed measurement units.
- Integrate an order-characteristics table and capacity or time-window constraints when the source data is provided.
- Add multi-vehicle routing and optional road-network travel-time updates.
- Generate a formatted PDF report from a selected route and dataset summary.
