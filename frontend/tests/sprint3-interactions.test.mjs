import assert from 'node:assert/strict'
import { after, afterEach, beforeEach, test } from 'node:test'
import { fileURLToPath } from 'node:url'
import { JSDOM } from 'jsdom'
import { createServer } from 'vite'
import React, { act } from 'react'

// Real React state/effects in a simulated DOM. Every HTTP request is mocked;
// no browser, API or HTTP listener is started. This does not verify layout.
const dom = new JSDOM('<div id="root"></div>', {url: 'http://test.local/lots', pretendToBeVisual: true})
for (const key of ['window', 'document', 'HTMLElement', 'HTMLDivElement', 'SVGElement', 'Element', 'Node', 'Event', 'MouseEvent', 'sessionStorage', 'getComputedStyle', 'requestAnimationFrame', 'cancelAnimationFrame']) globalThis[key] = dom.window[key]
globalThis.ResizeObserver = dom.window.ResizeObserver = class { observe() {} unobserve() {} disconnect() {} }
globalThis.IS_REACT_ACT_ENVIRONMENT = true
const { createRoot } = await import('react-dom/client')
const server = await createServer({root: fileURLToPath(new URL('..', import.meta.url)), configFile: false, optimizeDeps: {noDiscovery: true, include: []}, server: {middlewareMode: true, hmr: false}})
const originalFetch = globalThis.fetch
let root, routes, calls
beforeEach(() => {
  routes = new Map(); calls = []
  dom.window.history.replaceState({}, '', '/lots')
  globalThis.fetch = async (url, options = {}) => {
    const path = new URL(url, dom.window.location.href).pathname
    const key = `${options.method ?? 'GET'} ${path}`
    calls.push({key, body: options.body ? JSON.parse(options.body) : null, url: String(url)})
    assert.ok(routes.has(key), `Unexpected request: ${key}`)
    const value = routes.get(key)
    if (value instanceof Response) return value
    return new Response(JSON.stringify(typeof value === 'function' ? value() : value), {headers: {'Content-Type': 'application/json'}})
  }
  root = createRoot(document.getElementById('root'))
})
afterEach(async () => { await act(async () => {root.unmount(); await new Promise(resolve => setTimeout(resolve, 50))}) })
after(async () => { globalThis.fetch = originalFetch; await server.close(); dom.window.close() })
const load = async name => (await server.ssrLoadModule(`/src/components/${name}.tsx`))[name]
const mount = async (name, props) => { const component = await load(name); await act(async () => {root.render(React.createElement(component, props))}) }
const button = label => [...document.querySelectorAll('button')].find(item => item.textContent === label)
const click = async element => { assert.ok(element); await act(() => element.click()) }
const waitFor = async condition => {
  const deadline = Date.now() + 5000
  while (!condition() && Date.now() < deadline) await act(async () => {await new Promise(resolve => setTimeout(resolve, 20))})
  assert.ok(condition(), 'Expected component state did not appear within 5 seconds')
}
const input = async (element, value) => {
  assert.ok(element)
  await act(() => {
    Object.getOwnPropertyDescriptor(dom.window.HTMLInputElement.prototype, 'value').set.call(element, value)
    element.dispatchEvent(new dom.window.Event('input', {bubbles: true}))
  })
}
const submit = async () => { await act(async () => document.querySelector('form').dispatchEvent(new dom.window.Event('submit', {bubbles: true, cancelable: true}))) }
const lot = {id: '89d69962-fa86-59d7-8adf-26cb56fa9ef4', lot_code: 'XOAI-001', name: 'Xoài Cát Chu', product_id: 'product', product: {id: 'product', name: 'Xoài Cát Chu', unit: 'kg'}, current_holder_organization_id: 'own', remaining_quantity: '40.000', quantity: '40.000', status: 'active'}

