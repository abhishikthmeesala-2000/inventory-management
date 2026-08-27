<script setup>
import { ref, computed, onMounted, watch, onBeforeUnmount } from 'vue'
import { api } from '../api'

// Raw API data in refs; derived/display values in computed (project convention).
const maxBudget = ref(0)
const budget = ref(0)
const recommendedItems = ref([])
const budgetUsed = ref(0)

const loading = ref(true)
const error = ref(null)

const placingOrder = ref(false)
const orderError = ref(null)
const placedOrder = ref(null)

// Debounce handle for the budget watcher (no @vueuse/core dependency in this project).
let debounceHandle = null

const fetchRecommendations = async (value) => {
  loading.value = true
  error.value = null
  try {
    const response = await api.getRestockRecommendations(value)
    recommendedItems.value = response.recommended_items || []
    budgetUsed.value = response.budget_used || 0
  } catch (err) {
    error.value = 'Failed to load restock recommendations'
    console.error(err)
  } finally {
    loading.value = false
  }
}

const initBudgetRange = async () => {
  loading.value = true
  error.value = null
  try {
    // budget=0 returns no recommendations but a real max_budget to size the slider.
    const response = await api.getRestockRecommendations(0)
    maxBudget.value = response.max_budget || 0
    recommendedItems.value = response.recommended_items || []
    budgetUsed.value = response.budget_used || 0
  } catch (err) {
    error.value = 'Failed to load restock recommendations'
    console.error(err)
  } finally {
    loading.value = false
  }
}

watch(budget, (newValue) => {
  // Clear any pending place-order confirmation/error once the budget changes again.
  placedOrder.value = null
  orderError.value = null

  if (debounceHandle) clearTimeout(debounceHandle)
  debounceHandle = setTimeout(() => {
    fetchRecommendations(newValue)
  }, 250)
})

onBeforeUnmount(() => {
  if (debounceHandle) clearTimeout(debounceHandle)
})

const totalItems = computed(() => recommendedItems.value.length)

const remainingBudget = computed(() => budget.value - budgetUsed.value)

const canPlaceOrder = computed(() => recommendedItems.value.length > 0 && !placingOrder.value)

const getTrendClass = (trend) => {
  if (trend === 'increasing' || trend === 'decreasing' || trend === 'stable') return trend
  return 'info'
}

