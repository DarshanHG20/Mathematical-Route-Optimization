# Food Delivery Route Optimizer (TSP)

A login-free, three-page web app for a small Operations Research project. The interface uses HTML and CSS; the local server, place-name checks, matrix validation, exact TSP solver, and route comparison use only Python's standard library. No third-party packages or external map service are required.

## The three pages

1. **Overview** (`/`) explains the flow and links to the place form and sample result.
2. **Enter places** (`/input`) accepts a depot name, three delivery place names, and a 4 x 4 distance matrix.
3. **Route result** (`/results`) shows the shortest route, leg-by-leg lookup, three distinct tours, and verification checks.

On the input page, each place field has local autocomplete suggestions such as City Market, Bus Stand, College, Hospital, and Railway Station. Users can also type custom place names. Names must be non-empty, unique, and no more than 50 characters. The Restaurant and delivery place labels are all editable; their form order controls the matrix row and column order.

The default names, in matrix order, are:

1. Restaurant (depot)
2. City Market
3. Bus Stand
4. College

Edit the `LOCATION_NAMES` list near the top of `app.py` to change the defaults. Edit `PLACE_SUGGESTIONS` there to change the local suggestion list.

## Illustrative sample data

The pre-filled distance matrix is in kilometres. It is illustrative sample data, not actual map data and not Swiggy/Zomato data.

```text
0,4,6,7
4,0,3,5
6,3,0,4
7,5,4,0
```

The sample result page compares all three distinct round trips:

| Tour | Leg-by-leg addition | Total |
|---|---:|---:|
| Restaurant -> City Market -> Bus Stand -> College -> Restaurant | 4 + 3 + 4 + 7 | 18 km |
| Restaurant -> City Market -> College -> Bus Stand -> Restaurant | 4 + 5 + 4 + 6 | 19 km |
| Restaurant -> Bus Stand -> City Market -> College -> Restaurant | 6 + 3 + 5 + 7 | 21 km |

The shortest sample route is **Restaurant -> City Market -> Bus Stand -> College -> Restaurant**, for **18 km**.

## Run the application

1. Extract the ZIP file to a folder.
2. Open a terminal in `food_delivery_tsp_web`.
3. Run `python app.py`.
4. Open `http://127.0.0.1:8000` in a browser.
5. Select **Enter places**, type or choose place-name suggestions, and enter the matrix in the displayed order.
6. Stop the server with `Ctrl+C` in the terminal.

On Windows, `run.bat` starts the same local application. The app has no login and sends no place names or distances to a service.

## Input rules and assumptions

- Enter exactly four unique place names: one depot and three delivery places.
- Enter exactly four matrix rows with four comma-separated values per row.
- Keep row and column order identical to the place fields above the matrix.
- Distances must be finite, non-negative, symmetric, and zero on the diagonal.
- Values are interpreted as kilometres.
- The solver assumes a symmetric distance matrix. It removes reverse duplicates and compares the three unique closed tours.
- Every tour starts and ends at the depot and visits each delivery place once.
- For real project data, use anonymized place names and driving distances from an appropriate map/routing source. The suggestion list only supplies names; it does not provide coordinates or distances.

## How the solver works

1. Fix the depot as the start and end point.
2. Generate all 3! = 6 delivery-place orders.
3. Remove reverse duplicates because the matrix is symmetric, leaving 3 distinct tours.
4. Add every consecutive leg, including the return to the depot.
5. Select the lowest total and independently recalculate it.
6. Verify the depot, place visits, total, and tour count.

Exact enumeration is suitable for four places. Its runtime grows factorially, so it is not intended for a large fleet-routing system.

## Run verification tests

From the project folder, run:

```text
python -m unittest discover -s tests -v
```

Tests cover the sample calculation, custom place names, suggestions and page rendering, valid matrix acceptance, invalid place/matrix rejection, and local HTTP form submissions.

## Project files

```text
food_delivery_tsp_web/
  app.py
  requirements.txt
  run.bat
  README.md
  templates/index.html
  templates/input.html
  templates/results.html
  static/style.css
  tests/test_solver.py
  tests/test_web_app.py
  docs/Food_Delivery_TSP_Project_Solution.pdf
```

## Scope

This is a single-rider, distance-minimization TSP. It does not model traffic, time windows, food preparation time, vehicle capacity, multiple riders, or routes that finish at the last delivery place instead of returning to the depot.
