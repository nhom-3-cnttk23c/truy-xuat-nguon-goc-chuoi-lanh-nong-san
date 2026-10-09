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
  lot_code: string | null
  product_id: string | null
  harvested_on: string | null
  quantity: string | null
  remaining_quantity: string
  current_holder_organization_id: string
  current_holder_organization_name: string
  status: 'active' | 'pending_handover' | 'closed'
  parent_batch_id: string | null
  lineage_depth: number
  root_harvest_id: string | null
  product: Product | null
}

export interface LotPage {
  items: Lot[]
  next_cursor: string | null
}

export type ProductUnit = 'kg' | 'tấn' | 'thùng'

export interface Product {
  id: string
  name: string
  unit: ProductUnit
}

export interface ProductPayload {
  name: string
  unit: ProductUnit
}

export interface OrganizationOption {
  id: string
  name: string
}

export interface Handover {
  id: string
  lot_id: string
  lot_code: string | null
  lot_name: string
  from_organization_id: string
  from_organization_name: string
  to_organization_id: string
  to_organization_name: string
  status: 'pending' | 'accepted' | 'rejected'
  note: string | null
  rejection_reason: string | null
  created_at: string
}

export interface HandoverPayload {
  lot_id: string
  to_organization_id: string
  note?: string
}

export interface LotPayload {
  farm_id: string
  product_id: string
  harvested_on: string
  quantity: string
}

export interface LotListParams {
  q?: string
  product_id?: string
  cursor?: string
  page_size?: number
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
  organization_name: string
}

export interface IntegrityIssue {
  sequence_number: number
  kind: string
}

export interface IntegrityReport {
  valid: boolean
  checked_events: number
  first_invalid_sequence: number | null
  issues: IntegrityIssue[]
}

export interface IntegrityCheckRecord extends IntegrityReport {
  id: string
  lot_id: string
  checked_at: string
}

export interface EventHistory {
  events: LotEvent[]
  integrity: IntegrityReport
}

export interface CreateEventRequest {
  lot_id: string
  event_type: string
  payload?: Record<string, unknown>
}

export interface SplitChildPayload {
  name: string
  quantity: string
}

export interface LotSplitRequest {
  children: SplitChildPayload[]
  note?: string
}

export interface LotSplitResponse {
  transaction_id: string
  parent_id: string
  children: Lot[]
}

export interface BatchRelation {
  id: string
  transaction_id: string
  parent_batch_id: string
  child_batch_id: string
  weight_transferred: string
  op_type: 'split' | 'merge'
  created_at: string
}

export interface BatchEvent {
  event_id: string
  batch_id: string
  event_type: string
  payload: Record<string, unknown>
  prev_hash: string
  hash: string
  actor_user_id: string
  transaction_id: string
  recorded_at: string
}

export interface LotOriginTrace {
  root_harvest_id: string
  root_harvest_name: string
  root_harvest_lot_code: string | null
  lineage_depth: number
  is_ancestor_visible: boolean
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
    'products:read',
    'lots:read',
    'lots:create',
    'events:read',
    'events:create',
    'handovers:create',
    'handovers:resolve',
  ],
  cooperative: [
    'auth:session',
    'products:read',
    'lots:read',
    'events:read',
    'events:create',
    'handovers:create',
    'handovers:resolve',
  ],
  transporter: [
    'auth:session',
    'products:read',
    'lots:read',
    'events:read',
    'events:create',
    'handovers:create',
    'handovers:resolve',
  ],
  distributor: [
    'auth:session',
    'products:read',
    'lots:read',
    'events:read',
    'events:create',
    'handovers:create',
    'handovers:resolve',
  ],
  inspector: [
    'auth:session',
    'products:read',
    'lots:read_all',
    'events:read_all',
    'events:verify',
  ],
  organization_admin: [
    'auth:session',
    'farms:read',
    'farms:write',
    'products:read',
    'lots:read',
    'lots:create',
    'events:read',
    'events:create',
    'handovers:create',
    'handovers:resolve',
  ],
  system_admin: [
    'auth:session',
    'farms:read',
    'farms:write',
    'farms:read_all',
    'lots:read',
    'lots:read_all',
    'events:read',
    'events:read_all',
    'events:verify',
    'products:read',
    'products:write',
    'products:read_all',
    'security:read',
  ],
}

export function hasPermission(role: RoleCode, permission: string): boolean {
  const perms = ROLE_PERMISSIONS[role] ?? []
  if (perms.includes(permission)) {
    return true
  }
  if (permission === 'farms:read' && perms.includes('farms:read_all')) {
    return true
  }
  if (permission === 'lots:read' && perms.includes('lots:read_all')) {
    return true
  }
  if (permission === 'events:read' && perms.includes('events:read_all')) {
    return true
  }
  if (permission === 'products:read' && perms.includes('products:read_all')) {
    return true
  }
  return false
}

