import { lazy, Suspense, useCallback, useEffect, useRef, useState, type FormEvent } from 'react'
import {
  createHandover,
  getHandoverOrganizations,
  getIncomingHandovers,
  getLot,
  getLotHistory,
  getOutgoingHandovers,
} from '../services/api'
import type { EventHistory, Handover, Lot, LotDetail, OrganizationOption } from '../types'
import { EventTimeline } from './EventTimeline'
import { LotTransformForm } from './LotTransformForm'
import { LotLifecyclePanel } from './LotLifecyclePanel'
import { lotStatusLabel } from '../types'
import { TaskLink } from './TaskLink'
import { EventCreateForm } from './EventCreateForm'
import { RecallPanel } from './RecallPanel'
const LineagePanel = lazy(() => import('./LineagePanel').then(module => ({default: module.LineagePanel})))

interface LotDetailPanelProps {
  canManageDistribution: boolean
  canTransform: boolean
  organizationId: string
  onOpenLot: (lotId: string) => void
  lotId: string
  canReadEvents: boolean
  canCreateEvents: boolean
  canCreateHandover: boolean
  canResolveHandover: boolean
  onBack: () => void
}

function displayLotCode(lot: Pick<Lot, 'lot_code' | 'id'>): string {
  return lot.lot_code ?? lot.id.slice(0, 8)
}

function statusLabel(status: Lot['status']): string {
  return lotStatusLabel(status)
}

function handoverLabel(status: Handover['status']): string {
  if (status === 'accepted') return 'Đã nhận'
  if (status === 'rejected') return 'Đã từ chối'
  return 'Đang chờ xác nhận'
}

