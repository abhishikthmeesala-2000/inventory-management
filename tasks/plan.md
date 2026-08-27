# Implementation Plan: Restocking Tab

## Overview

Add a new "Restocking" tab that lets a user set a budget via a slider, see
demand-forecast-driven restock recommendations that fit within that budget,
and submit a restocking order. Submitted orders show up in the existing
Orders tab under a new "Submitted Orders" section, including delivery lead
time.

## Architecture Decisions

- **Ranking algorithm**: join `demand_forecasts.json` to `inventory.json` by
  SKU. For each forecast, `shortfall_qty = max(forecasted_demand -
  current_demand, 0)` and `shortfall_cost = shortfall_qty * unit_cost`. Sort
  descending by `shortfall_cost`. Greedily walk the sorted list: if an item's
  cost fits in the remaining budget, take it and decrement the remaining
  budget; otherwise skip it and keep going (so cheaper items later in the
  list still get picked) — a simple greedy bin-fill, not a full knapsack
  solve. Chosen because it's a couple of lines of Python, deterministic, and
  matches "recommend items to restock" without needing an optimizer.
- **Budget slider range**: dynamic. `max_budget` = sum of `shortfall_cost`
  across every forecast item (the cost to fully cover 100% of the current
  shortfall), recomputed on every request from live data — no hardcoded cap
  to go stale.
- **Lead time**: add a `lead_time_days` field to every record in
  `server/data/inventory.json` (int, varied by category — e.g. 5-21 days).
  This is the only data-model change; it's a small, realistic addition and
  it's the one place lead time will ever need to be read from.
- **Persistence / new endpoint**: build a dedicated `RestockOrder` /
  `CreateRestockOrderRequest` model and route, separate from the existing
  unused `PurchaseOrder` model (which is keyed on `backlog_item_id` and
  doesn't fit demand-forecast-based restocking). New in-memory list
  `restock_orders` in `server/mock_data.py`, following the same
  load-once/in-memory pattern as everything else — submitted orders are lost
  on backend restart, consistent with the rest of the app. This does **not**
  fix the pre-existing `/api/tasks` / `/api/purchase-orders` gap flagged
  earlier — that's an unrelated, separate gap and stays out of scope here.
- **New endpoints** (`server/main.py`):
  - `GET /api/restocking/recommendations?budget=<float>` → `{ max_budget,
    budget_used, recommended_items: [...] }`. Computing `max_budget` on
    every call keeps this a single endpoint instead of two.
  - `POST /api/restocking/orders` → body is the list of accepted line items
    (sku, quantity, unit_cost) the user is submitting; server recomputes
    totals server-side (never trusts client-sent totals), assigns an id/
    order_number, sets `expected_delivery_date` from
    `max(lead_time_days)` across the order's items, appends to
    `restock_orders`, returns the created order.
  - `GET /api/restocking/orders` → list of submitted restock orders, consumed
    by the Orders tab's new section.
- **No manual per-item quantity editing in v1**: the user submits the
  recommended set as computed. This matches the literal spec ("recommend
  items... Place Order button submits the restocking order") and keeps the
  UI to slider + list + button. Flag as an assumption, not a question,
  since it doesn't change the architecture if revisited later.
- **Mandatory tool rule** (root `CLAUDE.md`): every task below that creates
  or modifies a `.vue` file MUST be implemented via the `vue-expert`
  subagent — this applies to Tasks 5, 6, and 7.
- **Testing**: new backend endpoints get pytest coverage in
  `tests/backend/` per the `backend-api-test` skill.

## Task List

### Phase 1: Backend foundation

- [ ] Task 1: Data model — lead time field + RestockOrder models + in-memory store
- [ ] Task 2: Recommendation endpoint
- [ ] Task 3: Submit / list restock-order endpoints

### Checkpoint: Backend complete
- [ ] `cd tests && uv run pytest backend/ -v` passes
- [ ] Manual check via `http://localhost:8001/docs`: `/api/restocking/recommendations?budget=5000` returns a sane, budget-respecting list; `POST /api/restocking/orders` then `GET /api/restocking/orders` round-trips correctly
- [ ] Review with human before proceeding to frontend

### Phase 2: Restocking tab (frontend)

- [ ] Task 4: API client methods + route + nav entry
- [ ] Task 5: Restocking.vue — budget slider + live recommendations
- [ ] Task 6: Restocking.vue — Place Order flow (submit, confirm, loading/error states)

### Checkpoint: Restocking tab works end-to-end
- [ ] Manual/Playwright check: moving the slider updates the recommended list; Place Order succeeds and shows confirmation
- [ ] Review with human before proceeding to Orders integration

### Phase 3: Orders tab integration

- [ ] Task 7: "Submitted Orders" section in Orders.vue with lead time display

### Checkpoint: Full feature complete
- [ ] Place a restocking order on the Restocking tab, confirm it appears in the Orders tab's Submitted Orders section with the correct lead time
- [ ] All backend tests pass, frontend builds clean (`npm run build`)
- [ ] All acceptance criteria met, ready for review

## Risks and Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| Greedy ranking leaves budget unused when no combination fits exactly | Low | Acceptable for a demo; documented behavior, not a bug |
| Submitted orders lost on backend restart | Low | Consistent with the rest of the app's in-memory model; explicitly called out to the user |
| `lead_time_days` values are fabricated (no real supplier data) | Low | Values are clearly demo data, same trust level as the rest of `inventory.json` |
| Frontend polls recommendations on every slider tick, causing request spam | Medium | Debounce the budget-change watcher before calling the API (e.g. ~250ms) |

## Open Questions

None outstanding — ranking algorithm, budget range, lead-time source, and
persistence approach were all confirmed with the user before this plan was
written.