test('N3-117: split adds/removes rows, blocks excess stock and shows every child code', async () => {
  routes.set('GET /api/v1/lots/', {items: [], next_cursor: null})
  const children = [{...lot, id: 'child-1', lot_code: 'XOAI-002', quantity: '12.000'}, {...lot, id: 'child-2', lot_code: 'XOAI-003', quantity: '8.000'}]
  routes.set(`POST /api/v1/lots/${lot.id}/split`, {parent: lot, children})
  await mount('LotTransformForm', {lot, canManageDistribution: false, onCompleted: () => {}})
  await click(button('Thêm lô con'))
  assert.equal(document.querySelectorAll('.transform-row').length, 3)
  await click(button('Bỏ lô con 3'))
  const amounts = document.querySelectorAll('input[inputmode="decimal"]')
  await input(amounts[0], '30'); await input(amounts[1], '20')
  assert.equal(button('Xác nhận tách lô').disabled, true)
  assert.match(document.body.textContent, /Vượt 10.000/)
  assert.equal(calls.filter(item => item.key.startsWith('POST')).length, 0)
  await input(amounts[0], '12'); await input(amounts[1], '8')
  assert.equal(button('Xác nhận tách lô').disabled, false)
  await submit()
  assert.deepEqual([...document.querySelectorAll('.result-lots button')].map(item => item.textContent), ['XOAI-002', 'XOAI-003'])
  assert.deepEqual(calls.find(item => item.key.startsWith('POST')).body.children.map(item => item.quantity), ['12', '8'])
})

test('N3-135: merge validates each parent amount, sends selected parents and shows new code', async () => {
  const other = {...lot, id: '89d69962-fa86-59d7-8adf-26cb56fa9ef5', lot_code: 'XOAI-004', remaining_quantity: '25.000'}
  routes.set('GET /api/v1/lots/', {items: [other], next_cursor: null})
  routes.set('POST /api/v1/lots/merge', {...lot, id: 'merged', lot_code: 'XOAI-005'})
  await mount('LotTransformForm', {lot, initialMode: 'merge', canManageDistribution: false, onCompleted: () => {}})
  assert.equal(button('Xác nhận gộp lô').disabled, true)
  await click(document.querySelector('[aria-label="Chọn XOAI-004"]'))
  assert.equal(button('Xác nhận gộp lô').disabled, false)
  const amounts = document.querySelectorAll('input[inputmode="decimal"]')
  await input(amounts[1], '26')
  assert.equal(button('Xác nhận gộp lô').disabled, true)
  await input(amounts[1], '15')
  await submit()
  assert.equal(document.querySelector('.result-lots button').textContent, 'XOAI-005')
  assert.deepEqual(calls.find(item => item.key.startsWith('POST')).body.parents, [{lot_id: lot.id, quantity: '40.000'}, {lot_id: other.id, quantity: '15'}])
})

test('N3-135: list selection sets product filter and disables incompatible lots with explanation', async () => {
  const other = {...lot, id: 'different', product_id: 'other', lot_code: 'CAM-001'}
  const compatible = {...lot, id: '89d69962-fa86-59d7-8adf-26cb56fa9ef5', lot_code: 'XOAI-004'}
  routes.set('GET /api/v1/products/', [lot.product, {id: 'other', name: 'Cam sành', unit: 'kg'}])
  routes.set('GET /api/v1/lots/', {items: [lot, other, compatible], next_cursor: null})
  await mount('LotsPanel', {canReadLots: true, canCreateLots: false, canTransform: true, organizationId: 'own', onOpenLot: () => {}})
  await act(async () => {await new Promise(resolve => setTimeout(resolve, 300))})
  await click(document.querySelector('[aria-label="Chọn XOAI-001"]'))
  assert.equal(document.querySelector('select').value, lot.product_id)
  await act(async () => {await new Promise(resolve => setTimeout(resolve, 300))})
  const checkbox = document.querySelector('[aria-label^="Chọn CAM-001"]')
  assert.equal(checkbox.disabled, true)
  assert.match(document.body.textContent, /Sản phẩm khác với lô đã chọn/)
  assert.equal(document.querySelector('a[href*="task=merge"]'), null)
  assert.ok(calls.some(item => item.url.includes('product_id=product')))
  await click(document.querySelector('[aria-label="Chọn XOAI-004"]'))
  const link = document.querySelector('a[href*="task=merge"]')
  assert.equal(new URL(link.href).searchParams.get('parents'), `${lot.id},${compatible.id}`)
})

