"""Target discovery uses the result limit after grouping and distance ordering."""

import json

import pytest

from services.data_pipeline import live_acquisition
from services.data_pipeline.sources.base import HttpResponse


def test_nearby_host_selection_limits_grouped_results(monkeypatch):
    rows = [{"tid": index + 1, "distance_pc": index + 0.5} for index in range(20)]

    def request(self, params):
        # Reproduces the observed underfilled DISTINCT TOP response; MAXREC
        # bounds the explicitly grouped, distance-ordered result instead.
        result = rows[:4] if "top " in params["query"].lower() else rows
        assert params["MAXREC"] == 20
        return HttpResponse(200, {}, json.dumps(result).encode()), 1, 3

    monkeypatch.setattr(live_acquisition.NasaTapRequester, "request", request)
    selected = live_acquisition.select_nearby_confirmed_hosts()
    assert len(selected.tic_ids) == 20
    assert selected.provenance["selected_hosts"] == rows
    assert selected.provenance["attempt_count"] == 1


@pytest.mark.parametrize(
    "rows",
    [
        [{"tid": 1, "distance_pc": 10}, {"tid": 2, "distance_pc": 5}],
        [{"tid": 1, "distance_pc": 10}, {"tid": 1, "distance_pc": 10}],
        [{"tid": 1, "distance_pc": 21}],
        [{"tid": True, "distance_pc": 5}],
        [{"tid": 1}],
        [],
    ],
)
def test_selection_rejects_unverifiable_scientific_scope(monkeypatch, rows):
    def request(self, params):
        return HttpResponse(200, {}, json.dumps(rows).encode()), 1, 3

    monkeypatch.setattr(live_acquisition.NasaTapRequester, "request", request)
    with pytest.raises(ValueError, match="NASA 目标发现"):
        live_acquisition.select_nearby_confirmed_hosts()
