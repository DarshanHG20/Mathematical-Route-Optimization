"""Exact and heuristic solvers for directed or symmetric travelling-salesperson tours."""

from dataclasses import dataclass
from heapq import heappush, heapreplace
from itertools import permutations
from math import fsum, isclose, isfinite, inf


EXACT_ENUMERATION_STOPS = 9
HELD_KARP_STOPS = 15
MAX_SOLVER_STOPS = 100
ALTERNATIVE_LIMIT = 24


@dataclass(frozen=True)
class Result:
    route: tuple
    legs: tuple
    total: float
    algorithm: str
    optimal: bool
    alternatives: tuple
    tours_compared: int = 0


def _check(matrix, depot, stops):
    valid, message = matrix.validate()
    if not valid:
        raise ValueError(f"Selected matrix is invalid: {message}")
    if depot not in matrix.nodes or any(stop not in matrix.nodes for stop in stops):
        raise ValueError("A selected node does not exist in the matrix.")
    if not stops:
        raise ValueError("Select at least one delivery location.")
    if depot in stops:
        raise ValueError("The depot cannot also be a delivery stop.")
    if len(set(stops)) != len(stops):
        raise ValueError("Delivery stops must be unique.")
    if len(stops) > MAX_SOLVER_STOPS:
        raise ValueError(f"Select no more than {MAX_SOLVER_STOPS} delivery stops.")


def _score(matrix, route):
    legs = tuple(
        (route[index], route[index + 1], matrix.cost(route[index], route[index + 1]))
        for index in range(len(route) - 1)
    )
    return legs, fsum(leg[2] for leg in legs)


def _is_symmetric(matrix):
    return matrix.symmetric


def _enumerate(matrix, depot, stops):
    positions = {node: index for index, node in enumerate(matrix.nodes)}
    symmetric = _is_symmetric(matrix)
    best = []
    compared = 0

    for order in permutations(stops):
        # A symmetric closed tour and its reverse have identical cost. Keep one
        # orientation by matrix order; directed matrices retain both directions.
        if symmetric and len(order) > 1 and positions[order[0]] > positions[order[-1]]:
            continue
        route = (depot,) + order + (depot,)
        legs, total = _score(matrix, route)
        route_order = tuple(positions[node] for node in route[1:-1])
        rank = (total, route_order)
        item = (-total, tuple(-index for index in route_order), route, legs)
        compared += 1
        if len(best) < ALTERNATIVE_LIMIT:
            heappush(best, item)
        else:
            worst_rank = (-best[0][0], tuple(-index for index in best[0][1]))
            if rank < worst_rank:
                heapreplace(best, item)

    if not best:
        raise ValueError("No complete route could be generated.")
    ranked = sorted(
        ((-item[0], tuple(-index for index in item[1]), item[2], item[3]) for item in best),
        key=lambda item: (item[0], item[1]),
    )
    total, _, route, legs = ranked[0]
    alternatives = tuple((item[2], item[0]) for item in ranked[1:])
    return Result(route, legs, total, "Exact enumeration", True, alternatives, compared)


def _held_karp(matrix, depot, stops):
    count = len(stops)
    state_count = 1 << count
    costs = [[inf] * count for _ in range(state_count)]
    parents = [[-1] * count for _ in range(state_count)]

    for index, node in enumerate(stops):
        costs[1 << index][index] = matrix.cost(depot, node)

    for mask in range(1, state_count):
        for last in range(count):
            bit = 1 << last
            if not mask & bit or mask == bit:
                continue
            previous_mask = mask ^ bit
            best_cost = inf
            best_previous = -1
            for previous in range(count):
                if previous_mask & (1 << previous):
                    candidate = costs[previous_mask][previous] + matrix.cost(stops[previous], stops[last])
                    if candidate < best_cost:
                        best_cost, best_previous = candidate, previous
            costs[mask][last] = best_cost
            parents[mask][last] = best_previous

    full_mask = state_count - 1
    final_cost, final = min(
        (costs[full_mask][last] + matrix.cost(stops[last], depot), last)
        for last in range(count)
    )
    order_indices = []
    mask, last = full_mask, final
    while last >= 0:
        order_indices.append(last)
        previous = parents[mask][last]
        mask ^= 1 << last
        last = previous
    order_indices.reverse()
    route = (depot,) + tuple(stops[index] for index in order_indices) + (depot,)
    legs, total = _score(matrix, route)
    if not isclose(total, final_cost, rel_tol=1e-9, abs_tol=1e-9):
        raise ValueError("Held-Karp reconstruction did not match its dynamic-programming total.")
    return Result(route, legs, total, "Held-Karp dynamic programming", True, (), 0)


