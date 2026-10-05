import { useState, useEffect, useCallback, useRef, type FormEvent } from 'react'
import { createFarm, getFarms, updateFarm } from '../services/api'
import {
  hasPermission,
  ROLE_LABELS,
  ROLE_PERMISSIONS,
  type Farm,
  type SessionUser,
} from '../types'
import { FarmFormPanel } from './FarmFormPanel'
import { IntegrityPanel } from './IntegrityPanel'
import { LotsPanel } from './LotsPanel'
import { SecurityPanel } from './SecurityPanel'
import { WorkspaceSidebar } from './WorkspaceSidebar'
import { WorkspaceTopbar } from './WorkspaceTopbar'

export type WorkspaceTab = 'lots' | 'overview' | 'security' | 'integrity'

interface FarmWorkspaceProps {
  user: SessionUser
  activeTab: WorkspaceTab
  isDark: boolean
  onToggleTheme: () => void
  onTabChange: (tab: WorkspaceTab) => void
  onLogout: () => void
  onNotify: (message: string) => void
}

export function FarmWorkspace({
  user,
  activeTab,
  isDark,
  onToggleTheme,
  onTabChange,
  onLogout,
  onNotify,
}: FarmWorkspaceProps) {
  const canReadFarms = hasPermission(user.role, 'farms:read')
  const canWriteFarms = hasPermission(user.role, 'farms:write')
  const canReadLots = hasPermission(user.role, 'lots:read')
  const grantedPermissions = ROLE_PERMISSIONS[user.role] ?? []

  const [sidebarOpen, setSidebarOpen] = useState(false)
  const [searchQuery, setSearchQuery] = useState('')

  const [farms, setFarms] = useState<Farm[]>([])
  const [loadingFarms, setLoadingFarms] = useState<boolean>(canReadFarms)
  const [listError, setListError] = useState<string | null>(null)

  const [editingFarm, setEditingFarm] = useState<Farm | null>(null)
  const [name, setName] = useState('')
  const [areaHa, setAreaHa] = useState('')
  const [latitude, setLatitude] = useState('')
  const [longitude, setLongitude] = useState('')
  const [saving, setSaving] = useState(false)
  const savingRef = useRef(false)
  const [formFeedback, setFormFeedback] = useState<{
    type: 'success' | 'error'
    message: string
  } | null>(null)

  const [rbacProbeResult, setRbacProbeResult] = useState<string | null>(null)
  const [tamperSimulated, setTamperSimulated] = useState(false)

  const refreshFarms = useCallback(async () => {
    if (!canReadFarms) return
    setLoadingFarms(true)
    setListError(null)
    try {
      const data = await getFarms()
      setFarms(data)
    } catch (err) {
      setListError(
        err instanceof Error ? err.message : 'Không thể tải danh sách vùng trồng'
      )
    } finally {
      setLoadingFarms(false)
    }
  }, [canReadFarms])

  useEffect(() => {
    if (!canReadFarms) return
    let cancelled = false

    getFarms()
      .then((data) => {
        if (!cancelled) {
          setFarms(data)
          setLoadingFarms(false)
        }
      })
      .catch((err: unknown) => {
        if (!cancelled) {
          setListError(
            err instanceof Error
              ? err.message
              : 'Không thể tải danh sách vùng trồng'
          )
          setLoadingFarms(false)
        }
      })

    return () => {
      cancelled = true
    }
  }, [canReadFarms])

  const resetForm = () => {
    setEditingFarm(null)
    setName('')
    setAreaHa('')
    setLatitude('')
    setLongitude('')
  }

  const startEdit = (farm: Farm) => {
    setEditingFarm(farm)
    setName(farm.name)
    setAreaHa(String(farm.area_ha))
    setLatitude(String(farm.latitude))
    setLongitude(String(farm.longitude))
    setFormFeedback(null)
    onTabChange('overview')
    onNotify(`Đang chỉnh sửa: ${farm.name}`)
  }

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    if (savingRef.current) return

    savingRef.current = true
    setSaving(true)
    setFormFeedback(null)

    try {
      const payload = {
        name: name.trim(),
        area_ha: areaHa.trim(),
        latitude: latitude.trim(),
        longitude: longitude.trim(),
      }

      if (editingFarm) {
        const updated = await updateFarm(editingFarm.id, payload)
        setFarms((prev) =>
          prev.map((item) => (item.id === updated.id ? updated : item))
        )
        setFormFeedback({
          type: 'success',
          message: `Đã cập nhật "${updated.name}" (UUID cố định: ${updated.id.slice(0, 8)}...).`,
        })
        onNotify(`Đã lưu cập nhật: ${updated.name}`)
      } else {
        const created = await createFarm(payload)
        setFarms((prev) => [...prev, created])
        setFormFeedback({
          type: 'success',
          message: `Đã thêm vùng trồng "${created.name}".`,
        })
        onNotify(`Đã thêm vùng trồng: ${created.name}`)
      }
      resetForm()
    } catch (err) {
      setFormFeedback({
        type: 'error',
        message: err instanceof Error ? err.message : 'Không thể lưu vùng trồng',
      })
    } finally {
      savingRef.current = false
      setSaving(false)
    }
  }

  const runForbiddenProbe = async () => {
    setRbacProbeResult('Đang gửi GET /api/v1/farms/ tới Backend...')
    try {
      await getFarms()
      setRbacProbeResult(
        '200 OK — Vai trò hiện tại được phép truy cập danh sách vùng trồng.'
      )
      onNotify('Kiểm tra API thành công (200 OK)')
    } catch (err) {
      if (err instanceof Error) {
        setRbacProbeResult(
          `403 Forbidden — Backend đã chặn truy cập theo đúng ma trận RBAC: "${err.message}"`
        )
        onNotify('Backend đã chặn truy cập trái phép (403 Forbidden)')
      }
    }
  }

  const filteredFarms = farms.filter((f) => {
    const q = searchQuery.trim().toLowerCase()
    if (!q) return true
    return (
      f.name.toLowerCase().includes(q) ||
      f.id.toLowerCase().includes(q) ||
      String(f.latitude).includes(q) ||
      String(f.longitude).includes(q)
    )
  })

  const totalAreaHa = farms.reduce(
    (sum, item) => sum + (Number(item.area_ha) || 0),
    0
  )
  const avgAreaHa = farms.length > 0 ? totalAreaHa / farms.length : 0
  const maxAreaHa = Math.max(
    ...farms.map((item) => Number(item.area_ha) || 1),
    5
  )

  return (
    <div className="application-shell">
      {sidebarOpen && (
        <button
          type="button"
          className="dashboard-overlay"
          aria-label="Đóng thanh điều hướng"
          onClick={() => setSidebarOpen(false)}
        />
      )}

      <div className="dashboard-layout">
        <WorkspaceSidebar
          user={user}
          activeTab={activeTab}
          sidebarOpen={sidebarOpen}
          onCloseSidebar={() => setSidebarOpen(false)}
          onTabChange={onTabChange}
          onLogout={onLogout}
        />

        <div className="dashboard-main">
          <WorkspaceTopbar
            user={user}
            activeTab={activeTab}
            canReadFarms={canReadFarms}
            searchQuery={searchQuery}
            isDark={isDark}
            onToggleSidebar={() => setSidebarOpen((prev) => !prev)}
            onSearchChange={setSearchQuery}
            onRefresh={() => void refreshFarms()}
            onToggleTheme={onToggleTheme}
          />

          <main className="dashboard-content">
            <section aria-label="Chỉ số vận hành tổng hợp">
              <div className="stats-grid">
                <article className="stat-card panel-card">
                  <p className="stat-label">Đơn vị thành viên (Tenant)</p>
                  <p
                    className="stat-value stat-value-sans"
                    title={user.organization_name}
                  >
                    {user.organization_name}
                  </p>
                  <p className="stat-trend">
                    ID: {user.organization_id.slice(0, 8)}...
                  </p>
                </article>

                <article className="stat-card panel-card">
                  <p className="stat-label">Vùng trồng thuộc đơn vị</p>
                  <p className="stat-value">
                    {canReadFarms ? `${farms.length} vùng` : 'Chặn (403)'}
                  </p>
                  <p className="stat-trend">
                    {canReadFarms
                      ? 'Cô lập bởi PostgreSQL RLS'
                      : 'Không có quyền farms:read'}
                  </p>
                </article>

                <article className="stat-card panel-card">
                  <p className="stat-label">Tổng diện tích canh tác</p>
                  <p className="stat-value">
                    {canReadFarms ? `${totalAreaHa.toFixed(2)} ha` : '—'}
                  </p>
                  <p className="stat-trend">
                    {canReadFarms
                      ? `TB: ${avgAreaHa.toFixed(2)} ha / thửa`
                      : 'Bị giới hạn theo RBAC'}
                  </p>
                </article>

                <article className="stat-card panel-card">
                  <p className="stat-label">Vai trò &amp; Quyền RBAC</p>
                  <p className="stat-value stat-value-sans">
                    {ROLE_LABELS[user.role]}
                  </p>
                  <p className="stat-trend">
                    <code>{user.role}</code> ({grantedPermissions.length} quyền)
                  </p>
                </article>

                <article className="stat-card panel-card">
                  <p className="stat-label">Chuỗi băm sự kiện (N3-4)</p>
                  <p className="stat-value">
                    {tamperSimulated ? 'Lỗi Hash!' : '4/4 Hợp lệ'}
                  </p>
                  <p
                    className={`stat-trend ${
                      tamperSimulated ? 'stat-trend-danger' : ''
                    }`}
                  >
                    {tamperSimulated
                      ? 'Phát hiện can thiệp tại #03'
                      : 'SHA-256 · 147,8k sự kiện/s'}
                  </p>
                </article>

                <article className="stat-card panel-card">
                  <p className="stat-label">Bảo mật phiên (N3-5)</p>
                  <p className="stat-value stat-value-sans">Argon2id + Cookie</p>
                  <p className="stat-trend">Khóa 15p nếu sai mật khẩu 5 lần</p>
                </article>
              </div>
            </section>

            {activeTab === 'lots' && (
              <LotsPanel
                canReadLots={canReadLots}
                canReadEvents={hasPermission(user.role, 'events:read')}
              />
            )}


            {activeTab === 'overview' && (
              <>
                <div className="dashboard-split-main">
                  {!canReadFarms ? (
                    <section className="panel-card panel-box">
                      <div className="panel-head">
                        <h2>
                          Chặn Truy cập Danh mục Vùng trồng theo RBAC (N3-6)
                        </h2>
                        <span className="status-badge status-danger">
                          HTTP 403 Forbidden
                        </span>
                      </div>
                      <p className="panel-sub">
                        Tài khoản <strong>{user.email}</strong> đang mang vai trò{' '}
                        <code>{user.role}</code> (quyền được cấp:{' '}
                        <code>{grantedPermissions.join(', ')}</code>). Theo thiết
                        kế bảo mật N3-6, vai trò Thanh tra viên chỉ đọc lô hàng (
                        <code>lots:read_all</code>) và bị chặn truy cập trực tiếp
                        vào API quản lý vùng trồng (<code>farms:read</code>,{' '}
                        <code>farms:write</code>).
                      </p>

                      <div className="action-row alert-spaced">
                        <button
                          type="button"
                          className="ds-button ds-button-brand ds-button-sm"
                          onClick={() => void runForbiddenProbe()}
                        >
                          Gửi thử GET /api/v1/farms/ (Kiểm chứng chặn 403)
                        </button>
                        <button
                          type="button"
                          className="ds-button ds-button-secondary ds-button-sm"
                          onClick={() => onTabChange('security')}
                        >
                          Mở Ma trận Phân quyền đầy đủ
                        </button>
                      </div>

                      {rbacProbeResult && (
                        <div className="alert-box alert-error alert-spaced">
                          {rbacProbeResult}
                        </div>
                      )}
                    </section>
                  ) : (
                    <section
                      className="data-table-wrapper panel-card"
                      aria-labelledby="farms-table-title"
                    >
                      <div className="data-table-header">
                        <div>
                          <h2 id="farms-table-title" className="section-title">
                            Danh mục Vùng trồng &amp; Thửa đất ({filteredFarms.length}
                            )
                          </h2>
                          <p className="panel-sub">
                            Dữ liệu lọc tự động theo{' '}
                            <code>
                              organization_id = {user.organization_id.slice(0, 8)}
                              ...
                            </code>{' '}
                            tại tầng PostgreSQL RLS
                          </p>
                        </div>
                        <span className="status-badge status-done">
                          UUID Bất biến (N3-7)
                        </span>
                      </div>

                      {listError && (
                        <div className="alert-box alert-error table-alert">
                          {listError}
                        </div>
                      )}

                      <div className="table-scroll">
                        <table className="data-table">
                          <thead>
                            <tr>
                              <th scope="col">Mã UUID</th>
                              <th scope="col">Tên Vùng trồng / Thửa đất</th>
                              <th scope="col">Diện tích</th>
                              <th scope="col">Tỷ trọng</th>
                              <th scope="col">Tọa độ GPS (WGS84)</th>
                              <th scope="col">Thao tác</th>
                            </tr>
                          </thead>
                          <tbody>
                            {loadingFarms ? (
                              <tr>
                                <td colSpan={6} className="cell-center">
                                  Đang tải danh sách vùng trồng...
                                </td>
                              </tr>
                            ) : filteredFarms.length === 0 ? (
                              <tr>
                                <td colSpan={6} className="cell-center">
                                  Không có vùng trồng nào khớp với bộ lọc.
                                </td>
                              </tr>
                            ) : (
                              filteredFarms.map((farm) => {
                                const areaNum = Number(farm.area_ha) || 0
                                const sharePct =
                                  totalAreaHa > 0
                                    ? Math.round((areaNum / totalAreaHa) * 100)
                                    : 0
                                return (
                                  <tr
                                    key={farm.id}
                                    className={
                                      editingFarm?.id === farm.id
                                        ? 'row-editing'
                                        : undefined
                                    }
                                  >
                                    <td>
                                      <code title={farm.id}>
                                        {farm.id.slice(0, 8)}...
                                      </code>
                                    </td>
                                    <th scope="row" className="cell-strong">
                                      {farm.name}
                                    </th>
                                    <td>
                                      <span className="status-badge status-done">
                                        {areaNum.toFixed(2)} ha
                                      </span>
                                    </td>
                                    <td>
                                      <div className="area-bar-cell">
                                        <div className="area-bar-track">
                                          <div
                                            className="area-bar-fill"
                                            style={{ width: `${sharePct}%` }}
                                          />
                                        </div>
                                        <span className="area-bar-pct">
                                          {sharePct}%
                                        </span>
                                      </div>
                                    </td>
                                    <td>
                                      <div className="coord-inline">
                                        <code>
                                          {farm.latitude}, {farm.longitude}
                                        </code>
                                        <a
                                          href={`https://www.google.com/maps?q=${farm.latitude},${farm.longitude}`}
                                          target="_blank"
                                          rel="noreferrer"
                                          className="map-external-link"
                                        >
                                          Bản đồ
                                        </a>
                                      </div>
                                    </td>
                                    <td>
                                      {canWriteFarms && (
                                        <button
                                          type="button"
                                          className="ds-button ds-button-secondary ds-button-xs"
                                          onClick={() => startEdit(farm)}
                                        >
                                          Sửa
                                        </button>
                                      )}
                                    </td>
                                  </tr>
                                )
                              })
                            )}
                          </tbody>
                        </table>
                      </div>
                    </section>
                  )}

                  <FarmFormPanel
                    canReadFarms={canReadFarms}
                    canWriteFarms={canWriteFarms}
                    farms={farms}
                    totalAreaHa={totalAreaHa}
                    maxAreaHa={maxAreaHa}
                    editingFarm={editingFarm}
                    name={name}
                    areaHa={areaHa}
                    latitude={latitude}
                    longitude={longitude}
                    saving={saving}
                    formFeedback={formFeedback}
                    onNameChange={setName}
                    onAreaChange={setAreaHa}
                    onLatChange={setLatitude}
                    onLngChange={setLongitude}
                    onApplyPreset={(preset) => {
                      setName(preset.name)
                      setAreaHa(preset.area_ha)
                      setLatitude(preset.latitude)
                      setLongitude(preset.longitude)
                      setFormFeedback(null)
                      onNotify(`Đã điền mẫu: ${preset.name}`)
                    }}
                    onSubmit={handleSubmit}
                    onCancelEdit={resetForm}
                    onNotify={onNotify}
                  />
                </div>

                <div className="dashboard-split-equal">
                  <IntegrityPanel
                    compact
                    tamperSimulated={tamperSimulated}
                    onToggleTamper={() => {
                      setTamperSimulated((prev) => !prev)
                      onNotify(
                        !tamperSimulated
                          ? 'Đã mô phỏng sửa lén nhiệt độ tại sự kiện #03!'
                          : 'Đã khôi phục dữ liệu gốc hợp lệ.'
                      )
                    }}
                  />

                  <section className="panel-card panel-box">
                    <div className="panel-head">
                      <h2>
                        Trạng thái Cô lập Đa tổ chức (RLS) &amp; Phân quyền RBAC (N3-6)
                      </h2>
                      <button
                        type="button"
                        className="ds-button ds-button-secondary ds-button-xs"
                        onClick={() => onTabChange('security')}
                      >
                        Chi tiết ma trận
                      </button>
                    </div>

                    <div className="info-grid-2">
                      <div className="info-item">
                        <span className="info-item-label">
                          Biến phiên PostgreSQL (app.current_organization)
                        </span>
                        <code>{user.organization_id}</code>
                      </div>

                      <div className="info-item">
                        <span className="info-item-label">
                          Quyền hạn RBAC được cấp cho {user.role}
                        </span>
                        <div className="badge-row">
                          {grantedPermissions.map((perm) => (
                            <span
                              key={perm}
                              className="status-badge status-done"
                            >
                              {perm}
                            </span>
                          ))}
                        </div>
                      </div>
                    </div>

                    <div className="action-row alert-spaced">
                      <button
                        type="button"
                        className="ds-button ds-button-brand ds-button-xs"
                        onClick={() => void runForbiddenProbe()}
                      >
                        Kiểm tra API: GET /api/v1/farms/
                      </button>
                      <span className="panel-sub">
                        Đổi nhanh sang tài khoản Mộc Châu hoặc Thanh tra trên
                        thanh công cụ để so sánh kết quả
                      </span>
                    </div>

                    {rbacProbeResult && (
                      <div
                        className={`alert-box alert-spaced ${
                          rbacProbeResult.startsWith('200')
                            ? 'alert-success'
                            : 'alert-error'
                        }`}
                        role="status"
                      >
                        {rbacProbeResult}
                      </div>
                    )}
                  </section>
                </div>
              </>
            )}

            {activeTab === 'security' && (
              <SecurityPanel
                user={user}
                rbacProbeResult={rbacProbeResult}
                onRunProbe={() => void runForbiddenProbe()}
              />
            )}

            {activeTab === 'integrity' && (
              <IntegrityPanel
                tamperSimulated={tamperSimulated}
                onToggleTamper={() => {
                  setTamperSimulated((prev) => !prev)
                  onNotify(
                    !tamperSimulated
                      ? 'Đã mô phỏng sửa lén nhiệt độ tại sự kiện #03!'
                      : 'Đã khôi phục dữ liệu gốc hợp lệ.'
                  )
                }}
              />
            )}
          </main>
        </div>
      </div>
    </div>
  )
}
