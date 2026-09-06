from datetime import datetime, timezone
import importlib
from fastapi.testclient import TestClient

api = importlib.import_module("weather_api.app")
PREFIX = "/api/experiments/weather/v0"

class Query:
    def query(self, station, at):
        if station != "CYYT": raise ValueError("only the contracted CYYT TAF is available")
        return {"data_mode": "live", "operational": False, "station": station, "at": at, "groups": []}

def test_taf_route_uses_timestamp_query_service(monkeypatch):
    monkeypatch.setattr(api, "taf_query_service", lambda: Query())
    response = TestClient(api.app).get(f"{PREFIX}/aviation/taf", params={"station": "CYYT", "at": "2026-09-06T14:00:00Z"})
    assert response.status_code == 200
    assert response.json()["at"] == "2026-09-06T14:00:00Z"
    assert response.json()["operational"] is False

def test_taf_route_rejects_naive_time_and_uncontracted_station(monkeypatch):
    monkeypatch.setattr(api, "taf_query_service", lambda: Query())
    client = TestClient(api.app)
    assert client.get(f"{PREFIX}/aviation/taf", params={"station": "CYYT", "at": "2026-09-06T14:00:00"}).status_code == 422
    assert client.get(f"{PREFIX}/aviation/taf", params={"station": "KBOS", "at": "2026-09-06T14:00:00Z"}).status_code == 422
