<template>
  <Teleport to="body">
    <Transition name="modal">
      <div v-if="isOpen && backlogItem" class="modal-overlay" @click="close">
        <div class="modal-container" @click.stop>
          <div class="modal-header">
            <h3 class="modal-title">{{ mode === 'create' ? 'Create Purchase Order' : 'Purchase Order Details' }}</h3>
            <button class="close-button" @click="close">
              <svg width="20" height="20" viewBox="0 0 20 20" fill="none">
                <path d="M15 5L5 15M5 5L15 15" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>
              </svg>
            </button>
          </div>

          <div class="modal-body">
            <div class="po-item-summary">
              <div class="po-item-name">{{ translateProductName(backlogItem.item_name) }}</div>
              <div class="po-item-sku">SKU: {{ backlogItem.item_sku }}</div>
            </div>

            <!-- Create Mode -->
            <form v-if="mode === 'create'" class="po-form" @submit.prevent="submitPurchaseOrder">
              <div class="form-row">
                <label class="form-label" for="po-supplier">Supplier Name</label>
                <input
                  id="po-supplier"
                  v-model="supplierName"
                  type="text"
                  class="form-input"
                  placeholder="e.g. Acme Components Inc."
                  required
                />
              </div>

              <div class="form-grid">
                <div class="form-row">
                  <label class="form-label" for="po-quantity">Quantity</label>
                  <input
                    id="po-quantity"
                    v-model.number="quantity"
                    type="number"
                    min="1"
                    step="1"
                    class="form-input"
                    required
                  />
                </div>

                <div class="form-row">
                  <label class="form-label" for="po-unit-cost">Unit Cost</label>
                  <input
                    id="po-unit-cost"
                    v-model.number="unitCost"
                    type="number"
                    min="0.01"
                    step="0.01"
                    class="form-input"
                    required
                  />
                </div>
              </div>

              <div class="form-row">
                <label class="form-label" for="po-delivery-date">Expected Delivery Date</label>
                <input
                  id="po-delivery-date"
                  v-model="expectedDeliveryDate"
                  type="date"
                  class="form-input"
                  required
                />
              </div>

              <div class="form-row">
                <label class="form-label" for="po-notes">Notes (optional)</label>
                <textarea
                  id="po-notes"
                  v-model="notes"
                  class="form-textarea"
                  rows="3"
                  placeholder="Additional details for this order..."
                ></textarea>
              </div>

              <div class="form-total" v-if="quantity && unitCost">
                <span class="form-total-label">Estimated Total</span>
                <span class="form-total-value">{{ formatUSD(quantity * unitCost) }}</span>
              </div>

              <div v-if="createError" class="form-error">{{ createError }}</div>
            </form>

            <!-- View Mode -->
            <div v-else class="po-view">
              <div v-if="viewLoading" class="po-status-message">Loading purchase order...</div>
              <div v-else-if="viewError" class="po-status-message error">{{ viewError }}</div>
              <div v-else-if="purchaseOrder" class="info-grid">
                <div class="info-item">
                  <div class="info-label">Supplier</div>
                  <div class="info-value">{{ purchaseOrder.supplier_name }}</div>
                </div>

                <div class="info-item">
                  <div class="info-label">Status</div>
                  <div class="info-value">
                    <span class="badge" :class="statusBadgeClass(purchaseOrder.status)">{{ purchaseOrder.status }}</span>
                  </div>
                </div>

                <div class="info-item">
                  <div class="info-label">Quantity</div>
                  <div class="info-value">{{ purchaseOrder.quantity }} units</div>
                </div>

                <div class="info-item">
                  <div class="info-label">Unit Cost</div>
                  <div class="info-value">{{ formatUSD(purchaseOrder.unit_cost) }}</div>
                </div>

                <div class="info-item">
                  <div class="info-label">Total Cost</div>
                  <div class="info-value">{{ formatUSD(purchaseOrder.quantity * purchaseOrder.unit_cost) }}</div>
                </div>

                <div class="info-item">
                  <div class="info-label">Expected Delivery</div>
                  <div class="info-value">{{ formatDate(purchaseOrder.expected_delivery_date) }}</div>
                </div>

                <div class="info-item">
                  <div class="info-label">Created</div>
                  <div class="info-value">{{ formatDate(purchaseOrder.created_date) }}</div>
                </div>

                <div class="info-item" v-if="purchaseOrder.notes">
                  <div class="info-label">Notes</div>
                  <div class="info-value">{{ purchaseOrder.notes }}</div>
                </div>
              </div>
            </div>
          </div>

          <div class="modal-footer">
            <button class="btn-secondary" @click="close">{{ mode === 'create' ? 'Cancel' : 'Close' }}</button>
            <button
              v-if="mode === 'create'"
              class="btn-primary"
              :disabled="submitting"
              @click="submitPurchaseOrder"
            >
              {{ submitting ? 'Creating...' : 'Create Purchase Order' }}
            </button>
          </div>
        </div>
      </div>
    </Transition>
  </Teleport>
