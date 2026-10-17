import { useEffect, useState, useMemo } from 'react'
import { getLotRecall } from '../services/api'
import type { RecallReport, RecallLotItem } from '../types'
import { lotStatusLabel } from '../types'

interface RecallPanelProps {
  lotId: string
  onOpenLot: (lotId: string) => void
}

export function RecallPanel({ lotId, onOpenLot }: RecallPanelProps) {
  const [reportLotId, setReportLotId] = useState<string | null>(null)
  const [report, setReport] = useState<RecallReport | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [statusFilter, setStatusFilter] = useState<'all' | 'active' | 'consumed' | 'closed'>('all')

  useEffect(() => {
    let active = true
    getLotRecall(lotId)
      .then((data) => {
        if (!active) return
        setReport(data)
        setReportLotId(lotId)
        setError(null)
      })
      .catch((err: unknown) => {
        if (!active) return
        setError(err instanceof Error ? err.message : 'Không thể tải báo cáo thu hồi.')
        setReportLotId(lotId)
      })
      .finally(() => {
        if (active) setLoading(false)
      })
    return () => {
      active = false
    }
  }, [lotId])

  const isLoading = loading || reportLotId !== lotId

  const filteredLots = useMemo(() => {
    if (!report) return []
    const lots = report.affected_lots
    if (statusFilter === 'all') return lots
    if (statusFilter === 'active') return lots.filter((item) => item.status === 'active' || item.status === 'pending_handover')
    if (statusFilter === 'consumed') return lots.filter((item) => item.status === 'consumed')
    if (statusFilter === 'closed') return lots.filter((item) => item.status === 'closed')
    return lots
  }, [report, statusFilter])

  const exportCsv = () => {
    if (!report) return
    const headers = [
      'Mã lô',
      'Tên lô',
      'Tầng',
      'Trạng thái',
      'Đơn vị đang giữ',
      'Loại đơn vị',
      'Địa điểm kho',
      'Địa chỉ kho',
      'Khối lượng ban đầu (kg)',
      'Còn lại trong kho (kg)',
      'Lượng có thể thu hồi (kg)',
      'Đã bán/tiêu thụ (kg)',
      'Gộp đa nguồn',
    ]

    const rows = report.affected_lots.map((item) => [
      `"${item.lot_code ?? item.id}"`,
      `"${item.name.replace(/"/g, '""')}"`,
      item.tier,
      `"${lotStatusLabel(item.status)}"`,
      `"${item.current_holder_organization_name ?? '—'}"`,
      `"${item.holder_org_type ?? '—'}"`,
      `"${item.current_location?.name ?? '—'}"`,
      `"${item.current_location?.address ?? '—'}"`,
      item.quantity ?? '0.000',
      item.remaining_quantity,
      item.recoverable_quantity,
      item.consumed_quantity,
      item.is_multi_source_merge ? 'Có' : 'Không',
    ])

    const csvContent = '\uFEFF' + [headers.join(','), ...rows.map((row) => row.join(','))].join('\r\n')
    const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' })
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = `danh-sach-thu-hoi-${report.root_lot.lot_code ?? lotId.slice(0, 8)}.csv`
    link.click()
    URL.revokeObjectURL(url)
  }

  if (isLoading) {
    return <section className="panel-card panel-box" aria-busy="true">Đang tổng hợp danh sách thu hồi phả hệ…</section>
  }

  if (error) {
    return <div className="alert-box alert-error" role="alert">{error}</div>
  }

  if (!report) {
    return <p>Không có dữ liệu thu hồi cho lô này.</p>
  }

  const { summary, root_lot } = report

  return (
    <section className="panel-card panel-box" aria-labelledby="recall-panel-title">
      <div className="panel-head">
        <div>
          <h2 id="recall-panel-title">Danh sách và Kế hoạch Thu hồi</h2>
          <p className="panel-sub">
            Truy vết xuôi toàn bộ các nhánh phân phối từ lô <strong>{root_lot.lot_code ?? root_lot.name}</strong> để xác định vị trí tồn kho và lượng hàng đã tiêu thụ.
          </p>
        </div>
        <button
          type="button"
          className="ds-button ds-button-secondary"
          onClick={exportCsv}
        >
          Xuất báo cáo CSV
        </button>
      </div>

      {summary.has_consumed_lot && (
        <div className="alert-box alert-error" role="alert">
          <strong>CẢNH BÁO KHẨN CẤP:</strong> Đã có <strong>{summary.total_consumed_kg} {root_lot.unit ?? 'kg'}</strong> sản phẩm được bán / tiêu thụ ra thị trường. Cần phát lệnh cảnh báo thu hồi tới các đại lý bán lẻ và người tiêu dùng!
        </div>
      )}

      {summary.has_multi_source_merge && (
        <div className="alert-box alert-warning" role="alert">
          <strong>LƯU Ý LÂY NHIỄM CHÉO:</strong> Có lô được gộp từ nhiều nguồn nông sản khác nhau trong chuỗi. Các sản phẩm gộp này đều nằm trong phạm vi nghi nhiễm.
        </div>
      )}

      {/* KPI Cards */}
      <div className="dashboard-kpi-grid">
        <div className="kpi-card">
          <div className="kpi-title">Tổng lô ảnh hưởng</div>
          <div className="kpi-value">{summary.total_affected_lots}</div>
          <div className="kpi-subtitle">Gồm lô gốc và {summary.total_descendants_count} lô hậu duệ</div>
        </div>

        <div className="kpi-card">
          <div className="kpi-title">Tồn kho có thể thu hồi</div>
          <div className="kpi-value">{summary.total_recoverable_kg} <span className="kpi-unit">{root_lot.unit ?? 'kg'}</span></div>
          <div className="kpi-subtitle">Đang nằm tại các kho và điểm tập kết</div>
        </div>

        <div className="kpi-card">
          <div className="kpi-title">Đã bán / Tiêu thụ</div>
          <div className="kpi-value" style={{ color: summary.has_consumed_lot ? '#dc2626' : 'inherit' }}>
            {summary.total_consumed_kg} <span className="kpi-unit">{root_lot.unit ?? 'kg'}</span>
          </div>
          <div className="kpi-subtitle">Đã xuất bán hoặc đưa vào tiêu thụ</div>
        </div>

        <div className="kpi-card">
          <div className="kpi-title">Đơn vị liên quan</div>
          <div className="kpi-value">{summary.involved_organizations_count}</div>
          <div className="kpi-subtitle">Cần gửi thông báo phong tỏa kho</div>
        </div>
      </div>

      {/* Involved Organizations List */}
      <div className="panel-box" style={{ marginTop: '1rem' }}>
        <strong>Các tổ chức cần liên hệ thu hồi khẩn cấp: </strong>
        <span>{summary.involved_organizations.join(' · ') || 'Chưa xác định'}</span>
      </div>

      {/* Filter Toolbar */}
      <div style={{ display: 'flex', gap: '0.5rem', alignItems: 'center', marginTop: '1.25rem', marginBottom: '0.75rem' }}>
        <span>Lọc theo trạng thái:</span>
        <button
          type="button"
          className={`ds-button ${statusFilter === 'all' ? 'ds-button-brand' : 'ds-button-secondary'} ds-button-sm`}
          onClick={() => setStatusFilter('all')}
        >
          Tất cả ({report.affected_lots.length})
        </button>
        <button
          type="button"
          className={`ds-button ${statusFilter === 'active' ? 'ds-button-brand' : 'ds-button-secondary'} ds-button-sm`}
          onClick={() => setStatusFilter('active')}
        >
          Còn tồn kho ({report.affected_lots.filter((item) => item.status === 'active' || item.status === 'pending_handover').length})
        </button>
        <button
          type="button"
          className={`ds-button ${statusFilter === 'consumed' ? 'ds-button-brand' : 'ds-button-secondary'} ds-button-sm`}
          onClick={() => setStatusFilter('consumed')}
        >
          Đã bán/tiêu thụ ({report.affected_lots.filter((item) => item.status === 'consumed').length})
        </button>
        <button
          type="button"
          className={`ds-button ${statusFilter === 'closed' ? 'ds-button-brand' : 'ds-button-secondary'} ds-button-sm`}
          onClick={() => setStatusFilter('closed')}
        >
          Đã chia tách/gộp ({report.affected_lots.filter((item) => item.status === 'closed').length})
        </button>
      </div>

      {/* Detailed Recall Lots Table */}
      <div className="lineage-table-scroll">
        <table className="data-table source-table">
          <thead>
            <tr>
              <th>Mã lô</th>
              <th>Tên lô</th>
              <th>Tầng</th>
              <th>Đang ở đâu (Đơn vị & Địa điểm kho)</th>
              <th>Còn bao nhiêu (Tồn kho)</th>
              <th>Đã bán bao nhiêu (Tiêu thụ)</th>
              <th>Trạng thái</th>
              <th>Pha trộn</th>
            </tr>
          </thead>
          <tbody>
            {filteredLots.map((item: RecallLotItem) => (
              <tr key={item.id} style={{ backgroundColor: item.status === 'consumed' ? 'rgba(239, 68, 68, 0.08)' : undefined }}>
                <td>
                  <button
                    type="button"
                    className="ds-button ds-button-secondary ds-button-sm"
                    onClick={() => onOpenLot(item.id)}
                  >
                    {item.lot_code ?? item.id.slice(0, 8)}
                  </button>
                </td>
                <td>
                  <strong>{item.name}</strong>
                  {item.id === root_lot.id && <span style={{ marginLeft: '0.5rem', fontSize: '0.8rem', color: '#dc2626' }}>[Lô khởi nguồn]</span>}
                </td>
                <td>
                  <span className="status-badge status-neutral">Tầng {item.tier}</span>
                </td>
                <td>
                  <div>
                    <strong>{item.current_holder_organization_name ?? '—'}</strong>
                    {item.holder_org_type && <span style={{ fontSize: '0.8rem', opacity: 0.8 }}> ({item.holder_org_type})</span>}
                  </div>
                  <div style={{ fontSize: '0.85rem', color: 'var(--text-muted, #666)' }}>
                    {item.current_location ? `${item.current_location.name} — ${item.current_location.address}` : 'Chưa gán vị trí kho cụ thể'}
                  </div>
                </td>
                <td>
                  <span style={{ fontWeight: item.recoverable_quantity !== '0.000' && item.recoverable_quantity !== '0' ? 'bold' : 'normal' }}>
                    {item.remaining_quantity} {item.unit ?? 'kg'}
                  </span>
                  {item.status === 'active' && <span style={{ display: 'block', fontSize: '0.75rem', color: '#16a34a' }}>Thu hồi ngay</span>}
                </td>
                <td>
                  <span style={{ fontWeight: item.consumed_quantity !== '0.000' && item.consumed_quantity !== '0' ? 'bold' : 'normal', color: item.status === 'consumed' ? '#dc2626' : 'inherit' }}>
                    {item.consumed_quantity} {item.unit ?? 'kg'}
                  </span>
                  {item.status === 'consumed' && <span style={{ display: 'block', fontSize: '0.75rem', color: '#dc2626' }}>Đã xuất bán</span>}
                </td>
                <td>
                  <span className={`status-badge ${item.status === 'active' ? 'status-done' : item.status === 'consumed' ? 'status-warning' : 'status-neutral'}`}>
                    {lotStatusLabel(item.status)}
                  </span>
                </td>
                <td>
                  {item.is_multi_source_merge ? (
                    <span style={{ color: '#d97706', fontSize: '0.8rem', fontWeight: 'bold' }}>Gộp đa nguồn</span>
                  ) : (
                    <span style={{ color: '#6b7280', fontSize: '0.8rem' }}>Đơn nguồn</span>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  )
}
