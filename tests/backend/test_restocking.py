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