</template>

<script setup>
import { ref, watch } from 'vue'
import { api } from '../api'
import { useI18n } from '../composables/useI18n'

const { translateProductName } = useI18n()

const props = defineProps({
  isOpen: {
    type: Boolean,
    default: false
  },
  backlogItem: {
    type: Object,
    default: null
  },
  mode: {
    type: String,
    default: 'create'
  }
})

const emit = defineEmits(['close', 'po-created'])

// Create mode state
const supplierName = ref('')
const quantity = ref(1)
const unitCost = ref(null)
const expectedDeliveryDate = ref('')
const notes = ref('')
const submitting = ref(false)
const createError = ref(null)

// View mode state
const purchaseOrder = ref(null)
const viewLoading = ref(false)
const viewError = ref(null)

const resetForm = () => {
  supplierName.value = ''
  quantity.value = props.backlogItem
    ? Math.max(props.backlogItem.quantity_needed - props.backlogItem.quantity_available, 1)
    : 1
  unitCost.value = null
  expectedDeliveryDate.value = ''
  notes.value = ''
  createError.value = null
  submitting.value = false
}

const loadPurchaseOrder = async () => {
  if (!props.backlogItem) return
  viewLoading.value = true
  viewError.value = null
  purchaseOrder.value = null
  try {
    purchaseOrder.value = await api.getPurchaseOrderByBacklogItem(props.backlogItem.id)
  } catch (err) {
    viewError.value = err.response?.status === 404
      ? 'No purchase order found for this item.'
      : 'Failed to load purchase order.'
    console.error(err)
  } finally {
    viewLoading.value = false
  }
}

const submitPurchaseOrder = async () => {
  if (submitting.value || !props.backlogItem) return
  createError.value = null
  submitting.value = true
  try {
    const payload = {
      backlog_item_id: props.backlogItem.id,
      supplier_name: supplierName.value,
      quantity: Number(quantity.value),
      unit_cost: Number(unitCost.value),
      expected_delivery_date: expectedDeliveryDate.value,
      notes: notes.value || undefined
    }
    const created = await api.createPurchaseOrder(payload)
    emit('po-created', created)
  } catch (err) {
    createError.value = err.response?.data?.detail || 'Failed to create purchase order. Please try again.'
    console.error(err)
  } finally {
    submitting.value = false
  }
}

const close = () => {
  emit('close')
}

const statusBadgeClass = (status) => {
  const normalized = (status || '').toLowerCase()
  if (normalized === 'pending') return 'warning'
  if (normalized === 'delivered' || normalized === 'completed') return 'success'
  return 'default'
}

