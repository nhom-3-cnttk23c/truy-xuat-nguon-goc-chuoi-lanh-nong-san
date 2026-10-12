import { useEffect, useState } from 'react'
import { getLots, getProducts } from '../services/api'
import type { Lot, Product } from '../types'
import { lotStatusLabel } from '../types'
import { LotCreateForm } from './LotCreateForm'
import { TaskLink } from './TaskLink'

interface Props {
  canReadLots: boolean; canCreateLots: boolean; canReadEvents?: boolean
  canTransform?: boolean; organizationId?: string; onOpenLot: (id: string) => void
}

export function LotsPanel({ canReadLots, canCreateLots, canReadEvents = true, canTransform, organizationId, onOpenLot }: Props) {
  const task = new URLSearchParams(window.location.search).get('task')
  const [lots, setLots] = useState<Lot[]>([])
  const [products, setProducts] = useState<Product[]>([])
  const [loading, setLoading] = useState(canReadLots)
  const [loadingProducts, setLoadingProducts] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [query, setQuery] = useState('')
  const [productId, setProductId] = useState('')
  const [cursor, setCursor] = useState<string | undefined>()
  const [previousCursors, setPreviousCursors] = useState<Array<string | undefined>>([])
  const [nextCursor, setNextCursor] = useState<string | null>(null)
  const [refresh, setRefresh] = useState(0)
  const [selected, setSelected] = useState<Lot[]>([])

  useEffect(() => {
    let active = true
    getProducts().then(data => { if (active) setProducts(data) })
      .catch((err: unknown) => { if (active) setError(err instanceof Error ? err.message : 'Không tải được sản phẩm.') })
      .finally(() => { if (active) setLoadingProducts(false) })
    return () => { active = false }
  }, [])

  useEffect(() => {
    if (!canReadLots || task === 'create') return
    let active = true
    const timer = window.setTimeout(() => {
      getLots({ q: query.trim(), product_id: productId || undefined, cursor, page_size: 20 })
        .then(page => { if (active) { setLots(page.items); setNextCursor(page.next_cursor) } })
        .catch((err: unknown) => { if (active) setError(err instanceof Error ? err.message : 'Không tải được danh sách lô.') })
        .finally(() => { if (active) setLoading(false) })
    }, 250)
    return () => { active = false; window.clearTimeout(timer) }
  }, [canReadLots, query, productId, cursor, refresh, task])

  const resetPage = () => { setLoading(true); setError(null); setCursor(undefined); setPreviousCursors([]) }
  if (!canReadLots) return <p role="status">Tài khoản này không có quyền xem danh sách lô.</p>
  if (task === 'create') return <div className="task-page info-stack">
    <a href="/lots" className="ds-button ds-button-secondary">← Danh sách lô</a>
    {error && <p role="alert">{error}</p>}
    {canCreateLots ? <LotCreateForm products={products} loadingProducts={loadingProducts} onCreated={lot => onOpenLot(lot.id)} /> : <p role="status">Tài khoản này không có quyền tạo lô thu hoạch.</p>}
  </div>

  return <section className="data-table-wrapper panel-card" aria-labelledby="lots-table-title">
    <div className="data-table-header">
      <div><h2 id="lots-table-title">Danh sách lô</h2><p className="panel-sub">Chọn nông sản để xem thông tin lô và nguồn gốc.</p></div>
      <div className="action-row">
        {canCreateLots && <TaskLink href="/lots?task=create">Tạo lô thu hoạch</TaskLink>}
        <button className="ds-button ds-button-secondary" type="button" disabled={loading} onClick={() => { setLoading(true); setError(null); setRefresh(value => value + 1) }}>Làm mới</button>
      </div>
    </div>
    <div className="lot-filter-row">
      <label className="form-field">Tìm theo mã lô<input type="search" value={query} onChange={event => { resetPage(); setQuery(event.target.value) }} placeholder="Nhập mã lô cần tìm" /></label>
      <label className="form-field">Sản phẩm<select value={productId} disabled={loadingProducts} onChange={event => { resetPage(); setSelected([]); setProductId(event.target.value) }}><option value="">Tất cả sản phẩm</option>{products.map(product => <option key={product.id} value={product.id}>{product.name}</option>)}</select></label>
    </div>
    {canTransform && <div className="selection-bar">
      <p>{selected.length ? `Đã chọn ${selected.length} lô. Chỉ gộp lô cùng sản phẩm do đơn vị của bạn đang giữ.` : 'Để gộp lô, tích chọn ít nhất hai lô cùng sản phẩm.'}</p>
      {selected.length >= 2 && <TaskLink href={`/lots/${selected[0].id}?task=merge&parents=${selected.map(lot => lot.id).join(',')}`}>Gộp {selected.length} lô đã chọn</TaskLink>}
      {selected.length > 0 && <button type="button" className="ds-button ds-button-secondary" onClick={() => setSelected([])}>Bỏ chọn tất cả</button>}
    </div>}
    {error && <p className="alert-box alert-error table-alert" role="alert">{error}</p>}
    <div className="table-scroll"><table className="data-table lots-table">
      <thead><tr>{canTransform && <th scope="col">Chọn</th>}<th scope="col">Nông sản</th><th scope="col">Mã truy xuất</th><th scope="col">Ngày thu hoạch</th><th scope="col">Còn lại</th><th scope="col">Trạng thái</th><th scope="col">Địa điểm</th>{canReadEvents && <th scope="col">Lịch sử</th>}</tr></thead>
      <tbody>{loading ? <tr><td colSpan={8} aria-busy="true">Đang tải danh sách lô…</td></tr> : lots.length === 0 ? <tr><td colSpan={8}>Không có lô phù hợp. Thử đổi bộ lọc hoặc tạo lô thu hoạch mới.</td></tr> : lots.map(lot => {
        const code = lot.lot_code ?? lot.id.slice(0, 8)
        const selectedHere = selected.some(item => item.id === lot.id)
        const reason = lot.current_holder_organization_id !== organizationId ? 'Đơn vị của bạn không giữ lô này' : lot.status !== 'active' || Number(lot.remaining_quantity) <= 0 ? 'Lô không còn lượng khả dụng' : selected.length && selected[0].product_id !== lot.product_id ? 'Sản phẩm khác với lô đã chọn' : selected.length >= 100 && !selectedHere ? 'Tối đa 100 lô mỗi lần gộp' : ''
        return <tr key={lot.id}>
          {canTransform && <td data-label="Chọn" title={reason}><input type="checkbox" aria-label={`Chọn ${code}${reason ? `: ${reason}` : ''}`} checked={selectedHere} disabled={!!reason && !selectedHere} onChange={event => {
            if (event.target.checked && selected.length === 0) { resetPage(); setProductId(lot.product_id ?? '') }
            setSelected(current => event.target.checked ? [...current, lot] : current.filter(item => item.id !== lot.id))
          }} />{reason && !selectedHere && <small className="panel-sub">{reason}</small>}</td>}
          <th scope="row" data-label="Nông sản"><a className="lot-code-link" href={`/lots/${lot.id}`} onClick={event => { if (!event.ctrlKey && !event.metaKey && !event.shiftKey && event.button === 0) {event.preventDefault(); onOpenLot(lot.id)} }}>{lot.product?.name ?? lot.name}</a></th>
          <td data-label="Mã truy xuất"><code>{code}</code></td><td data-label="Ngày thu hoạch">{lot.harvested_on ?? 'Lô dẫn xuất'}</td><td data-label="Còn lại">{lot.remaining_quantity} {lot.product?.unit}</td><td data-label="Trạng thái">{lotStatusLabel(lot.status)}</td><td data-label="Địa điểm">{lot.current_location?.name ?? 'Chưa gán địa điểm'}</td>
          {canReadEvents && <td data-label="Lịch sử"><a href={`/lots/${lot.id}?view=history`} className="ds-button ds-button-secondary">Xem lịch sử</a></td>}
        </tr>
      })}</tbody>
    </table></div>
    <div className="lot-pagination">
      <span>Trang {previousCursors.length + 1} · {lots.length} lô trên trang</span>
      <button type="button" className="ds-button ds-button-secondary" disabled={loading || previousCursors.length === 0} onClick={() => { const previous = [...previousCursors]; setCursor(previous.pop()); setPreviousCursors(previous); setLoading(true); setError(null) }}>Trang trước</button>
      <button type="button" className="ds-button ds-button-secondary" disabled={loading || !nextCursor} onClick={() => { if (nextCursor) {setPreviousCursors(current => [...current, cursor]); setCursor(nextCursor); setLoading(true); setError(null)} }}>Trang sau</button>
    </div>
  </section>
}
