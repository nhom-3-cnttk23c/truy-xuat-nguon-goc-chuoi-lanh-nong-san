export type RoleCode =
  | 'grower'
  | 'cooperative'
  | 'transporter'
  | 'distributor'
  | 'inspector'
  | 'organization_admin'
  | 'system_admin'

export type OrganizationType =
  | 'farm'
  | 'cooperative'
  | 'transport'
  | 'distribution'
  | 'inspection'
  | 'administration'

export interface HealthResponse {
  status: string
  message: string
}

export interface LoginRequest {
  email: string
  password: string
}

export interface SessionUser {
  id: string
  email: string
  full_name: string
  organization_id: string
  organization_name: string
  organization_type: OrganizationType
  role: RoleCode
}

export interface Farm {
  id: string
  organization_id: string
  name: string
  area_ha: string
  latitude: string
  longitude: string
}

export interface FarmPayload {
  name: string
  area_ha: number | string
  latitude: number | string
  longitude: number | string
}

export interface Lot {
  id: string
  organization_id: string
  farm_id: string
  name: string
}

export interface LotEvent {
  id: string
  organization_id: string
  lot_id: string
  sequence_number: number
  event_type: string
  recorded_at: string
  payload: Record<string, unknown>
  prev_hash: string
  event_hash: string
}

export interface CreateEventRequest {
  lot_id: string
  event_type: string
  payload?: Record<string, unknown>
}

export const ROLE_LABELS: Record<RoleCode, string> = {
  grower: 'Nông hộ / Trang trại',
  cooperative: 'Hợp tác xã',
  transporter: 'Đơn vị vận chuyển',
  distributor: 'Nhà phân phối',
  inspector: 'Thanh tra viên',
  organization_admin: 'Quản trị đơn vị',
  system_admin: 'Quản trị hệ thống',
}

export const ORG_TYPE_LABELS: Record<OrganizationType, string> = {
  farm: 'Nông trại sản xuất',
  cooperative: 'Hợp tác xã',
  transport: 'Vận tải chuỗi lạnh',
  distribution: 'Trung tâm phân phối',
  inspection: 'Cơ quan thanh tra',
  administration: 'Quản trị vận hành',
}

export const ROLE_PERMISSIONS: Record<RoleCode, string[]> = {
  grower: [
    'auth:session',
    'farms:read',
    'farms:write',
    'lots:read',
    'events:read',
    'events:create',
  ],
  cooperative: ['auth:session', 'lots:read', 'events:read', 'events:create'],
  transporter: ['auth:session', 'lots:read', 'events:read', 'events:create'],
  distributor: ['auth:session', 'lots:read', 'events:read', 'events:create'],
  inspector: ['auth:session', 'lots:read_all', 'events:read_all'],
  organization_admin: [
    'auth:session',
    'farms:read',
    'farms:write',
    'lots:read',
    'events:read',
    'events:create',
  ],
  system_admin: ['auth:session'],
}

export function hasPermission(role: RoleCode, permission: string): boolean {
  const perms = ROLE_PERMISSIONS[role] ?? []
  if (perms.includes(permission)) {
    return true
  }
  if (permission === 'lots:read' && perms.includes('lots:read_all')) {
    return true
  }
  if (permission === 'events:read' && perms.includes('events:read_all')) {
    return true
  }
  return false
}

