import { AuditPanel } from './AuditPanel'
import {
  ORG_TYPE_LABELS,
  ROLE_LABELS,
  ROLE_PERMISSIONS,
  type RoleCode,
  type SessionUser,
} from '../types'

interface SecurityPanelProps {
  user: SessionUser
  rbacProbeResult: string | null
  onRunProbe: () => void
}

const ALL_ROLES: RoleCode[] = [
  'system_admin',
  'organization_admin',
  'grower',
  'inspector',
  'cooperative',
  'transporter',
  'distributor',
]

function PermissionBadge({
  allowed,
  granted,
  denied = '—',
}: {
  allowed: boolean
  granted: string
  denied?: string
}) {
  return (
    <span className={`status-badge ${allowed ? 'status-done' : 'status-neutral'}`}>
      {allowed ? granted : denied}
    </span>
  )
}

export function SecurityPanel({
  user,
  rbacProbeResult,
  onRunProbe,
}: SecurityPanelProps) {
  const grantedPermissions = ROLE_PERMISSIONS[user.role] ?? []

  return (
    <div className="dashboard-split-equal security-panel-layout">
      <section className="panel-card panel-box">
        <div className="panel-head">
          <h2>Ngữ cảnh Phiên &amp; Cô lập Đa tổ chức (PostgreSQL RLS)</h2>
          <span className="status-badge status-done">Cô lập dữ liệu bằng RLS</span>
        </div>

        <div className="info-grid-2">
          <div className="info-item">
            <span className="info-item-label">Tài khoản xác thực</span>
            <strong className="info-item-value">{user.full_name}</strong>
            <div className="panel-sub">{user.email}</div>
          </div>

          <div className="info-item">
            <span className="info-item-label">Đơn vị chủ quản (Tenant)</span>
            <strong className="info-item-value">{user.organization_name}</strong>
            <div className="panel-sub">
              Loại hình: {ORG_TYPE_LABELS[user.organization_type]}
            </div>
          </div>

          <div className="info-item">
            <span className="info-item-label">
              Biến phiên DB (app.current_organization)
            </span>
            <code>{user.organization_id}</code>
          </div>

          <div className="info-item">
            <span className="info-item-label">Quyền RBAC hiện tại</span>
            <div className="badge-row">
              {grantedPermissions.map((perm) => (
                <span key={perm} className="status-badge status-done">
                  {perm}
                </span>
              ))}
            </div>
          </div>
        </div>

        <p className="panel-sub security-context-note">
          {`Phiên hiện tại được gắn với đơn vị ${user.organization_name}. Backend kiểm tra quyền theo vai trò; PostgreSQL RLS tiếp tục giới hạn bản ghi theo đơn vị hoặc đơn vị đang giữ lô. Chỉ quản trị hệ thống và thanh tra được đọc dữ liệu toàn cục theo phạm vi được cấp.`}
        </p>

        <div className="action-row alert-spaced">
          <button
            type="button"
            className="ds-button ds-button-brand ds-button-sm"
            onClick={onRunProbe}
          >
            Kiểm tra quyền đọc vùng trồng
          </button>
          <span className="panel-sub">
            Kiểm tra phản hồi 200 OK hoặc 403 Forbidden từ máy chủ
          </span>
        </div>

        {rbacProbeResult && (
          <div
            className={`alert-box alert-spaced ${
              rbacProbeResult.startsWith('200') ? 'alert-success' : 'alert-error'
            }`}
            role="status"
          >
            {rbacProbeResult}
          </div>
        )}
      </section>

      <section className="data-table-wrapper panel-card">
        <div className="data-table-header">
          <div>
            <h2 className="section-title">
              Ma trận phân quyền
            </h2>
            <p className="panel-sub">
              So sánh quyền theo vai trò. Dữ liệu lô được giới hạn theo đơn vị đang giữ; danh mục nông sản dùng chung chỉ quản trị hệ thống được sửa.
            </p>
          </div>
        </div>

        <div className="table-scroll">
          <table className="data-table security-matrix">
            <thead>
              <tr>
                <th>Vai trò</th>
                <th>Vùng trồng</th>
                <th>Lô hàng</th>
                <th>Nông sản</th>
                <th>Sự kiện</th>
                <th>Bàn giao</th>
                <th>Bảo mật</th>
              </tr>
            </thead>
            <tbody>
              {ALL_ROLES.map((roleCode) => {
                const perms = ROLE_PERMISSIONS[roleCode] ?? []
                const isCurrent = user.role === roleCode
                const canReadFarms =
                  perms.includes('farms:read') || perms.includes('farms:read_all')
                return (
                  <tr
                    key={roleCode}
                    className={isCurrent ? 'row-editing' : undefined}
                  >
                    <th scope="row" className="cell-strong">
                      {ROLE_LABELS[roleCode]}
                      {isCurrent && <div><span className="status-badge status-done">Vai trò của bạn</span></div>}
                    </th>
                    <td data-label="Vùng trồng">
                      <PermissionBadge
                        allowed={canReadFarms}
                        granted={perms.includes('farms:read_all') ? 'Xem toàn cục' : 'Xem đơn vị'}
                        denied="Không truy cập"
                      />
                      <PermissionBadge
                        allowed={perms.includes('farms:write')}
                        granted="Sửa"
                        denied={canReadFarms ? 'Chỉ xem' : '—'}
                      />
                    </td>
                    <td data-label="Lô hàng">
                      <PermissionBadge
                        allowed={perms.includes('lots:read') || perms.includes('lots:read_all')}
                        granted={perms.includes('lots:read_all') ? 'Xem toàn cục' : 'Lô đang giữ'}
                        denied="Không xem"
                      />
                      <PermissionBadge
                        allowed={perms.includes('lots:create')}
                        granted="Tạo lô"
                        denied="Không tạo"
                      />
                    </td>
                    <td data-label="Nông sản">
                      <PermissionBadge
                        allowed={perms.includes('products:write')}
                        granted="Sửa danh mục"
                        denied={perms.includes('products:read') ? 'Chỉ xem' : 'Không truy cập'}
                      />
                    </td>
                    <td data-label="Sự kiện">
                      <PermissionBadge
                        allowed={perms.includes('events:create')}
                        granted="Ghi sự kiện"
                        denied={perms.includes('events:read') || perms.includes('events:read_all') ? 'Chỉ xem' : 'Không truy cập'}
                      />
                      <PermissionBadge
                        allowed={perms.includes('events:verify')}
                        granted="Kiểm tra"
                        denied="Không kiểm tra"
                      />
                    </td>
                    <td data-label="Bàn giao">
                      <PermissionBadge
                        allowed={perms.includes('handovers:create')}
                        granted="Gửi yêu cầu"
                        denied="Không gửi"
                      />
                      <PermissionBadge
                        allowed={perms.includes('handovers:resolve')}
                        granted="Xác nhận / từ chối"
                        denied="Không xử lý"
                      />
                    </td>
                    <td data-label="Bảo mật">
                      <PermissionBadge
                        allowed={perms.includes('security:read')}
                        granted="Xem ma trận"
                        denied="Không xem"
                      />
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      </section>
      {user.role === 'system_admin' && <AuditPanel />}
    </div>
  )
}