const formatCurrency = (value) => {
  return `$${(value || 0).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
}

const formatDate = (value) => {
  const date = new Date(value)
  if (isNaN(date.getTime())) return value
  return date.toLocaleDateString(undefined, { year: 'numeric', month: 'short', day: 'numeric' })
}

const placeOrder = async () => {
  if (!canPlaceOrder.value) return

  placingOrder.value = true
  orderError.value = null
  placedOrder.value = null

  try {
    // Server only accepts/needs sku + quantity per item; it looks up price/name/lead-time itself.
    const items = recommendedItems.value.map(item => ({
      sku: item.sku,
      quantity: item.quantity
    }))
    const order = await api.placeRestockOrder(items)
    placedOrder.value = order
  } catch (err) {
    orderError.value = err.response?.data?.detail || 'Failed to place restock order'
    console.error(err)
  } finally {
    placingOrder.value = false
  }
}

onMounted(() => initBudgetRange())
</script>

<template>
  <div class="restocking">
    <div class="page-header">
      <h2>Restocking</h2>
      <p>Budget-based restock recommendations and order placement</p>
    </div>

    <div class="card budget-card">
      <div class="card-header">
        <h3 class="card-title">Restock Budget</h3>
        <div class="budget-amount">{{ formatCurrency(budget) }}</div>
      </div>
      <input
        v-model.number="budget"
        type="range"
        class="budget-slider"
        min="0"
        :max="maxBudget"
        step="100"
      />
      <div class="budget-range-labels">
        <span>$0</span>
        <span>{{ formatCurrency(maxBudget) }}</span>
      </div>
      <div class="budget-stats">
        <div class="budget-stat">
          <span class="stat-label">Budget Used</span>
          <span class="stat-value">{{ formatCurrency(budgetUsed) }}</span>
        </div>
        <div class="budget-stat">
          <span class="stat-label">Remaining</span>
          <span class="stat-value">{{ formatCurrency(remainingBudget) }}</span>
        </div>
        <div class="budget-stat">
          <span class="stat-label">Items Recommended</span>
          <span class="stat-value">{{ totalItems }}</span>
        </div>
      </div>
    </div>

    <div v-if="placedOrder" class="banner success-banner">
      <div class="banner-title">Order placed successfully</div>
      <div class="banner-body">
        Order <strong>{{ placedOrder.order_number }}</strong> placed for
        {{ formatCurrency(placedOrder.total_cost) }}. Expected delivery on
        <strong>{{ formatDate(placedOrder.expected_delivery_date) }}</strong>.
      </div>
    </div>

    <div v-if="orderError" class="banner error-banner">
      <div class="banner-title">Unable to place order</div>
      <div class="banner-body">{{ orderError }}</div>
    </div>

    <div class="card">
      <div class="card-header">
        <h3 class="card-title">Recommended Items ({{ totalItems }})</h3>
        <button
          class="btn-primary"
          :disabled="!canPlaceOrder"
          @click="placeOrder"
        >
          {{ placingOrder ? 'Placing Order...' : 'Place Order' }}
        </button>
      </div>

      <div v-if="loading" class="loading">Loading recommendations...</div>
      <div v-else-if="error" class="error">{{ error }}</div>
      <div v-else-if="recommendedItems.length === 0" class="empty-state">
        <p>No recommended items at this budget.</p>
        <p class="empty-hint">Increase the budget slider to see restock recommendations.</p>
      </div>
      <div v-else class="table-container">
        <table>
          <thead>
            <tr>
              <th>SKU</th>
              <th>Item Name</th>
              <th>Trend</th>
              <th>Quantity</th>
              <th>Unit Cost</th>
              <th>Line Total</th>
              <th>Lead Time</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="item in recommendedItems" :key="item.sku">
              <td><strong>{{ item.sku }}</strong></td>
              <td>{{ item.name }}</td>
              <td>
                <span :class="['badge', getTrendClass(item.trend)]">{{ item.trend }}</span>
              </td>
              <td>{{ item.quantity }}</td>
              <td>{{ formatCurrency(item.unit_cost) }}</td>
              <td><strong>{{ formatCurrency(item.line_total) }}</strong></td>
              <td>{{ item.lead_time_days }} days</td>
            </tr>
          </tbody>
          <tfoot>
            <tr>
              <td colspan="5" class="total-label">Total</td>
              <td class="total-value"><strong>{{ formatCurrency(budgetUsed) }}</strong></td>
              <td></td>
            </tr>
          </tfoot>
        </table>
      </div>
    </div>
  </div>
</template>

<style scoped>
.page-header {
  margin-bottom: 1.5rem;
}

.page-header h2 {
  margin-bottom: 0.25rem;
}

.page-header p {
  color: #64748b;
  font-size: 0.875rem;
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 1.5rem;
  padding-bottom: 1rem;
  margin-bottom: 0;
}

.card-title {
  font-size: 1rem;
  font-weight: 600;
  color: #0f172a;
  margin: 0;
}

.budget-amount {
  font-size: 1.25rem;
  font-weight: 700;
  color: #0f172a;
}

.budget-slider {
  width: 100%;
  height: 6px;
  border-radius: 3px;
  background: #e2e8f0;
  appearance: none;
  outline: none;
  cursor: pointer;
  margin: 0.5rem 0;
}

.budget-slider::-webkit-slider-thumb {
  appearance: none;
  width: 18px;
  height: 18px;
  border-radius: 50%;
  background: #3b82f6;
  cursor: pointer;
  border: 2px solid white;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.2);
}

.budget-slider::-moz-range-thumb {
  width: 18px;
  height: 18px;
  border-radius: 50%;
  background: #3b82f6;
  cursor: pointer;
  border: 2px solid white;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.2);
}

.budget-range-labels {
  display: flex;
  justify-content: space-between;
  font-size: 0.75rem;
  color: #94a3b8;
  margin-bottom: 1rem;
}

.budget-stats {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 1rem;
  padding-top: 1rem;
  border-top: 1px solid #e2e8f0;
}

.budget-stat {
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
}

.stat-label {
  font-size: 0.75rem;
  color: #64748b;
  text-transform: uppercase;
  letter-spacing: 0.025em;
}

.stat-value {
  font-size: 1rem;
  font-weight: 600;
  color: #0f172a;
}

.btn-primary {
  padding: 0.5rem 1.25rem;
  border: none;
  border-radius: 6px;
  font-size: 0.875rem;
  font-weight: 600;
  color: white;
  background: #3b82f6;
  cursor: pointer;
  transition: all 0.2s ease;
  white-space: nowrap;
}

.btn-primary:hover:not(:disabled) {
  background: #2563eb;
}

.btn-primary:disabled {
  background: #cbd5e1;
  cursor: not-allowed;
}

.banner {
  border-radius: 10px;
  padding: 1rem 1.25rem;
  margin-bottom: 1.25rem;
  border: 1px solid;
}

.success-banner {
  background: #d1fae5;
  border-color: #a7f3d0;
  color: #065f46;
}

.error-banner {
  background: #fecaca;
  border-color: #fca5a5;
  color: #991b1b;
}

.banner-title {
  font-weight: 700;
  font-size: 0.875rem;
  margin-bottom: 0.25rem;
}

.banner-body {
  font-size: 0.875rem;
}

.loading,
.error {
  padding: 2rem;
  text-align: center;
  color: #64748b;
}

.error {
  color: #ef4444;
}

.empty-state {
  padding: 3rem 1rem;
  text-align: center;
  color: #64748b;
}

.empty-hint {
  font-size: 0.813rem;
  color: #94a3b8;
  margin-top: 0.25rem;
}

.total-label {
  text-align: right;
  font-weight: 600;
  color: #475569;
}

.total-value {
  color: #0f172a;
}

tfoot td {
  border-top: 2px solid #e2e8f0;
  padding: 0.625rem 0.75rem;
}
</style>
