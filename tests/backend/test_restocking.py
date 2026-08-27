"""
Tests for the restocking feature: data model foundation, recommendation
endpoint, and order submission/listing endpoints.
"""
from datetime import datetime

import pytest


class TestRestockDataModel:
    """Task 1: lead_time_days field + RestockOrder models + in-memory store."""

    def test_inventory_items_have_lead_time_days(self, client):
        """Every inventory item exposes a positive integer lead_time_days."""
        response = client.get("/api/inventory")
        assert response.status_code == 200

        data = response.json()
        assert len(data) > 0

        for item in data:
            assert "lead_time_days" in item, f"Missing lead_time_days on {item.get('sku')}"
            assert isinstance(item["lead_time_days"], int)
            assert item["lead_time_days"] > 0

    def test_restock_order_model_importable_and_constructible(self):
        """RestockOrder/CreateRestockOrderRequest models exist with expected fields."""
        from main import CreateRestockOrderRequest, RestockOrder, RestockOrderItem

        request = CreateRestockOrderRequest(items=[{"sku": "PCB-001", "quantity": 10}])
        assert request.items[0]["sku"] == "PCB-001"

        line_item = RestockOrderItem(
            sku="PCB-001",
            name="Single Layer PCB Assembly",
            quantity=10,
            unit_cost=24.99,
            line_total=249.90,
        )

        order = RestockOrder(
            id="1",
            order_number="RO-2025-0001",
            items=[line_item],
            total_cost=249.90,
            status="Submitted",
            created_date="2025-09-30T10:30:00",
            expected_delivery_date="2025-10-10T10:30:00",
        )
        assert order.total_cost == 249.90
        assert order.items[0].sku == "PCB-001"

    def test_restock_orders_store_starts_empty(self):
        """The in-memory restock_orders list is importable from main and starts empty."""
        from main import restock_orders

        assert restock_orders == []


class TestRestockRecommendations:
    """Task 2: GET /api/restocking/recommendations."""

    def test_zero_budget_returns_no_items_but_reports_max_budget(self, client):
        """Budget of 0 recommends nothing, but still reports the full shortfall cost."""
        response = client.get("/api/restocking/recommendations?budget=0")
        assert response.status_code == 200

        data = response.json()
        assert data["recommended_items"] == []
        assert data["budget_used"] == 0
        assert data["max_budget"] > 0

    def test_omitted_budget_defaults_to_no_recommendations(self, client):
        """Omitting the budget param behaves the same as budget=0."""
        response = client.get("/api/restocking/recommendations")
        assert response.status_code == 200
        assert response.json()["recommended_items"] == []

    def test_large_budget_returns_every_item_with_positive_shortfall(self, client):
        """A budget covering everything returns every forecast with shortfall > 0."""
        response = client.get("/api/restocking/recommendations?budget=1000000")
        assert response.status_code == 200

        data = response.json()
        assert data["budget_used"] == pytest.approx(data["max_budget"], abs=0.01)

        skus = {item["sku"] for item in data["recommended_items"]}
        # SRV-302 has a decreasing trend (forecast < current demand) -> zero shortfall
        assert "SRV-302" not in skus
        # SRV-301 has the largest single shortfall cost in the fixture data
        assert "SRV-301" in skus

    def test_mid_size_budget_respects_budget_cap(self, client):
        """No combination of recommended items may exceed the requested budget."""
        response = client.get("/api/restocking/recommendations?budget=5000")
        assert response.status_code == 200

        data = response.json()
        total = sum(item["line_total"] for item in data["recommended_items"])
        assert total <= 5000
        assert data["budget_used"] == pytest.approx(total, abs=0.01)

        for item in data["recommended_items"]:
            assert item["line_total"] <= 5000

    def test_recommended_item_fields(self, client):
        """Each recommended item exposes the fields the frontend needs to render."""
        response = client.get("/api/restocking/recommendations?budget=1000000")
        data = response.json()
        assert len(data["recommended_items"]) > 0

        for item in data["recommended_items"]:
            assert isinstance(item["sku"], str)
            assert isinstance(item["name"], str)
            assert item["trend"] in ("increasing", "stable", "decreasing")
            assert isinstance(item["quantity"], int) and item["quantity"] > 0
            assert isinstance(item["unit_cost"], (int, float))
            assert isinstance(item["lead_time_days"], int) and item["lead_time_days"] > 0
            assert item["line_total"] == pytest.approx(item["quantity"] * item["unit_cost"], abs=0.01)

    def test_unmatched_forecast_sku_is_skipped_not_a_500(self, client):
        """A forecast referencing a SKU absent from inventory is silently skipped."""
        from main import demand_forecasts

        fake_forecast = {
            "id": "test-unmatched",
            "item_sku": "NONEXISTENT-SKU-999",
            "item_name": "Nonexistent Item",
            "current_demand": 10,
            "forecasted_demand": 100,
            "trend": "increasing",
            "period": "Next 30 days",
        }
        demand_forecasts.append(fake_forecast)
        try:
            response = client.get("/api/restocking/recommendations?budget=1000000")
            assert response.status_code == 200
            skus = {item["sku"] for item in response.json()["recommended_items"]}
            assert "NONEXISTENT-SKU-999" not in skus
        finally:
            demand_forecasts.remove(fake_forecast)


