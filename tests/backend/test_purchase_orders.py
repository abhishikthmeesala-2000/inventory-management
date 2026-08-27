"""
Tests for purchase order endpoints: creating a PO for a backlog item and
looking one up by backlog item ID.
"""
import pytest


class TestPurchaseOrderEndpoints:
    """Test suite for purchase-order-related endpoints."""

    def test_post_creates_purchase_order_for_valid_backlog_item(self, client):
        """A valid request creates a PO and returns it with server-set status/created_date."""
        response = client.post("/api/purchase-orders", json={
            "backlog_item_id": "1",
            "supplier_name": "Acme Parts Co.",
            "quantity": 500,
            "unit_cost": 12.5,
            "expected_delivery_date": "2025-10-15",
        })
        assert response.status_code == 200

        po = response.json()
        assert po["backlog_item_id"] == "1"
        assert po["supplier_name"] == "Acme Parts Co."
        assert po["quantity"] == 500
        assert po["unit_cost"] == 12.5
        assert po["status"]
        assert "created_date" in po
        assert "id" in po

    def test_get_purchase_order_after_creation(self, client):
        """A created PO can be looked up by its backlog_item_id."""
        create_response = client.post("/api/purchase-orders", json={
            "backlog_item_id": "2",
            "supplier_name": "Global Motors Supply",
            "quantity": 10,
            "unit_cost": 445.0,
            "expected_delivery_date": "2025-10-20",
        })
        assert create_response.status_code == 200
        created = create_response.json()

        get_response = client.get("/api/purchase-orders/2")
        assert get_response.status_code == 200

        fetched = get_response.json()
        assert fetched["id"] == created["id"]
        assert fetched["backlog_item_id"] == "2"
        assert fetched["supplier_name"] == "Global Motors Supply"

    def test_get_purchase_order_for_backlog_item_without_po_returns_404(self, client):
        """A backlog item with no PO yet returns 404, not a 500 or empty object."""
        response = client.get("/api/purchase-orders/nonexistent-backlog-id-999")
        assert response.status_code == 404

    def test_backlog_reflects_has_purchase_order_after_creation(self, client):
        """GET /api/backlog picks up a newly created PO via has_purchase_order."""
        create_response = client.post("/api/purchase-orders", json={
            "backlog_item_id": "3",
            "supplier_name": "Valve Supply Inc.",
            "quantity": 80,
            "unit_cost": 22.0,
            "expected_delivery_date": "2025-10-18",
        })
        assert create_response.status_code == 200

        backlog_response = client.get("/api/backlog")
        assert backlog_response.status_code == 200

        backlog_item = next(item for item in backlog_response.json() if item["id"] == "3")
        assert backlog_item["has_purchase_order"] is True

    def test_post_unknown_backlog_item_id_returns_400(self, client):
        """Referencing a backlog item that doesn't exist is rejected, not a 500."""
        response = client.post("/api/purchase-orders", json={
            "backlog_item_id": "nonexistent-backlog-id-999",
            "supplier_name": "Nobody",
            "quantity": 10,
            "unit_cost": 5.0,
            "expected_delivery_date": "2025-10-15",
        })
        assert response.status_code == 400

    def test_post_non_positive_quantity_returns_400(self, client):
        response = client.post("/api/purchase-orders", json={
            "backlog_item_id": "4",
            "supplier_name": "Widget Works",
            "quantity": 0,
            "unit_cost": 5.0,
            "expected_delivery_date": "2025-10-15",
        })
        assert response.status_code == 400
