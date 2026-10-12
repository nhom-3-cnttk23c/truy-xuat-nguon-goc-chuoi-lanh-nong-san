import assert from 'node:assert/strict'
import { after, test } from 'node:test'
import { fileURLToPath } from 'node:url'
import { createServer } from 'vite'
import React from 'react'
import { renderToStaticMarkup } from 'react-dom/server'

// Offline rendering only: no browser, HTTP listener, API or effects are run.
const server = await createServer({root: fileURLToPath(new URL('..', import.meta.url)), cacheDir: fileURLToPath(new URL('../node_modules/.vite-task-tests', import.meta.url)), configFile: false, optimizeDeps: {noDiscovery: true, include: []}, server: {middlewareMode: true, hmr: false}})
after(() => server.close())
globalThis.window = {location: {search: ''}}
const load = async (name) => (await server.ssrLoadModule(`/src/components/${name}.tsx`))[name]
const html = (component, props) => renderToStaticMarkup(React.createElement(component, props))
const lot = {id: '89d69962-fa86-59d7-8adf-26cb56fa9ef4', remaining_quantity: '40.000', product: {unit: 'kg'}, current_holder_organization_id: 'own', status: 'active'}

test('task links stay in the current tab with a simple label', async () => {
  const output = html(await load('TaskLink'), {href: '/lots?task=create', children: 'Tạo lô'})
  assert.doesNotMatch(output, /target=|mở tab mới|↗/)
  assert.match(output, />Tạo lô<\/a>/)
})
test('split starts with empty amounts and disabled submission', async () => {
  window.location.search = '?task=split'
  const output = html(await load('LotTransformForm'), {lot, canManageDistribution: false, onCompleted: () => {}})
  assert.match(output, /Tổng khối lượng/)
  assert.match(output, /Lô nguồn sẽ còn 40.000/)
  assert.match(output, /disabled="">Xác nhận tách lô/)
})
test('merge starts in merge mode with disabled submission until valid candidates chosen', async () => {
  window.location.search = '?task=merge'
  const output = html(await load('LotTransformForm'), {lot, initialMode: 'merge', canManageDistribution: false, onCompleted: () => {}})
  assert.match(output, /Gộp cùng sản phẩm/)
  assert.match(output, /Các lô mẹ và phần khối lượng lấy ra/)
  assert.match(output, /disabled="">Xác nhận gộp lô/)
})
test('manual event form requires confirmation and excludes reserved business events', async () => {
  const output = html(await load('EventCreateForm'), {lot})
  assert.match(output, /disabled="">Lưu sự kiện/)
  assert.match(output, /không thể sửa hoặc xóa/)
  assert.doesNotMatch(output, /value="lot_split"|value="lot_consumed"|value="handover_accepted"/)
})
test('create-lot page reports missing permission without exposing a form', async () => {
  window.location.search = '?task=create'
  const output = html(await load('LotsPanel'), {canReadLots: true, canCreateLots: false, onOpenLot: () => {}})
  assert.match(output, /không có quyền tạo lô/)
  assert.doesNotMatch(output, /<form/)
})
test('location manager opens a separate task instead of inline fields', async () => {
  window.location.search = ''
  const output = html(await load('LocationsPanel'), {})
  assert.match(output, /href="\/lots\?task=locations"/)
  assert.doesNotMatch(output, /<form/)
})
test('demo guide offers twelve steps with role and expected-result instructions', async () => {
  const output = html(await load('DemoGuide'), {})
  assert.match(output, /12. Bàn giao quá hạn/)
  assert.match(output, /Tài khoản thực hiện/)
  assert.match(output, /Kết quả cần đối chiếu/)
  assert.match(output, /không tự động xác nhận nghiệm thu/)
})

test('merge candidates exclude other holders, products and unavailable lots across pages', async () => {
  const { eligibleMergeCandidates } = await server.ssrLoadModule('/src/utils/merge.ts')
  const source = {...lot, product_id: 'product'}
  const good = {...source, id: 'child'}
  const candidates = [good, {...good}, source, {...good, id: 'foreign', current_holder_organization_id: 'other'}, {...good, id: 'wrong', product_id: 'different'}, {...good, id: 'empty', remaining_quantity: '0.000'}, {...good, id: 'pending', status: 'pending_handover'}]
  assert.deepEqual(eligibleMergeCandidates(candidates, source).map(item => item.id), ['child'])
})

test('history renders ten rows and keeps optional verification details collapsed', async () => {
  const events = Array.from({length: 21}, (_, index) => ({id: String(index), sequence_number: index + 1, event_type: 'cold_storage', recorded_at: '2026-10-12T00:00:00Z', organization_name: 'Đơn vị demo', payload: {}, prev_hash: '0'.repeat(64), event_hash: 'a'.repeat(64)}))
  const output = html(await load('EventTimeline'), {events, lotName: 'Demo', integrity: {valid: true, checked_events: 21}})
  assert.equal((output.match(/class="event-details"/g) ?? []).length, 10)
  assert.match(output, /Trang 1\/3/)
  assert.doesNotMatch(output, /<details[^>]* open/)
  assert.match(output, /21 sự kiện/)
})

test('edit dialog provides an accessible temporary window and close action', async () => {
  const output = html(await load('EditDialog'), {title: 'Sửa nông sản', busy: true, onClose: () => {}, children: 'Thông tin'})
  assert.match(output, /<dialog[^>]*aria-label="Sửa nông sản"/)
  assert.match(output, /disabled=""[^>]*aria-label="Đóng hộp thoại"/)
  assert.doesNotMatch(output, /iframe|target=/)
})

test('product form opens as a dialog while the catalogue remains on the page', async () => {
  window.location.search = '?task=create'
  const output = html(await load('ProductManager'), {user: {role: 'system_admin'}})
  assert.match(output, /<dialog[^>]*aria-label="Thêm nông sản"/)
  assert.match(output, /<table class="data-table product-table"/)
  assert.match(output, /placeholder="Ví dụ: Xoài cát Hòa Lộc"/)
  assert.doesNotMatch(output, /target="_blank"/)
})
