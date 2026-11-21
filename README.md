# Food Delivery Route Optimizer

A small, login-free web app for finding the shortest delivery loop through three places. It uses an exact Traveling Salesperson Problem (TSP) solver and Python's standard library, so it needs no third-party packages or map service.

## Run the app

Open a terminal in the `food_delivery_tsp_web` folder and run:

```powershell
cd food_delivery_tsp_web
python app.py
```

Then visit <http://127.0.0.1:8000> in your browser. On Windows, you can also run `run.bat` from that folder. Stop the server with `Ctrl+C`.

## How it works

- Enter a depot, three delivery place names, and a 4-by-4 distance matrix.
- The app validates the names and matrix, then compares all three distinct round trips.
- The result shows the shortest route, each leg, tour totals, and verification checks.
- Distances must be finite, non-negative, symmetric, and zero on the diagonal. Matrix rows and columns must follow the displayed place order.
- Distances are treated as kilometres. The included sample values are illustrative, not real map measurements.

The solver starts and ends at the depot and visits each delivery place once. It is designed for this small four-place example, not large fleet-routing problems.

## Tests

From `food_delivery_tsp_web`, run:

```powershell
python -m unittest discover -s tests -v
```

## Project structure

```text
food_delivery_tsp_web/
  app.py
  run.bat
  requirements.txt
  templates/
  static/
  tests/
  docs/
  README.md
```

See [`food_delivery_tsp_web/README.md`](food_delivery_tsp_web/README.md) for the full guide, sample matrix, solver details, and input rules.