class TestRestockOrders:
    """Task 3: POST/GET /api/restocking/orders."""

    def test_post_creates_order_with_server_computed_totals(self, client):
        """Server computes name/unit_cost/total_cost from inventory, ignoring any client-sent price."""
        response = client.post("/api/restocking/orders", json={
            "items": [{"sku": "PCB-001", "quantity": 10, "unit_cost": 999999}]
        })
        assert response.status_code == 200

        order = response.json()
        assert order["status"] == "Submitted"
        assert len(order["items"]) == 1

        item = order["items"][0]
        assert item["sku"] == "PCB-001"
        assert item["name"] == "Single Layer PCB Assembly"
        assert item["unit_cost"] == 24.99  # server's price, not the bogus 999999 sent by the client
        assert item["line_total"] == pytest.approx(249.90, abs=0.01)
        assert order["total_cost"] == pytest.approx(249.90, abs=0.01)

    def test_post_multiple_items_sums_total_cost(self, client):
        """total_cost reflects every line item, computed server-side."""
        response = client.post("/api/restocking/orders", json={
            "items": [
                {"sku": "PCB-001", "quantity": 5},
                {"sku": "MCU-401", "quantity": 20},
            ]
        })
        assert response.status_code == 200

        expected_total = 5 * 24.99 + 20 * 8.25
        assert response.json()["total_cost"] == pytest.approx(expected_total, abs=0.01)

    def test_post_unknown_sku_returns_400(self, client):
        """An order line referencing a SKU absent from inventory is rejected, not a 500."""
        response = client.post("/api/restocking/orders", json={
            "items": [{"sku": "NONEXISTENT-SKU-999", "quantity": 5}]
        })
        assert response.status_code == 400

    def test_post_non_positive_quantity_returns_400(self, client):
        response = client.post("/api/restocking/orders", json={
            "items": [{"sku": "PCB-001", "quantity": 0}]
        })
        assert response.status_code == 400

    def test_post_empty_items_returns_400(self, client):
        response = client.post("/api/restocking/orders", json={"items": []})
        assert response.status_code == 400

    def test_expected_delivery_date_uses_longest_lead_time(self, client):
        """expected_delivery_date = created_date + the longest lead_time_days among the order's items."""
        # MCU-401 lead_time_days=5, SRV-301 lead_time_days=18 (see server/data/inventory.json)
        response = client.post("/api/restocking/orders", json={
            "items": [
                {"sku": "MCU-401", "quantity": 5},
                {"sku": "SRV-301", "quantity": 2},
            ]
        })
        assert response.status_code == 200

        order = response.json()
        created = datetime.fromisoformat(order["created_date"])
        expected = datetime.fromisoformat(order["expected_delivery_date"])
        assert (expected - created).days == 18

    def test_get_includes_previously_submitted_order(self, client):
        """A submitted order shows up in the GET list."""
        create_response = client.post("/api/restocking/orders", json={
            "items": [{"sku": "DSP-403", "quantity": 3}]
        })
        assert create_response.status_code == 200
        created_order_number = create_response.json()["order_number"]

        list_response = client.get("/api/restocking/orders")
        assert list_response.status_code == 200

        order_numbers = [o["order_number"] for o in list_response.json()]
        assert created_order_number in order_numbers

    def test_get_returns_orders_in_submission_order(self, client):
        """Orders appear in the order they were submitted."""
        first = client.post("/api/restocking/orders", json={"items": [{"sku": "MCU-402", "quantity": 1}]}).json()
        second = client.post("/api/restocking/orders", json={"items": [{"sku": "MCU-402", "quantity": 1}]}).json()

        all_orders = client.get("/api/restocking/orders").json()
        order_numbers = [o["order_number"] for o in all_orders]
        assert order_numbers.index(first["order_number"]) < order_numbers.index(second["order_number"])