test('N3-135: selected parents from the list are loaded and prefilled in the merge form', async () => {
  const other = {...lot, id: '89d69962-fa86-59d7-8adf-26cb56fa9ef5', lot_code: 'XOAI-004', remaining_quantity: '25.000'}
  dom.window.history.replaceState({}, '', `/lots/${lot.id}?task=merge&parents=${lot.id},${other.id}`)
  routes.set(`GET /api/v1/lots/${other.id}`, other)
  routes.set('GET /api/v1/lots/', {items: [], next_cursor: null})
  routes.set('POST /api/v1/lots/merge', {...lot, id: 'merged', lot_code: 'XOAI-005'})
  await mount('LotTransformForm', {lot, initialMode: 'merge', canManageDistribution: false, onCompleted: () => {}})
  assert.equal(document.querySelector('[aria-label="Chọn XOAI-004"]').checked, true)
  assert.equal(document.querySelectorAll('input[inputmode="decimal"]')[1].value, '25.000')
  await submit()
  assert.deepEqual(calls.find(item => item.key.startsWith('POST')).body.parents.map(item => item.lot_id), [lot.id, other.id])
})

const farms = [{id: 'farm-1', name: 'Vườn xoài Cao Lãnh'}, {id: 'farm-2', name: 'Vườn xoài Thanh Bình'}]
const detailProps = {lotId: lot.id, organizationId: 'own', canReadEvents: true, canCreateEvents: true, canCreateHandover: true, canResolveHandover: true, canTransform: true, canManageDistribution: false, onOpenLot: () => {}, onBack: () => {}}
const seedDetails = (status = 'active') => {
  routes.set(`GET /api/v1/lots/${lot.id}`, {...lot, status, parents: [], children: [], direct_farms: [], root_farms: farms, event_count: 1})
  routes.set(`GET /api/v1/events/lots/${lot.id}/history`, {events: [{id: 'event', sequence_number: 1, event_type: 'cold_storage', recorded_at: '2026-10-12T00:00:00Z', organization_name: 'HTX Cao Lãnh', payload: {}, prev_hash: '0'.repeat(64), event_hash: 'a'.repeat(64)}], total: 1, next_cursor: null, integrity: {valid: true, checked_events: 1}})
  routes.set('GET /api/v1/handovers/incoming', [])
  routes.set('GET /api/v1/handovers/outgoing', [])
  routes.set('GET /api/v1/handovers/organizations', [])
  const roots = [{...lot, id: 'root-1', lot_code: 'XOAI-GOC-1'}, {...lot, id: 'root-2', lot_code: 'XOAI-GOC-2'}]
  routes.set(`GET /api/v1/lots/${lot.id}/lineage`, {selected_lot_id: lot.id, nodes: [lot, ...roots], edges: roots.map(parent => ({id: parent.id, parent_lot_id: parent.id, child_lot_id: lot.id, quantity: '20.000'})), roots: roots.map(parent => parent.id), root_farms: farms})
}

test('N3-134/N3-125: all three tabs switch content and origins show every root farm', async () => {
  seedDetails()
  await mount('LotDetailPanel', detailProps)
  assert.equal(document.querySelectorAll('[role="tab"]').length, 3)
  assert.ok(document.querySelector('a[href*="task=split"]'))
  await click(document.getElementById('tab-history'))
  assert.equal(document.querySelector('[role="tabpanel"]').getAttribute('aria-labelledby'), 'tab-history')
  assert.equal(document.querySelectorAll('.event-details').length, 1)
  await click(document.getElementById('tab-origins'))
  await waitFor(() => document.querySelector('.source-table'))
  const origins = document.getElementById('lineage-title').closest('section')
  assert.match(origins.textContent, /Vườn xoài Cao Lãnh/)
  assert.match(origins.textContent, /Vườn xoài Thanh Bình/)
  assert.equal(origins.querySelectorAll('.source-table tbody tr').length, 3)
  await click(document.getElementById('tab-overview'))
  assert.equal(document.querySelectorAll('.event-details').length, 0)
  assert.match(document.querySelector('[role="tabpanel"]').textContent, /Thao tác với lô/)
})