def _nearest_neighbor_two_opt(matrix, depot, stops):
    remaining = set(stops)
    path = [depot]
    while remaining:
        next_node = min(remaining, key=lambda node: (matrix.cost(path[-1], node), str(node)))
        path.append(next_node)
        remaining.remove(next_node)

    route_with_depot = tuple(path + [depot])
    _, current_cost = _score(matrix, route_with_depot)
    improved = True
    passes = 0
    max_passes = min(len(path), 30)
    while improved and passes < max_passes:
        improved = False
        passes += 1
        for start in range(1, len(path) - 1):
            for end in range(start + 1, len(path)):
                candidate_path = path[:start] + path[start : end + 1][::-1] + path[end + 1 :]
                candidate_route = tuple(candidate_path + [depot])
                _, candidate_cost = _score(matrix, candidate_route)
                if candidate_cost < current_cost - 1e-12:
                    path, current_cost = candidate_path, candidate_cost
                    improved = True
        if not improved:
            break

    route = tuple(path + [depot])
    legs, total = _score(matrix, route)
    return Result(route, legs, total, "Nearest-neighbor with 2-opt", False, (), 0)


def solve(matrix, depot, stops):
    """Solve a closed TSP tour while fixing the depot and preserving edge direction."""
    stops = tuple(stops)
    _check(matrix, depot, stops)
    count = len(stops)
    if count <= EXACT_ENUMERATION_STOPS:
        return _enumerate(matrix, depot, stops)
    if count <= HELD_KARP_STOPS:
        return _held_karp(matrix, depot, stops)
    return _nearest_neighbor_two_opt(matrix, depot, stops)


def verify(matrix, result, depot, stops):
    """Independently validate route membership, leg costs, closure, and total."""
    stops = tuple(stops)
    route = tuple(result.route)
    valid_matrix, _ = matrix.validate()
    visits_once = (
        len(route) == len(stops) + 2
        and len(route[1:-1]) == len(stops)
        and set(route[1:-1]) == set(stops)
        and len(set(route[1:-1])) == len(stops)
    )
    closed = len(route) >= 3 and route[0] == depot and route[-1] == depot

    expected_legs = []
    leg_values_valid = valid_matrix and len(route) >= 2
    if leg_values_valid:
        for start, end in zip(route, route[1:]):
            try:
                value = matrix.cost(start, end)
            except (KeyError, ValueError):
                leg_values_valid = False
                break
            if value is None or not isfinite(value) or value < 0:
                leg_values_valid = False
                break
            expected_legs.append((start, end, value))

    legs_match = len(expected_legs) == len(result.legs) and all(
        expected[0] == actual[0]
        and expected[1] == actual[1]
        and isclose(expected[2], actual[2], rel_tol=1e-9, abs_tol=1e-9)
        for expected, actual in zip(expected_legs, result.legs)
    )
    recalculated_total = fsum(leg[2] for leg in expected_legs)
    total_matches = leg_values_valid and isclose(
        recalculated_total, result.total, rel_tol=1e-9, abs_tol=1e-9
    ) and isclose(
        fsum(leg[2] for leg in result.legs), result.total, rel_tol=1e-9, abs_tol=1e-9
    )

    return {
        "Every selected stop is visited exactly once": visits_once,
        "The depot starts and ends the route": closed,
        "Every route leg uses a valid matrix value": leg_values_valid and legs_match,
        "The displayed total matches an independent sum": total_matches,
    }
