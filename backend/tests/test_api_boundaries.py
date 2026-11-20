from fastapi.routing import APIRoute
import inspect
from datetime import date
from typing import get_args

import pytest

from app.api.security import require_admin_access, require_authenticated_user, require_pro_access
from app.api.v1 import admin, backtests, custom_accumulators, selections, tickets


def _route(path: str, method: str, router):
    return next(
        route
        for route in router.routes
        if isinstance(route, APIRoute)
        and route.path == path
        and method in route.methods
    )


def test_admin_routes_require_research_access():
    for route in admin.router.routes:
        if isinstance(route, APIRoute):
            dependency_callables = {
                dependency.call for dependency in route.dependant.dependencies
            }
            assert require_admin_access in dependency_callables, route.path


def test_backtest_run_accepts_authenticated_admin_or_research_key():
    route = _route("/backtests/run", "POST", backtests.router)
    dependency_callables = {
        dependency.call for dependency in route.dependant.dependencies
    }
    assert require_admin_access in dependency_callables


def test_daily_tickets_do_not_publish_internal_best_value():
    source = inspect.getsource(tickets.get_daily_tickets)
    assert "include_internal=include_internal" in source
    assert "reader_ticket_types(include_internal, admin=admin)" in source
    assert "AccumulatorTicket.ticket_type.in_(visible_ticket_types)" in source
    route = _route("/tickets/daily", "GET", tickets.router)
    include_internal = next(
        parameter
        for parameter in route.dependant.query_params
        if parameter.name == "include_internal"
    )
    assert include_internal.default is False


def test_ticket_history_defaults_to_public_stream():
    route = _route("/tickets/history", "GET", tickets.router)
    include_internal = route.dependant.query_params[1]
    assert include_internal.default is False


def test_customer_ticket_reads_require_an_authenticated_session():
    for path in ("/tickets/daily", "/tickets/history", "/tickets/{ticket_id}"):
        route = _route(path, "GET", tickets.router)
        dependency_callables = {
            dependency.call for dependency in route.dependant.dependencies
        }
        assert require_authenticated_user in dependency_callables, route.path


def test_public_proof_is_readable_without_an_account():
    route = _route("/tickets/public-proof", "GET", tickets.router)
    dependency_callables = {
        dependency.call for dependency in route.dependant.dependencies
    }
    assert require_authenticated_user not in dependency_callables
    assert require_pro_access not in dependency_callables


def test_custom_accumulator_mutations_require_authenticated_pro_access():
    for route in custom_accumulators.router.routes:
        if isinstance(route, APIRoute) and route.path in {"", "/{accumulator_id}"}:
            dependency_callables = {
                dependency.call for dependency in route.dependant.dependencies
            }
            assert require_pro_access in dependency_callables, route.path


def test_fixture_pick_counts_require_a_session_but_not_pro_access():
    route = _route("/selections/qualified/counts", "GET", selections.router)
    dependency_callables = {
        dependency.call for dependency in route.dependant.dependencies
    }
    assert require_authenticated_user in dependency_callables
    assert require_pro_access not in dependency_callables


def test_fixture_pick_counts_expose_counts_only():
    route = _route("/selections/qualified/counts", "GET", selections.router)
    (response_model,) = get_args(route.response_model)
    assert set(response_model.model_fields) == {"match_id", "picks"}


@pytest.mark.asyncio
async def test_fixture_pick_counts_group_picks_by_fixture():
    class _Result:
        def all(self):
            return [(7, 3), (9, 1)]

    class _Db:
        async def execute(self, *_args, **_kwargs):
            return _Result()

    rows = await selections.get_qualified_pick_counts(
        date=date(2026, 11, 15), min_qscore=75, db=_Db(), _user=object()
    )

    assert [(row.match_id, row.picks) for row in rows] == [(7, 3), (9, 1)]
