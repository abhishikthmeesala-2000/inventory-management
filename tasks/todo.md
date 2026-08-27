# Todo: Restocking Tab

See `tasks/plan.md` for architecture decisions and rationale.

---

## Phase 1: Backend foundation

### Task 1: Data model — lead time field + RestockOrder models + in-memory store

**Description:** Add a `lead_time_days` field to every item in
`server/data/inventory.json` (vary by category, roughly 5-21 days). Add
`RestockOrderItem`, `RestockOrder`, and `CreateRestockOrderRequest` Pydantic
models to `server/main.py`. Add a `restock_orders = []` in-memory list to
`server/mock_data.py`, loaded the same way `purchase_orders` is (empty list
at startup, populated only at runtime).

**Acceptance criteria:**
- [x] Every record in `inventory.json` has an integer `lead_time_days` field
- [x] `RestockOrder` model includes: `id`, `order_number`, `items` (list of
      `{sku, name, quantity, unit_cost, line_total}`), `total_cost`,
      `status`, `created_date`, `expected_delivery_date`
- [x] `restock_orders` list exists in `mock_data.py` and is importable from
      `main.py`

**Verification:**
- [x] `python3 -c "import json; json.load(open('server/data/inventory.json'))"` succeeds (valid JSON)
- [x] Backend starts cleanly: `cd server && uv run python main.py`
- [x] `cd server && uv run pytest ../tests/backend/test_restocking.py -v -c ../tests/pytest.ini` — 3/3 pass
- [x] Full suite regression check: 43/43 backend tests pass

**Dependencies:** None

**Files likely touched:**
- `server/data/inventory.json`
- `server/main.py`
- `server/mock_data.py`

**Estimated scope:** Small (3 files, mostly additive)

---

### Task 2: Recommendation endpoint

**Description:** Add `GET /api/restocking/recommendations?budget=<float>` to
`server/main.py`. Join `demand_forecasts` to `inventory_items` by SKU
(`item_sku` ↔ `sku`). Compute `shortfall_qty = max(forecasted_demand -
current_demand, 0)` and `shortfall_cost = shortfall_qty * unit_cost` per
item. Sort descending by `shortfall_cost`. Compute `max_budget` = sum of all
`shortfall_cost`. Greedily select items into `recommended_items` while
`budget` param is respected (skip-and-continue on items that don't fit, per
`tasks/plan.md`). Return `{ max_budget, budget_used, recommended_items }`,
where each recommended item includes `sku`, `name`, `trend`, `quantity`
(the shortfall qty), `unit_cost`, `line_total`, and `lead_time_days`
(pulled from the matching inventory record).

**Acceptance criteria:**
- [x] `budget=0` (or omitted) returns `recommended_items: []` and a correct
      non-zero `max_budget`
- [x] A budget large enough to cover everything returns all forecast items
      with positive shortfall
- [x] A mid-size budget returns a subset whose summed `line_total` is
      `<= budget`, and no single returned item's cost exceeds `budget`
- [x] Items with zero or negative shortfall (forecast ≤ current demand) are
      never recommended
- [x] A forecast SKU with no matching inventory record is skipped, not a
      500 error

**Verification:**
- [x] New tests in `tests/backend/test_restocking.py` (per `backend-api-test`
      skill) cover: empty budget, full-coverage budget, partial budget,
      zero-shortfall exclusion, unmatched-SKU handling
- [x] `cd server && uv run pytest ../tests/backend/test_restocking.py -v -c ../tests/pytest.ini` — 9/9 pass
- [x] Manual check via curl against the running server

**Note (data fix, approved by user):** `server/data/demand_forecasts.json`
had 8 of 9 `item_sku` values referencing SKUs that don't exist in
`inventory.json` at all (independently-generated fixtures, never
cross-referenced). Joining strictly by SKU as designed would have made the
feature recommend at most one item ever. Remapped those 8 records to real
inventory SKUs (keeping `current_demand`/`forecasted_demand`/`trend`
unchanged), which also required updating a hardcoded-SKU assertion in
`tests/backend/test_misc_endpoints.py::test_demand_forecast_has_new_items`.

