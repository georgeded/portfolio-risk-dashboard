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


def test_malformed_input_is_400_not_500():
    for weights in ("abc,1", "nan,1", "inf,1", "1,,2"):
        r = client.get(f"/api/report?tickers=AAA,BBB&weights={weights}")
        assert r.status_code == 400, weights
    assert client.get("/api/report?tickers=../../secret").status_code == 400
    assert client.get("/api/report?tickers=AAA,BBB&base_currency=dollars").status_code == 400
    r = client.post("/api/report", json={"positions": [{"ticker": "AAA", "weight": 1}], "base_currency": "us"})
    assert r.status_code == 400


def test_lookup():
    r = client.get("/api/lookup/aaa")
    assert r.status_code == 200
    assert r.json()["ticker"] == "AAA"
    assert r.json()["price_in_base"] == r.json()["last_price"]
    eur = client.get("/api/lookup/aaa?base=EUR").json()
    assert eur["base_currency"] == "EUR" and abs(eur["price_in_base"] / eur["last_price"] - 1) > 1e-6
    assert client.get("/api/lookup/aaa?base=euro").status_code == 400
    assert client.get("/api/lookup/nope").status_code == 404
    assert client.get("/api/lookup/bad$ticker").status_code == 400


def test_search():
    r = client.get("/api/search?q=aa")
    assert r.status_code == 200
    assert [x["ticker"] for x in r.json()["results"]] == ["AAA"]
    assert client.get("/api/search?q=").status_code == 422


def test_frontend_served():
    r = client.get("/")
    assert r.status_code == 200
    assert "Risk dashboard" in r.text
