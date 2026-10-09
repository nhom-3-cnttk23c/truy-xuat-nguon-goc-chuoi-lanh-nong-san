import type {
  CreateEventRequest,
  Farm,
  FarmPayload,
  HealthResponse,
  LoginRequest,
  LotListParams,
  Lot,
  LotPage,
  LotPayload,
  LotEvent,
  Product,
  ProductPayload,
  SessionUser,
  IntegrityCheckRecord,
  EventHistory,
  Handover,
  HandoverPayload,
  OrganizationOption,
  LotSplitRequest,
  LotSplitResponse,
  LotOriginTrace,
} from '../types'


function resolveBaseUrl(): string {
  const envUrl = import.meta.env.VITE_API_BASE_URL
  if (envUrl) {
    return envUrl.replace(/\/$/, '')
  }
  if (import.meta.env.DEV) {
    return ''
  }
  if (
    typeof window !== 'undefined' &&
    window.location.hostname.endsWith('.onrender.com')
  ) {
    return 'https://ttcs-backend-staging.onrender.com'
  }
  return 'https://ttcs-backend-staging.onrender.com'
}

export const API_BASE_URL = resolveBaseUrl()

export class ApiError extends Error {
  status: number
  fieldErrors: Record<string, string>

  constructor(
    status: number,
    message: string,
    fieldErrors: Record<string, string> = {},
  ) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.fieldErrors = fieldErrors
  }
}


const SESSION_STORAGE_KEY = 'agrochain_session_token'

export function getStoredSessionToken(): string | null {
  try {
    return sessionStorage.getItem(SESSION_STORAGE_KEY)
  } catch {
    return null
  }
}

export function setStoredSessionToken(token: string | null): void {
  try {
    if (token) {
      sessionStorage.setItem(SESSION_STORAGE_KEY, token)
    } else {
      sessionStorage.removeItem(SESSION_STORAGE_KEY)
    }
  } catch {
    // Ignore storage errors in restricted contexts
  }
}

async function parseApiError(response: Response): Promise<ApiError> {
  try {
    const body = (await response.json()) as {
      detail?: string | Array<{ msg?: string; loc?: Array<string | number> }>
    }
    if (typeof body.detail === 'string') {
      return new ApiError(response.status, body.detail)
    }
    if (Array.isArray(body.detail) && body.detail.length > 0) {
      const fieldErrors: Record<string, string> = {}
      for (const item of body.detail) {
        const field = item.loc?.find(
          (part) => typeof part === 'string' && part !== 'body',
        )
        if (field) fieldErrors[String(field)] = item.msg || 'Dữ liệu không hợp lệ'
      }
      const message = body.detail
        .map((item) => item.msg || 'Dữ liệu không hợp lệ')
        .join('; ')
      return new ApiError(response.status, message, fieldErrors)
    }
  } catch {
    // Fallback to status text below
  }
  return new ApiError(
    response.status,
    `Lỗi HTTP ${response.status}: ${response.statusText || 'Yêu cầu thất bại'}`,
  )
}

export async function request<T>(
  path: string,
  options: RequestInit = {}
): Promise<T> {
  const headers = new Headers(options.headers)
  if (!headers.has('Content-Type') && options.body) {
    headers.set('Content-Type', 'application/json')
  }

  headers.set('X-Client-Type', 'web-spa')

  const storedToken = getStoredSessionToken()
  if (storedToken && !headers.has('Authorization')) {
    headers.set('Authorization', `Bearer ${storedToken}`)
  }

  let response: Response
  try {
    response = await fetch(`${API_BASE_URL}${path}`, {
      ...options,
      headers,
      credentials: 'include',
    })
  } catch (err) {
    if (err instanceof Error && err.name === 'AbortError') {
      throw err
    }
    const isOffline = typeof navigator !== 'undefined' && !navigator.onLine
    const msg = isOffline
      ? 'Mất kết nối Internet. Vui lòng kiểm tra lại kết nối mạng của bạn.'
      : 'Không thể kết nối đến máy chủ API. Vui lòng thử lại sau vài giây (máy chủ có thể đang khởi động).'
    throw new ApiError(0, msg)
  }

  const authHeader = response.headers.get('Authorization')
  if (authHeader && authHeader.startsWith('Bearer ')) {
    setStoredSessionToken(authHeader.substring(7).trim())
  }

  if (!response.ok) {
    if (
      response.status === 401 &&
      path !== '/api/v1/auth/login' &&
      path !== '/api/v1/auth/me' &&
      typeof window !== 'undefined' &&
      window.location.pathname !== '/login'
    ) {
      setStoredSessionToken(null)
      const protectedPaths = new Set([
        '/lots',
        '/handovers',
        '/products',
        '/farms',
        '/products',
        '/security',
        '/integrity',
      ])
      const currentPath = `${window.location.pathname}${window.location.search}${window.location.hash}`
      const returnPath = protectedPaths.has(window.location.pathname)
        ? currentPath
        : '/lots'
      window.location.replace(
        `/login?next=${encodeURIComponent(returnPath)}`
      )
    }
    throw await parseApiError(response)
  }

  if (response.status === 204) {
    return undefined as T
  }

  try {
    return (await response.json()) as T
  } catch {
    throw new ApiError(
      response.status,
      'Dữ liệu phản hồi từ máy chủ không hợp lệ.'
    )
  }
}

export const checkHealth = () =>
  request<HealthResponse>(API_BASE_URL ? '/' : '/health')

