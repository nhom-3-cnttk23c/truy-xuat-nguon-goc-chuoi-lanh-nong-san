import { useEffect, useState, type FormEvent } from 'react'
import { hasPermission, type SessionUser, type Product, type ProductPayload, type ProductUnit } from '../types'
import { CsvImportPanel } from './CsvImportPanel'
import { TaskLink } from './TaskLink'
import { EditDialog } from './EditDialog'
import { getProducts, createProduct, updateProduct } from '../services/api'

const PRODUCT_UNITS: { value: ProductUnit; label: string }[] = [
  { value: 'kg', label: 'Kilôgam (kg)' },
  { value: 'tấn', label: 'Tấn' },
  { value: 'thùng', label: 'Thùng' },
]

interface ProductManagerProps {
  user: SessionUser
}

export function ProductManager({ user }: ProductManagerProps) {
  const params = new URLSearchParams(window.location.search)
  const task = params.get('task')
  const editId = params.get('id')
  const canWriteProducts = hasPermission(user.role, 'products:write')
  const [refresh, setRefresh] = useState(0)
  const [products, setProducts] = useState<Product[]>([])
  const [loading, setLoading] = useState(true)
  const [loadError, setLoadError] = useState<string | null>(null)
  const [formOpen, setFormOpen] = useState(task === 'create')
  const [editingProduct, setEditingProduct] = useState<Product | null>(null)
  const [name, setName] = useState('')
  const [unit, setUnit] = useState<ProductUnit>('kg')
  const [description, setDescription] = useState('')
  const [price, setPrice] = useState('0')
  const [quantity, setQuantity] = useState('0')
  const [saving, setSaving] = useState(false)
  const [feedback, setFeedback] = useState<{
    type: 'success' | 'error'
    message: string
  } | null>(null)

  useEffect(() => {
    let active = true
    getProducts()
      .then((data) => {
        if (active) {
          setProducts(data); setLoadError(null)
          if (task === 'edit') {
            const product = data.find(item => item.id === editId)
            if (product) {
              setEditingProduct(product); setName(product.name); setUnit(product.unit)
              setDescription(product.description ?? ''); setPrice(String(product.price)); setQuantity(String(product.quantity ?? 0)); setFormOpen(true)
            } else setLoadError('Không tìm thấy sản phẩm cần sửa. Quay lại danh mục để chọn sản phẩm khác.')
          }
        }
      })
      .catch((error: unknown) => {
        if (active) {
          setLoadError(
            error instanceof Error
              ? error.message
              : 'Không thể tải danh mục sản phẩm'
          )
        }
      })
      .finally(() => {
        if (active) setLoading(false)
      })
    return () => {
      active = false
    }
  }, [refresh, task, editId])

  const resetForm = () => {
    setEditingProduct(null)
    setName('')
    setUnit('kg')
    setDescription('')
    setPrice('0')
    setQuantity('0')
  }

  const openForm = (product: Product | null) => {
    resetForm()
    setFeedback(null)
    if (product) {
      setEditingProduct(product); setName(product.name); setUnit(product.unit)
      setDescription(product.description ?? ''); setPrice(String(product.price)); setQuantity(String(product.quantity ?? 0))
    }
    setFormOpen(true)
  }

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    if (saving) return

    const trimmedName = name.trim()
    if (!trimmedName) {
      setFeedback({ type: 'error', message: 'Tên sản phẩm không được để trống.' })
      return
    }

    setSaving(true)
    setFeedback(null)
    const payload: ProductPayload = {
      name: trimmedName,
      unit,
      description: description.trim() || undefined,
      price: Number(price),
      quantity: quantity.trim() ? Number(quantity) : 0,
    }

    try {
      const saved = editingProduct
        ? await updateProduct(editingProduct.id, payload)
        : await createProduct(payload)
      setProducts((current) => {
        const next = editingProduct
          ? current.map((product) =>
              product.id === saved.id ? saved : product
            )
          : [...current, saved]
        return next.sort((left, right) => left.name.localeCompare(right.name))
      })
      setFeedback({
        type: 'success',
        message: editingProduct
          ? `Đã cập nhật sản phẩm "${saved.name}".`
          : `Đã thêm sản phẩm "${saved.name}" vào danh mục dùng chung.`,
      })
      resetForm()
      setFormOpen(false)
    } catch (error) {
      setFeedback({
        type: 'error',
        message:
          error instanceof Error ? error.message : 'Không thể lưu sản phẩm',
      })
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="info-stack">
      {task && <a className="ds-button ds-button-secondary" href="/products">← Danh mục sản phẩm</a>}
      {task === 'csv' && feedback && <p role={feedback.type === 'error' ? 'alert' : 'status'} className={`alert-box ${feedback.type === 'error' ? 'alert-error' : 'alert-success'}`}>{feedback.message}</p>}
      {task && loadError && <p role="alert">{loadError}</p>}
      {task && loading && <p aria-busy="true">Đang tải danh mục…</p>}
      {task === 'csv' && user.role === 'system_admin' && <CsvImportPanel onImported={() => setRefresh(value => value + 1)} />}
      {task && !canWriteProducts && <p role="status">Tài khoản này không có quyền thay đổi danh mục.</p>}
      {canWriteProducts && formOpen && (
        <EditDialog title={editingProduct ? 'Sửa nông sản' : 'Thêm nông sản'} busy={saving} onClose={() => setFormOpen(false)}>
        <section
          className="panel-box panel-card"
          aria-labelledby="product-form-title"
        >
          <div className="panel-head">
            <h2 id="product-form-title">
              {editingProduct ? editingProduct.name : 'Thông tin nông sản'}
            </h2>
          </div>
          {feedback?.type === 'error' && <p role="alert" className="alert-box alert-error">{feedback.message}</p>}
          <form onSubmit={handleSubmit} className="form-stack">
            <div className="form-row-2">
              <div className="form-field">
                <label htmlFor="product-name">
                  Tên nông sản <span className="required-mark">*</span>
                </label>
                <input
                  id="product-name"
                  type="text"
                  required
                  maxLength={200}
                  value={name}
                  onChange={(event) => setName(event.target.value)}
                  placeholder="Ví dụ: Xoài cát Hòa Lộc"
                />
              </div>
              <div className="form-field">
                <label htmlFor="product-unit">
                  Đơn vị tính <span className="required-mark">*</span>
                </label>
                <select
                  id="product-unit"
                  required
                  value={unit}
                  onChange={(event) => setUnit(event.target.value as ProductUnit)}
                >
                  {PRODUCT_UNITS.map((option) => (
                    <option key={option.value} value={option.value}>
                      {option.label}
                    </option>
                  ))}
                </select>
              </div>
            </div>

            <div className="form-field">
              <label htmlFor="product-description">Mô tả</label>
              <input
                id="product-description"
                type="text"
                value={description}
                onChange={(event) => setDescription(event.target.value)}
                placeholder="Ví dụ: Xoài tươi, vỏ vàng khi chín; tính theo kg."
              />
            </div>

            <div className="form-row-2">
              <div className="form-field">
                <label htmlFor="product-price">Giá tham khảo (đồng / đơn vị)</label>
                <input
                  id="product-price"
                  type="number"
                  min="0"
                  step="0.01"
                  value={price}
                  onChange={(event) => setPrice(event.target.value)}
                />
              </div>
              <div className="form-field">
                <label htmlFor="product-quantity">Số lượng mặc định</label>
                <input
                  id="product-quantity"
                  type="number"
                  min="0"
                  step="1"
                  value={quantity}
                  onChange={(event) => setQuantity(event.target.value)}
                />
              </div>
            </div>

            <div className="action-row">
              <button
                type="submit"
                className="ds-button ds-button-brand ds-button-sm"
                disabled={saving}
              >
                {saving
                  ? 'Đang lưu...'
                  : editingProduct
                    ? 'Lưu'
                    : 'Thêm'}
              </button>
              <button type="button" className="ds-button ds-button-secondary" disabled={saving} onClick={() => setFormOpen(false)}>Hủy</button>
            </div>
          </form>
        </section>
        </EditDialog>
      )}

      {task !== 'csv' && <section
        className="data-table-wrapper panel-card"
        aria-labelledby="products-table-title"
      >
        <div className="data-table-header">
          <div>
            <h2 id="products-table-title" className="section-title">
              Nông sản ({products.length})
            </h2>
            <p className="panel-sub">
              Danh mục nông sản dùng chung. Chọn tên rõ ràng và đơn vị cân, đếm phù hợp.
            </p>
          </div>
          {canWriteProducts && (
            <div className="action-row"><button type="button" className="ds-button ds-button-brand" onClick={() => openForm(null)}>Thêm nông sản</button>{user.role === 'system_admin' && <TaskLink href="/products?task=csv" secondary>Nhập CSV</TaskLink>}</div>
          )}
        </div>

        {feedback && (
          <div
            className={`alert-box ${feedback.type === 'success' ? 'alert-success' : 'alert-error'} table-alert`}
            role="status"
            aria-live="polite"
          >
            {feedback.message}
          </div>
        )}
        {loadError && (
          <div className="alert-box alert-error table-alert" role="alert">
            {loadError}
          </div>
        )}

        <div className="table-scroll">
          <table className="data-table product-table">
            <thead>
              <tr>
                <th scope="col">Nông sản</th>
                <th scope="col">Đơn vị</th>
                <th scope="col">Mô tả</th>
                <th scope="col">Giá tham khảo</th>
                <th scope="col">Số lượng</th>
                {canWriteProducts && <th scope="col">Thao tác</th>}
              </tr>
            </thead>
            <tbody>
              {loading ? (
                <tr>
                  <td colSpan={canWriteProducts ? 6 : 5}>
                    Đang tải danh mục...
                  </td>
                </tr>
              ) : products.length === 0 ? (
                <tr>
                  <td colSpan={canWriteProducts ? 6 : 5}>
                    Chưa có sản phẩm trong danh mục.
                  </td>
                </tr>
              ) : (
                products.map((product) => (
                  <tr key={product.id}>
                    <th scope="row" className="cell-strong">
                      {product.name}
                    </th>
                    <td>{product.unit}</td>
                    <td>{product.description || '—'}</td>
                    <td>{product.price > 0 ? `${product.price.toLocaleString('vi-VN')} đ / ${product.unit}` : 'Chưa nhập'}</td>
                    <td>{product.quantity ?? 0}</td>
                    {canWriteProducts && (
                      <td>
                        <button type="button" className="ds-button ds-button-secondary" onClick={() => openForm(product)}>Sửa<span className="sr-only"> {product.name}</span></button>
                      </td>
                    )}
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </section>}
    </div>
  )
}
