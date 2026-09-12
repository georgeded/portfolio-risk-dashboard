from fastapi.testclient import TestClient

from api.app import app

client = TestClient(app)


def test_health():
    r = client.get("/api/health")
    assert r.status_code == 200
    assert r.json()["price_source"] == "csv"


def test_scenarios_and_thresholds():
    assert len(client.get("/api/scenarios").json()["scenarios"]) == 6
    assert "max_position_weight" in client.get("/api/thresholds").json()["thresholds"]


def test_report_get():
    r = client.get("/api/report?tickers=AAA,BBB&weights=60,40&portfolio_value=1000")
    assert r.status_code == 200
    body = r.json()
    assert [p["ticker"] for p in body["positions"]] == ["AAA", "BBB"]
    assert abs(body["positions"][0]["weight"] - 0.6) < 1e-12
    assert body["portfolio"]["value"] == 1000


def test_report_post_with_quantities():
    r = client.post("/api/report", json={
        "positions": [{"ticker": "AAA", "quantity": 5}, {"ticker": "CCC", "quantity": 5}],
        "lookback_days": 126,
    })
    assert r.status_code == 200
    assert r.json()["window"]["trading_days"] == 126
    assert r.json()["portfolio"]["value"] > 0


def test_bad_input_is_400():
    r = client.post("/api/report", json={"positions": [{"ticker": "ZZZ", "weight": 1}]})
    assert r.status_code == 400
    r = client.get("/api/report?tickers=AAA,BBB&weights=1")
    assert r.status_code == 400
    r = client.post("/api/report", json={"positions": []})
    assert r.status_code == 400


def test_lookup():
    r = client.get("/api/lookup/aaa")
    assert r.status_code == 200
    assert r.json()["ticker"] == "AAA"
    assert client.get("/api/lookup/nope").status_code == 404


def test_frontend_served():
    r = client.get("/")
    assert r.status_code == 200
    assert "Risk dashboard" in r.text