export const login = (payload: LoginRequest) =>
  request<SessionUser>('/api/v1/auth/login', {
    method: 'POST',
    body: JSON.stringify(payload),
  })

export const getCurrentUser = () => request<SessionUser>('/api/v1/auth/me')

export const logout = async (): Promise<void> => {
  try {
    await request<void>('/api/v1/auth/logout', { method: 'POST' })
  } finally {
    setStoredSessionToken(null)
  }
}

export const getFarms = () => request<Farm[]>('/api/v1/farms/')

function normalizeLotPage(response: unknown): LotPage {
  if (Array.isArray(response)) {
    // Older staging API versions return the first page as a bare list.
    return { items: response as Lot[], next_cursor: null }
  }

  if (response && typeof response === 'object') {
    const page = response as Partial<LotPage>
    if (Array.isArray(page.items)) {
      return {
        items: page.items,
        next_cursor: typeof page.next_cursor === 'string' ? page.next_cursor : null,
      }
    }
  }

  throw new ApiError(
    502,
    'Máy chủ trả về danh sách lô không đúng định dạng. Vui lòng tải lại sau khi đồng bộ API.',
  )
}

export const getLots = async (params: LotListParams = {}): Promise<LotPage> => {
  const query = new URLSearchParams()
  if (params.q?.trim()) query.set('q', params.q.trim())
  if (params.product_id) query.set('product_id', params.product_id)
  if (params.cursor) query.set('cursor', params.cursor)
  query.set('page_size', String(params.page_size ?? 20))
  const response = await request<unknown>(`/api/v1/lots/?${query.toString()}`)
  return normalizeLotPage(response)
}

export const getLot = (lotId: string) =>
  request<Lot>(`/api/v1/lots/${lotId}`)

export const getProducts = () => request<Product[]>('/api/v1/products/')

export const createProduct = (payload: ProductPayload) =>
  request<Product>('/api/v1/products/', {
    method: 'POST',
    body: JSON.stringify(payload),
  })

export const updateProduct = (productId: string, payload: ProductPayload) =>
  request<Product>(`/api/v1/products/${productId}`, {
    method: 'PUT',
    body: JSON.stringify(payload),
  })

export const getHandoverOrganizations = () =>
  request<OrganizationOption[]>('/api/v1/handovers/organizations')

export const getIncomingHandovers = () =>
  request<Handover[]>('/api/v1/handovers/incoming')

export const getOutgoingHandovers = () =>
  request<Handover[]>('/api/v1/handovers/outgoing')

export const createHandover = (payload: HandoverPayload) =>
  request<Handover>('/api/v1/handovers/', {
    method: 'POST',
    body: JSON.stringify(payload),
  })

export const acceptHandover = (handoverId: string) =>
  request<{ id: string; status: 'accepted' }>(`/api/v1/handovers/${handoverId}/accept`, { method: 'POST' })

export const rejectHandover = (handoverId: string, reason: string) =>
  request<{ id: string; status: 'rejected' }>(`/api/v1/handovers/${handoverId}/reject`, {
    method: 'POST',
    body: JSON.stringify({ reason }),
  })

export const createLot = (payload: LotPayload) =>
  request<Lot>('/api/v1/lots/', {
    method: 'POST',
    body: JSON.stringify(payload),
  })

export const getFarm = (farmId: string) =>
  request<Farm>(`/api/v1/farms/${farmId}`)

export const createFarm = (payload: FarmPayload) =>
  request<Farm>('/api/v1/farms/', {
    method: 'POST',
    body: JSON.stringify(payload),
  })

export const updateFarm = (farmId: string, payload: FarmPayload) =>
  request<Farm>(`/api/v1/farms/${farmId}`, {
    method: 'PUT',
    body: JSON.stringify(payload),
  })

export const getEvents = (lotId?: string) => {
  const query = lotId ? `?lot_id=${encodeURIComponent(lotId)}` : ''
  return request<LotEvent[]>(`/api/v1/events/${query}`)
}

export const verifyLotIntegrity = (lotId: string) =>
  request<IntegrityCheckRecord>(`/api/v1/events/lots/${lotId}/integrity-checks`, {
    method: 'POST',
  })

export const getIntegrityCheckHistory = (lotId: string) =>
  request<IntegrityCheckRecord[]>(`/api/v1/events/lots/${lotId}/integrity-checks`)

export const getLotHistory = (lotId: string) =>
  request<EventHistory>(`/api/v1/events/lots/${lotId}/history`)

export const getEvent = (eventId: string) =>
  request<LotEvent>(`/api/v1/events/${eventId}`)

export const createEvent = (payload: CreateEventRequest) =>
  request<LotEvent>('/api/v1/events/', {
    method: 'POST',
    body: JSON.stringify(payload),
  })

// ARCHITECTURAL GUARANTEE (N3-21):
// There are NO updateEvent or deleteEvent functions.
// Events are strictly append-only.

export const splitLot = (lotId: string, payload: LotSplitRequest) =>
  request<LotSplitResponse>(`/api/v1/lots/${lotId}/split`, {
    method: 'POST',
    body: JSON.stringify(payload),
  })

export const getLotChildren = (lotId: string) =>
  request<Lot[]>(`/api/v1/lots/${lotId}/children`)

export const getLotParents = (lotId: string) =>
  request<Lot[]>(`/api/v1/lots/${lotId}/parents`)

export const traceLotOrigin = (lotId: string) =>
  request<LotOriginTrace>(`/api/v1/lots/${lotId}/lineage/origin`)