const formatUSD = (amount) => {
  if (amount === null || amount === undefined || isNaN(amount)) return '$0.00'
  return `$${Number(amount).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
}

const formatDate = (dateString) => {
  if (!dateString) return 'N/A'
  const date = new Date(dateString)
  if (isNaN(date.getTime())) return 'N/A'
  return date.toLocaleDateString('en-US', {
    year: 'numeric',
    month: 'long',
    day: 'numeric'
  })
}

// Reset/load state whenever the modal is opened (or its mode/item changes while open)
watch(
  () => [props.isOpen, props.mode, props.backlogItem?.id],
  ([isOpen, mode]) => {
    if (!isOpen) return
    if (mode === 'view') {
      loadPurchaseOrder()
    } else {
      resetForm()
    }
  },
  { immediate: true }
)
</script>

<style scoped>
.modal-overlay {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: rgba(0, 0, 0, 0.5);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 2000;
  padding: 1rem;
}

.modal-container {
  background: white;
  border-radius: 12px;
  box-shadow: 0 20px 50px rgba(0, 0, 0, 0.15);
  max-width: 600px;
  width: 100%;
  max-height: 90vh;
  overflow: hidden;
  display: flex;
  flex-direction: column;
}

.modal-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 1.5rem;
  border-bottom: 1px solid #e2e8f0;
}

.modal-title {
  font-size: 1.25rem;
  font-weight: 700;
  color: #0f172a;
  letter-spacing: -0.025em;
}

.close-button {
  background: none;
  border: none;
  color: #64748b;
  cursor: pointer;
  padding: 0.5rem;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 6px;
  transition: all 0.15s ease;
}

.close-button:hover {
  background: #f1f5f9;
  color: #0f172a;
}

.modal-body {
  flex: 1;
  overflow-y: auto;
  padding: 2rem;
}

.po-item-summary {
  padding-bottom: 1.5rem;
  border-bottom: 1px solid #e2e8f0;
  margin-bottom: 1.5rem;
}

.po-item-name {
  font-size: 1.25rem;
  font-weight: 700;
  color: #0f172a;
  margin-bottom: 0.375rem;
}

.po-item-sku {
  font-size: 0.875rem;
  color: #64748b;
  font-family: 'Monaco', 'Courier New', monospace;
}

.po-form {
  display: flex;
  flex-direction: column;
  gap: 1.25rem;
}

.form-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 1.25rem;
}

.form-row {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}

.form-label {
  font-size: 0.813rem;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  color: #64748b;
}

.form-input,
.form-textarea {
  padding: 0.625rem 0.75rem;
  border: 1px solid #e2e8f0;
  border-radius: 8px;
  font-size: 0.938rem;
  color: #0f172a;
  font-family: inherit;
  transition: border-color 0.15s ease;
}

.form-input:focus,
.form-textarea:focus {
  outline: none;
  border-color: #3b82f6;
}

.form-textarea {
  resize: vertical;
}

.form-total {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 1rem 1.25rem;
  background: #f8fafc;
  border-radius: 8px;
  border: 1px solid #e2e8f0;
}

.form-total-label {
  font-size: 0.813rem;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  color: #64748b;
}

.form-total-value {
  font-size: 1.25rem;
  font-weight: 700;
  color: #0f172a;
}

.form-error {
  padding: 0.75rem 1rem;
  background: #fef2f2;
  border: 1px solid #fecaca;
  border-radius: 8px;
  color: #991b1b;
  font-size: 0.875rem;
  font-weight: 500;
}

.po-status-message {
  padding: 2rem;
  text-align: center;
  color: #64748b;
  font-size: 0.938rem;
}

.po-status-message.error {
  color: #991b1b;
}

.info-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
  gap: 1.5rem;
}

.info-item {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}

.info-label {
  font-size: 0.813rem;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  color: #64748b;
}

.info-value {
  font-size: 0.938rem;
  color: #0f172a;
  font-weight: 500;
}

.badge {
  display: inline-block;
  padding: 0.25rem 0.625rem;
  border-radius: 6px;
  font-size: 0.75rem;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.025em;
}

.badge.warning {
  background: #fed7aa;
  color: #92400e;
}

.badge.success {
  background: #bbf7d0;
  color: #166534;
}

.badge.default {
  background: #e2e8f0;
  color: #334155;
}

.modal-footer {
  padding: 1.5rem;
  border-top: 1px solid #e2e8f0;
  display: flex;
  justify-content: flex-end;
  gap: 0.75rem;
}

.btn-secondary {
  padding: 0.625rem 1.25rem;
  background: #f1f5f9;
  border: 1px solid #e2e8f0;
  border-radius: 8px;
  font-weight: 500;
  font-size: 0.875rem;
  color: #334155;
  cursor: pointer;
  transition: all 0.15s ease;
  font-family: inherit;
}

.btn-secondary:hover {
  background: #e2e8f0;
  border-color: #cbd5e1;
}

.btn-primary {
  padding: 0.625rem 1.25rem;
  background: #3b82f6;
  border: 1px solid #3b82f6;
  border-radius: 8px;
  font-weight: 600;
  font-size: 0.875rem;
  color: white;
  cursor: pointer;
  transition: all 0.15s ease;
  font-family: inherit;
}

.btn-primary:hover:not(:disabled) {
  background: #2563eb;
  border-color: #2563eb;
}

.btn-primary:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

/* Modal transition animations */
.modal-enter-active,
.modal-leave-active {
  transition: opacity 0.2s ease;
}

.modal-enter-from,
.modal-leave-to {
  opacity: 0;
}

.modal-enter-active .modal-container,
.modal-leave-active .modal-container {
  transition: transform 0.2s ease;
}

.modal-enter-from .modal-container,
.modal-leave-to .modal-container {
  transform: scale(0.95);
}
</style>