export function LotDetailPanel({
  canManageDistribution,
  canTransform,
  organizationId,
  onOpenLot,
  lotId,
  canReadEvents,
  canCreateEvents,
  canCreateHandover,
  canResolveHandover,
  onBack,
}: LotDetailPanelProps) {
  const [lot, setLot] = useState<LotDetail | null>(null)
  const [history, setHistory] = useState<EventHistory | null>(null)
  const [organizations, setOrganizations] = useState<OrganizationOption[]>([])
  const [handover, setHandover] = useState<Handover | null>(null)
  const [loadedLotId, setLoadedLotId] = useState<string | null>(null)
  const [recipientId, setRecipientId] = useState('')
  const [note, setNote] = useState('')
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)
  const [transformCompleted, setTransformCompleted] = useState(false)
  const savingRef = useRef(false)
  const task = new URLSearchParams(window.location.search).get('task')
  const initialView = new URLSearchParams(window.location.search).get('view')
  const [view, setView] = useState((initialView === 'history' && canReadEvents) || initialView === 'origins' || initialView === 'recall' ? initialView : 'overview')
  const taskAllowed = task === 'split' || task === 'merge' ? canTransform : task === 'move' || task === 'consume' ? canManageDistribution : task === 'handover' ? canCreateHandover : task === 'event' ? canCreateEvents : task === 'recall' ? true : false

  const loadDetails = useCallback(async () => {
    const [lotResult, historyResult, outgoing, incoming, orgOptions] = await Promise.all([
      getLot(lotId),
      canReadEvents ? getLotHistory(lotId) : Promise.resolve(null),
      canCreateHandover ? getOutgoingHandovers() : Promise.resolve([]),
      canResolveHandover ? getIncomingHandovers() : Promise.resolve([]),
      canCreateHandover ? getHandoverOrganizations() : Promise.resolve([]),
    ])
    const latest = [...outgoing, ...incoming]
      .filter((item) => item.lot_id === lotId)
      .sort((left, right) => right.created_at.localeCompare(left.created_at))[0]
    return { lot: lotResult, history: historyResult, organizations: orgOptions, handover: latest ?? null }
  }, [canCreateHandover, canReadEvents, canResolveHandover, lotId])

  useEffect(() => {
    let active = true
    loadDetails()
      .then((details) => {
        if (!active) return
        setLot(details.lot)
        setLoadedLotId(lotId)
        setHistory(details.history)
        setOrganizations(details.organizations)
        setRecipientId((current) => current || details.organizations[0]?.id || '')
        setHandover(details.handover)
        setError(null)
      })
      .catch((err: unknown) => {
        if (!active) return
        setLot(null)
        setLoadedLotId(lotId)
        setError(err instanceof Error ? err.message : 'Không thể tải chi tiết lô.')
      })
      .finally(() => {
        if (active) setLoading(false)
      })
    return () => { active = false }
  }, [loadDetails, lotId])

  const sendHandover = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    if (savingRef.current || !lot || !recipientId || lot.status !== 'active') return
    savingRef.current = true
    setSaving(true)
    setError(null)
    setNotice(null)
    try {
      const created = await createHandover({
        lot_id: lot.id,
        to_organization_id: recipientId,
        note: note.trim() || undefined,
      })
      setHandover(created)
      setLot((current) => current ? { ...current, status: 'pending_handover' } : current)
      setNote('')
      setNotice('Đã gửi yêu cầu. Lô vẫn do đơn vị của bạn giữ cho đến khi bên nhận xác nhận.')
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Không thể gửi yêu cầu bàn giao.')
    } finally {
      savingRef.current = false
      setSaving(false)
    }
  }

  return (
    <div className="info-stack lot-detail-page">
      <button type="button" className="ds-button ds-button-secondary lot-detail-back" onClick={onBack}>
        ← Danh sách lô
      </button>

      {error && <div className="alert-box alert-error" role="alert">{error}</div>}
      {notice && <div className="alert-box alert-success" role="status">{notice}</div>}
      {loading || loadedLotId !== lotId ? (
        <section className="panel-card panel-box" aria-busy="true">Đang tải chi tiết lô…</section>
      ) : lot ? (
        <>
          <section className="panel-card panel-box" aria-labelledby="lot-detail-title">
            <div className="panel-head lot-detail-heading">
              <div>
                <p className="panel-sub">Chi tiết lô hàng</p>
                <h2 id="lot-detail-title">{lot.name && lot.name !== lot.product?.name ? lot.name : (lot.product?.name ?? lot.name)}</h2>
                <p className="panel-sub">Mã truy xuất: <code>{displayLotCode(lot)}</code></p>
                <p className="panel-sub">Đơn vị đang giữ: <strong>{lot.current_holder_organization_name}</strong></p>
              </div>
              <span className={`status-badge ${lot.status === 'active' ? 'status-done' : 'status-neutral'}`}>
                {statusLabel(lot.status)}
              </span>
            </div>
            <dl className="lot-detail-facts">
              {canReadEvents && <div><dt>Hoạt động đã ghi</dt><dd>{lot.event_count}</dd></div>}
              <div><dt>Ngày thu hoạch</dt><dd>{lot.harvested_on ?? '—'}</dd></div>
              <div><dt>Khối lượng ban đầu</dt><dd>{lot.quantity ?? '—'} {lot.product?.unit ?? ''}</dd></div>
              <div><dt>Còn lại</dt><dd>{lot.remaining_quantity} {lot.product?.unit ?? ''}</dd></div>
              <div><dt>Địa điểm hiện tại</dt><dd>{lot.current_location ? <>{lot.current_location.name}<br />{lot.current_location.address}</> : 'Chưa gán địa điểm'}</dd></div>
              <div><dt>Vùng trồng gốc</dt><dd>{(lot.root_farms ?? lot.direct_farms).map(farm => farm.name).join(', ') || 'Chưa có thông tin vùng trồng'}</dd></div>
            </dl>
          </section>

          {!task && <>
            <nav className="detail-tabs" role="tablist" aria-label="Thông tin lô" onKeyDown={event => {
              if (!['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(event.key)) return
              event.preventDefault()
              const tabs = Array.from(event.currentTarget.querySelectorAll<HTMLButtonElement>('[role=tab]'))
              const index = tabs.findIndex(tab => tab === document.activeElement)
              const next = event.key === 'Home' ? 0 : event.key === 'End' ? tabs.length - 1 : (index + (event.key === 'ArrowRight' ? 1 : -1) + tabs.length) % tabs.length
              tabs[next]?.click(); tabs[next]?.focus()
            }}>
              {(['overview', ...(canReadEvents ? ['history'] : []), 'origins'] as const).map(tab => <button key={tab} id={`tab-${tab}`} type="button" role="tab" aria-selected={view === tab} aria-controls="lot-tab-content" tabIndex={view === tab ? 0 : -1} onClick={() => setView(tab)}>
                {tab === 'overview' ? 'Tổng quan' : tab === 'history' ? 'Lịch sử sự kiện' : 'Nguồn gốc'}
              </button>)}
            </nav>
            <div id="lot-tab-content" role="tabpanel" aria-labelledby={`tab-${view}`} className="info-stack">
              {view === 'overview' && <section className="panel-card panel-box">
                <h2>Thao tác với lô</h2>
                <p className="panel-sub">Chọn thao tác phù hợp với lô nông sản đang giữ.</p>
                <div className="action-row">
                  {lot.status === 'active' && lot.current_holder_organization_id === organizationId && <>
                    {canTransform && <><TaskLink href={`/lots/${lot.id}?task=split`}>Tách lô</TaskLink><TaskLink href={`/lots/${lot.id}?task=merge`} secondary>Gộp lô</TaskLink></>}
                    {canManageDistribution && <><TaskLink href={`/lots/${lot.id}?task=move`} secondary>Di chuyển lô</TaskLink><TaskLink href={`/lots/${lot.id}?task=consume`} secondary>Ghi nhận tiêu thụ</TaskLink></>}
                    {canCreateHandover && <TaskLink href={`/lots/${lot.id}?task=handover`} secondary>Bàn giao lô</TaskLink>}
                    {canCreateEvents && <TaskLink href={`/lots/${lot.id}?task=event`} secondary>Ghi nhận hoạt động</TaskLink>}
                  </>}
                  <TaskLink href={`/lots/${lot.id}?task=recall`} secondary>Kế hoạch thu hồi</TaskLink>
                </div>
                {lot.status !== 'active' && <p>Lô {statusLabel(lot.status).toLocaleLowerCase('vi-VN')}. Xem lịch sử hoặc kế hoạch thu hồi để kiểm tra dòng chảy sản phẩm.</p>}
                {lot.current_holder_organization_id !== organizationId && <p>Bạn đang xem thông tin. Đơn vị đang giữ lô mới có thể thực hiện thao tác.</p>}
                {handover && <p>Bàn giao gần nhất: {handoverLabel(handover.status)} · {handover.from_organization_name} → {handover.to_organization_name}{handover.overdue_at && handover.status === 'pending' ? ' · Quá hạn xác nhận' : ''}</p>}
              </section>}
              {view === 'history' && history && <section className="panel-card panel-box"><EventTimeline key={lot.id} lotId={lot.id} nextCursor={history.next_cursor} events={history.events} lotName={displayLotCode(lot)} loading={false} integrity={history.integrity} /></section>}
              {view === 'origins' && <>
          <section className="panel-card panel-box" aria-label="Nguồn gốc và quan hệ trực tiếp">
            <h2>Nguồn gốc và quan hệ</h2>
            <p>Vùng trồng liên quan trực tiếp: {lot.direct_farms.map(farm => farm.name).join(', ') || 'Xem vùng trồng gốc trong sơ đồ bên dưới'}</p>
            <p>Lô mẹ: {lot.parents.length === 0 ? 'Lô thu hoạch gốc' : lot.parents.map(parent => <button key={parent.id} type="button" disabled={parent.historical_only} title={parent.historical_only ? 'Xem lịch sử trong sơ đồ bên dưới' : undefined} className="ds-button ds-button-secondary" onClick={() => onOpenLot(parent.id)}>{displayLotCode(parent)}</button>)}</p>
            <p>Lô con: {lot.children.length === 0 ? 'Chưa có lô con' : lot.children.map(child => <button key={child.id} type="button" disabled={child.historical_only} title={child.historical_only ? 'Xem lịch sử trong sơ đồ bên dưới' : undefined} className="ds-button ds-button-secondary" onClick={() => onOpenLot(child.id)}>{displayLotCode(child)}</button>)}</p>
          </section>

          <Suspense fallback={<section className="panel-card panel-box" aria-busy="true">Đang tải sơ đồ phả hệ…</section>}>
            <LineagePanel key={`${lot.id}:${lot.status}:${lot.current_location_id}`} lotId={lot.id} onOpenLot={onOpenLot} />
          </Suspense>

          <div style={{ marginTop: '1rem' }}>
            <RecallPanel key={lot.id} lotId={lot.id} onOpenLot={onOpenLot} />
          </div>
              </>}
            </div>
          </>}

          {task && <a className="ds-button ds-button-secondary" href={`/lots/${lot.id}`}>← Quay lại chi tiết lô</a>}
          {task === 'recall' && <RecallPanel key={lot.id} lotId={lot.id} onOpenLot={onOpenLot} />}
          {task === 'event' && canCreateEvents && lot.current_holder_organization_id === organizationId && lot.status === 'active' && <EventCreateForm lot={lot} />}

          {(task === 'split' || task === 'merge') && canTransform && (transformCompleted || (lot.current_holder_organization_id === organizationId && lot.status === 'active')) && (
            <LotTransformForm key={lot.id} initialMode={task} lot={lot} canManageDistribution={canManageDistribution} onCompleted={onOpenLot} onTransformed={async () => {
              setTransformCompleted(true)
              try {
                const details = await loadDetails()
                setLot(details.lot); setHistory(details.history); setHandover(details.handover)
              } catch { setError('Thao tác đã được lưu, nhưng chưa tải lại được thông tin lô nguồn. Tải lại trang để kiểm tra lượng còn lại.') }
            }} />
          )}

          {(task === 'move' || task === 'consume') && canManageDistribution && lot.current_holder_organization_id === organizationId && lot.status === 'active' && (
            <LotLifecyclePanel key={`${lot.id}:${lot.current_location_id}`} operation={task} lot={lot} onCompleted={async () => {
              const details = await loadDetails()
              setLot(details.lot); setHistory(details.history); setHandover(details.handover)
              setNotice(task === 'move' ? 'Đã di chuyển lô. Địa điểm hiện tại đã được cập nhật.' : 'Đã ghi nhận tiêu thụ và kết thúc lô.')
            }} />
          )}

          {task === 'handover' && <section className="panel-card panel-box" aria-labelledby="lot-handover-title">
            <div className="panel-head">
              <div>
                <h2 id="lot-handover-title">Bàn giao lô</h2>
                <p className="panel-sub">Đơn vị nhận cần xác nhận trước khi quyền giữ lô được chuyển.</p>
              </div>
              {handover && <span className={`handover-status handover-status-${handover.status}`}>{handoverLabel(handover.status)}</span>}
            </div>

            {handover && (
              <div className="lot-handover-current">
                <p>
                  {handover.from_organization_name} → {handover.to_organization_name}
                </p>
                {handover.note && <p className="panel-sub">Ghi chú: {handover.note}</p>}
                {handover.status === 'pending' && handover.overdue_at && <p className="alert-box alert-error" role="status">Quá hạn xác nhận bàn giao · Bên nhận vẫn có thể xác nhận nhận lô.</p>}
                <time className="panel-sub" dateTime={handover.created_at}>
                  {new Date(handover.created_at).toLocaleString('vi-VN', { dateStyle: 'medium', timeStyle: 'short' })}
                </time>
              </div>
            )}

            {canCreateHandover && lot.current_holder_organization_id === organizationId && lot.status === 'active' && (
              <form className="handover-create-form lot-detail-handover-form" onSubmit={(event) => void sendHandover(event)}>
                <div className="form-field">
                  <label htmlFor="lot-detail-recipient">Đơn vị nhận</label>
                  <select
                    id="lot-detail-recipient"
                    value={recipientId}
                    onChange={(event) => setRecipientId(event.target.value)}
                    required
                    disabled={organizations.length === 0}
                  >
                    <option value="">Chọn đơn vị nhận</option>
                    {organizations.map((organization) => (
                      <option key={organization.id} value={organization.id}>{organization.name}</option>
                    ))}
                  </select>
                </div>
                <div className="form-field handover-note-field">
                  <label htmlFor="lot-detail-note">Ghi chú (không bắt buộc)</label>
                  <input
                    id="lot-detail-note"
                    value={note}
                    maxLength={500}
                    onChange={(event) => setNote(event.target.value)}
                    placeholder="Thông tin cần gửi bên nhận"
                  />
                </div>
                <button className="ds-button ds-button-brand" type="submit" disabled={saving || !recipientId}>
                  {saving ? 'Đang gửi…' : 'Gửi yêu cầu bàn giao'}
                </button>
              </form>
            )}
            {canCreateHandover && lot.status === 'pending_handover' && !handover && (
              <p className="panel-sub">Lô đang chờ xác nhận bàn giao.</p>
            )}
            {canCreateHandover && organizations.length === 0 && lot.status === 'active' && (
              <p className="panel-sub">Chưa có đơn vị nhận khả dụng để gửi bàn giao.</p>
            )}
          </section>}

          {task && !notice && !transformCompleted && (!taskAllowed || lot.current_holder_organization_id !== organizationId || lot.status !== 'active') && <p role="status">Thao tác không khả dụng với trạng thái hoặc quyền hiện tại. Quay lại chi tiết lô để chọn thao tác phù hợp.</p>}
        </>
      ) : null}
    </div>
  )
}
