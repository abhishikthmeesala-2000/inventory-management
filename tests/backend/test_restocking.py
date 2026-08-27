"""
Tests for the restocking feature: data model foundation, recommendation
endpoint, and order submission/listing endpoints.
"""
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