**Dependencies:** Task 1

**Files likely touched:**
- `server/main.py`
- `tests/backend/test_restocking.py`

**Estimated scope:** Medium (endpoint logic + tests)

---

### Task 3: Submit / list restock-order endpoints

**Description:** Add `POST /api/restocking/orders` (body:
`CreateRestockOrderRequest` — a list of `{sku, quantity}` the user is
submitting) and `GET /api/restocking/orders` to `server/main.py`. On POST,
look up each SKU in `inventory_items` server-side to get `unit_cost`,
`name`, and `lead_time_days` — never trust client-sent prices. Compute
`total_cost`, set `expected_delivery_date` = today + `max(lead_time_days)`
across the order's items, assign an `id`/`order_number`, set
`status="Submitted"`, append to `restock_orders`, return the created order.
GET returns the full `restock_orders` list.

**Acceptance criteria:**
- [ ] POST with a valid item list returns 200 and the created order with
      server-computed totals (client-sent prices, if any, are ignored)
- [ ] POST with an unknown SKU returns a 400 (not a 500)
- [ ] `expected_delivery_date` equals `created_date` + the longest
      `lead_time_days` among the order's items
- [ ] GET returns every previously-submitted order for the life of the
      process, in submission order
- [ ] A server restart clears `restock_orders` back to empty (documents the
      existing in-memory constraint, doesn't fight it)

**Verification:**
- [ ] Tests in `tests/backend/test_restocking.py` cover: successful submit,
      unknown-SKU rejection, delivery-date computation, GET after POST
- [ ] `cd tests && uv run pytest backend/test_restocking.py -v` passes

**Dependencies:** Task 1, Task 2 (shares helper/model code)

**Files likely touched:**
- `server/main.py`
- `tests/backend/test_restocking.py`

**Estimated scope:** Medium (2 endpoints + validation + tests)

---

## Checkpoint: Backend complete
- [ ] `cd tests && uv run pytest backend/ -v` passes (full suite, not just new tests — no regressions)
- [ ] Manual smoke test via `http://localhost:8001/docs`: recommendations respect budget; submit → list round-trips
- [ ] Review with human before starting frontend work

---

## Phase 2: Restocking tab (frontend)

> Every task in this phase touches a `.vue` file (or the router/API client
> that feeds one) — per root `CLAUDE.md`, implementation MUST go through the
> **vue-expert** subagent, not be written directly.

### Task 4: API client methods + route + nav entry

**Description:** Add `getRestockRecommendations(budget)`, `placeRestockOrder(items)`,
and `getRestockOrders()` to `client/src/api.js`, following the existing
`URLSearchParams`/axios pattern. Add the route `{ path: '/restocking',
component: Restocking }` to `client/src/main.js`. Add a "Restocking" nav
link in `client/src/App.vue` alongside the existing tabs.

**Acceptance criteria:**
- [ ] `api.getRestockRecommendations(budget)` calls
      `GET /api/restocking/recommendations?budget=...`
- [ ] `api.placeRestockOrder(items)` calls `POST /api/restocking/orders`
- [ ] `api.getRestockOrders()` calls `GET /api/restocking/orders`
- [ ] `/restocking` route renders (even with a placeholder component) and a
      nav link to it appears in the top nav

**Verification:**
- [ ] `npm run build` succeeds with no errors
- [ ] Manual/Playwright: navigating to `http://localhost:3000/restocking` loads without console errors

**Dependencies:** Task 3 (needs real endpoints to call)

**Files likely touched:**
- `client/src/api.js`
- `client/src/main.js`
- `client/src/App.vue`
- `client/src/views/Restocking.vue` (stub)

**Estimated scope:** Small (4 files, mostly wiring)

---

### Task 5: Restocking.vue — budget slider + live recommendations

**Description:** Build out `client/src/views/Restocking.vue`: fetch
`max_budget` on mount (via a `budget=0` or dedicated initial call), render a
range-slider bound to a `budget` ref with that dynamic max, debounce
(~250ms) a watcher on `budget` that calls
`api.getRestockRecommendations(budget)` and populates a `recommendedItems`
ref, and render the recommendations as a table (name, sku, trend, quantity,
unit cost, line total, lead time days) with a running total matching
`budget_used`. Follow the project's slate/gray design system and existing
view conventions (raw data in refs, derived display in computed
properties).

**Acceptance criteria:**
- [ ] Slider range is `[0, max_budget]` from the API, not hardcoded
- [ ] Moving the slider updates the recommended items list (debounced, not
      one request per pixel of drag)
- [ ] Table shows every field listed above per recommended item, plus a
      budget-used vs. budget-selected summary
- [ ] Empty state (budget = 0, or budget too small for any item) is handled
      without layout breakage

**Verification:**
- [ ] Manual/Playwright check at `http://localhost:3000/restocking`:
      drag slider, confirm list updates and stays within budget
- [ ] No console errors/warnings during interaction

**Dependencies:** Task 4

**Files likely touched:**
- `client/src/views/Restocking.vue`

**Estimated scope:** Medium (one component, real interaction logic)

---

### Task 6: Restocking.vue — Place Order flow

**Description:** Add a "Place Order" button to `Restocking.vue` that calls
`api.placeRestockOrder(recommendedItems)`, disables itself while the request
is in flight, shows a success confirmation (e.g. order number + expected
delivery date) on success, and shows an inline error state on failure
without crashing the view. Disable the button when there are no recommended
items.

**Acceptance criteria:**
- [ ] Button is disabled when `recommendedItems` is empty or a request is
      already in flight
- [ ] Successful submit shows the returned order number and expected
      delivery date
- [ ] Failed submit shows a visible error message and leaves the page
      usable (no unhandled promise rejection)

**Verification:**
- [ ] Manual/Playwright: full flow — set budget, see recommendations, place
      order, see confirmation
- [ ] Manual: stop the backend, attempt to place an order, confirm the error
      state renders instead of a blank/broken page

**Dependencies:** Task 5

**Files likely touched:**
- `client/src/views/Restocking.vue`

**Estimated scope:** Small (same file as Task 5, one interaction path)

---

## Checkpoint: Restocking tab works end-to-end
- [ ] Manual/Playwright: moving the slider updates the list; Place Order succeeds and shows confirmation
- [ ] `npm run build` still succeeds
- [ ] Review with human before starting Orders integration

---

## Phase 3: Orders tab integration

### Task 7: "Submitted Orders" section in Orders.vue

**Description:** Add a new "Submitted Orders" section to
`client/src/views/Orders.vue` (below or alongside the existing sales-orders
table — visually distinct since these are restocking/purchase orders, not
customer sales orders). Fetch via `api.getRestockOrders()` on mount, render
order number, items summary, total cost, submitted date, and expected
delivery date / lead time. Follow the project's existing status-badge
pattern (green/blue/yellow/red) for order status.

**Acceptance criteria:**
- [ ] Section is clearly labeled "Submitted Orders" and visually separated
      from the existing customer-orders table
- [ ] Every restock order placed from the Restocking tab appears here after
      a page reload (proves it round-tripped through the backend, not just
      local state)
- [ ] Delivery lead time is displayed per order (e.g. "Expected in 14 days"
      or the computed date)
- [ ] Empty state (no restock orders yet) renders cleanly

**Verification:**
- [ ] Manual/Playwright: place an order on the Restocking tab, navigate to
      Orders, confirm it appears with correct lead time
- [ ] Reload the Orders page, confirm the order persists (backend-held,
      not lost) for the remainder of the backend process's life

**Dependencies:** Task 3 (endpoint), Task 6 (something to actually submit)

**Files likely touched:**
- `client/src/views/Orders.vue`

**Estimated scope:** Small-Medium (one section in an existing view)

---

## Checkpoint: Full feature complete
- [ ] Place a restocking order on the Restocking tab, confirm it appears in
      the Orders tab's Submitted Orders section with correct lead time
- [ ] `cd tests && uv run pytest backend/ -v` passes (no regressions)
- [ ] `npm run build` succeeds
- [ ] All acceptance criteria above met, ready for review