test('N3-134: pending handover hides split, merge, event and handover actions', async () => {
  seedDetails('pending_handover')
  await mount('LotDetailPanel', detailProps)
  assert.equal(document.querySelectorAll('a[href*="task=split"],a[href*="task=merge"],a[href*="task=handover"],a[href*="task=event"]').length, 0)
  assert.match(document.body.textContent, /chờ bàn giao/i)
})

test('N3-125: denied lot read reports the API error without revealing lot details', async () => {
  seedDetails()
  routes.set(`GET /api/v1/lots/${lot.id}`, new Response(JSON.stringify({detail: 'Bạn không có quyền truy cập dữ liệu của tổ chức khác.'}), {status: 403, headers: {'Content-Type': 'application/json'}}))
  await mount('LotDetailPanel', detailProps)
  assert.match(document.querySelector('[role="alert"]').textContent, /không có quyền/)
  assert.equal(document.getElementById('lot-detail-title'), null)
})

const overdue = {id: 'handover', lot_id: lot.id, lot_code: lot.lot_code, lot_name: lot.name, from_organization_name: 'HTX Cao Lãnh', to_organization_name: 'Kho Sa Đéc', status: 'pending', created_at: '2026-10-09T00:00:00Z', overdue_at: '2026-10-11T00:00:00Z'}
const seedHandovers = () => {
  routes.set('GET /api/v1/handovers/incoming', [overdue])
  routes.set('GET /api/v1/handovers/outgoing', [overdue])
  routes.set('GET /api/v1/handovers/organizations', [])
  routes.set('GET /api/v1/lots/', {items: [], next_cursor: null})
}

test('N3-132: incoming and outgoing lists both show overdue text, not only color', async () => {
  seedHandovers()
  await mount('HandoversPanel', {canCreate: true, canResolve: true})
  assert.match(document.querySelector('.handover-card [role="status"]').textContent, /Quá hạn xác nhận bàn giao/)
  await click(button('Đã gửi'))
  assert.match(document.querySelector('.handover-card [role="status"]').textContent, /Quá hạn xác nhận bàn giao/)
  assert.match(document.querySelector('.handover-card').textContent, /Đến Kho Sa Đéc/)
})

test('N3-132: overdue request can still be accepted and the refreshed list shows accepted status', async () => {
  seedHandovers()
  dom.window.history.replaceState({}, '', '/handovers?task=review&id=handover')
  routes.set('POST /api/v1/handovers/handover/accept', () => {
    routes.set('GET /api/v1/handovers/incoming', [{...overdue, status: 'accepted'}])
    routes.set('GET /api/v1/handovers/outgoing', [])
    return {id: 'handover', status: 'accepted'}
  })
  await mount('HandoversPanel', {canCreate: false, canResolve: true})
  assert.equal(button('Xác nhận nhận lô').disabled, false)
  await click(button('Xác nhận nhận lô'))
  assert.equal(calls.filter(item => item.key === 'POST /api/v1/handovers/handover/accept').length, 1)
  assert.match(document.body.textContent, /Đã nhận lô XOAI-001/)
  assert.match(document.querySelector('.handover-status').textContent, /Đã nhận/)
  assert.equal(button('Xác nhận nhận lô'), undefined)
})

test('N3-132: sender lot detail includes the overdue handover notice', async () => {
  seedDetails('pending_handover')
  routes.set('GET /api/v1/handovers/outgoing', [overdue])
  await mount('LotDetailPanel', detailProps)
  assert.match(document.querySelector('[role="tabpanel"]').textContent, /Quá hạn xác nhận/)
})
