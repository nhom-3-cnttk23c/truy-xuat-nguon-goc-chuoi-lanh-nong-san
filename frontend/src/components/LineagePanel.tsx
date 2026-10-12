import { useEffect, useMemo, useRef, useState } from 'react'
import { Background, Controls, Position, ReactFlow, type Edge, type Node } from '@xyflow/react'
import '@xyflow/react/dist/style.css'
import { getLineage, getLotHistory } from '../services/api'
import dagre from '@dagrejs/dagre'
import type { Lineage, GraphLot, EventHistory } from '../types'
import { EventTimeline } from './EventTimeline'
import { lotStatusLabel } from '../types'

interface Props { lotId: string; onOpenLot: (id: string) => void }

export function LineagePanel({ lotId, onOpenLot }: Props) {
  const scrollRef = useRef<HTMLDivElement>(null)
  const [data, setData] = useState<[Lineage, Lineage] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [collapsed, setCollapsed] = useState<Set<string>>(new Set())
  const [compact, setCompact] = useState(true)
  const [historyLotId, setHistoryLotId] = useState<string | null>(null)
  const [history, setHistory] = useState<EventHistory | null>(null)
  const [historyError, setHistoryError] = useState<string | null>(null)
  const [historyRefresh, setHistoryRefresh] = useState(0)
  useEffect(() => {
    if (!historyLotId) return
    let active = true
    getLotHistory(historyLotId).then(result => {if (active) setHistory(result)})
      .catch((err: unknown) => {if (active) setHistoryError(err instanceof Error ? err.message : 'Không thể tải lịch sử nguồn.')})
    return () => {active = false}
  }, [historyLotId, historyRefresh])
  const showHistory = (id: string) => {setHistory(null); setHistoryError(null); setHistoryLotId(id); setHistoryRefresh(current => current + 1)}
  useEffect(() => {
    let active = true
    Promise.all([getLineage(lotId, 'ancestors'), getLineage(lotId, 'descendants')]).then(result => {
      if (active) setData(result)
    }).catch((err: unknown) => { if (active) setError(err instanceof Error ? err.message : 'Không thể tải phả hệ.') })
    return () => { active = false }
  }, [lotId])

  const {nodes, edges, lots} = useMemo(() => {
    if (!data) return {nodes: [] as Node[], edges: [] as Edge[], lots: [] as GraphLot[]}
    const lotMap = new Map(data.flatMap(graph => graph.nodes).map(lot => [lot.id, lot]))
    const relationMap = new Map(data.flatMap(graph => graph.edges).map(edge => [edge.id, edge]))
    const relations = [...relationMap.values()]
    // Walking stops at a collapsed node, so shared descendants remain visible
    // through another expanded parent in a merge DAG.
    const visible = new Set([lotId])
    for (const ancestors of [true, false]) {
      const graphEdges = ancestors ? data[0].edges : data[1].edges
      const adjacent = new Map<string, string[]>()
      for (const edge of graphEdges) {
        const from = ancestors ? edge.child_lot_id : edge.parent_lot_id
        const to = ancestors ? edge.parent_lot_id : edge.child_lot_id
        adjacent.set(from, [...(adjacent.get(from) ?? []), to])
      }
      const queue = [{id: lotId, depth: 0}]
      const visited = new Set([lotId])
      for (let index = 0; index < queue.length; index++) {
        const current = queue[index]
        if (collapsed.has(current.id) || (compact && current.depth >= 2)) continue
        for (const id of adjacent.get(current.id) ?? []) {
          visible.add(id)
          if (!visited.has(id)) { visited.add(id); queue.push({id, depth: current.depth + 1}) }
        }
      }
    }
    const layout = new dagre.graphlib.Graph().setDefaultEdgeLabel(() => ({}))
    layout.setGraph({rankdir: 'LR', nodesep: 60, ranksep: 90})
    const visibleLots = [...lotMap.values()].filter(lot => visible.has(lot.id))
    const visibleRelations = relations.filter(edge => visible.has(edge.parent_lot_id) && visible.has(edge.child_lot_id))
    for (const lot of visibleLots) layout.setNode(lot.id, {width: 270, height: 220})
    for (const edge of visibleRelations) layout.setEdge(edge.parent_lot_id, edge.child_lot_id)
    dagre.layout(layout)
    const center = layout.node(lotId)
    const nodes: Node[] = visibleLots.map(lot => ({
      id: lot.id, position: {x: layout.node(lot.id).x - center.x, y: layout.node(lot.id).y - center.y},
      sourcePosition: Position.Right, targetPosition: Position.Left,
      className: lot.id === lotId ? 'lineage-current' : '',
      data: {label: <div>
        <strong>{lot.lot_code ?? lot.name}</strong><br />
        {lot.historical_only ? 'Chỉ lịch sử đến lúc bàn giao' : <>{lot.current_holder_organization_name}<br />{lot.current_location ? `${lot.current_location.name} · ${lot.current_location.address}` : 'Chưa gán địa điểm'}<br />Còn {lot.remaining_quantity} {lot.product?.unit}<br />{lotStatusLabel(lot.status)}</>}<br />
        <button type="button" className="nodrag" onClick={event => {
          event.stopPropagation()
          setCollapsed(current => {const next = new Set(current); if (next.has(lot.id)) next.delete(lot.id); else next.add(lot.id); return next})
        }}>{collapsed.has(lot.id) ? 'Mở nhánh' : 'Thu gọn nhánh'}</button>
      </div>},
    }))
    return {nodes, edges: visibleRelations.map(edge => ({
      id: edge.id, source: edge.parent_lot_id, target: edge.child_lot_id,
      label: `${edge.quantity} ${lotMap.get(edge.child_lot_id)?.product?.unit ?? ''}`,
      type: 'smoothstep',
    })), lots: [...lotMap.values()]}
  }, [data, lotId, compact, collapsed])

  return <section className="panel-card panel-box" aria-labelledby="lineage-title">
    <div className="panel-head"><div><h2 id="lineage-title">Phả hệ lô</h2>
      <p className="panel-sub">Tổ tiên bên trái · lô hiện tại ở giữa · hậu duệ bên phải. Bấm lô để xem chi tiết.</p></div>
      <button type="button" className="ds-button ds-button-secondary" onClick={() => {setCompact(current => !current); setCollapsed(new Set())}}>{compact ? 'Hiện toàn bộ phả hệ' : 'Thu gọn còn 2 tầng'}</button>
    </div>
    {error ? <p className="alert-box alert-error" role="alert">{error}</p> : !data ? <p aria-busy="true">Đang tải phả hệ…</p> : <>
      <p>Vùng trồng gốc: {data[0].root_farms.map(farm => farm.name).join(', ') || 'Chưa có thông tin vùng trồng gốc'}</p>
      <div className="lineage-scroll" ref={scrollRef}><div className="lineage-canvas">
        <ReactFlow key={`${lotId}:${compact}:${[...collapsed].join(',')}`} nodes={nodes} edges={edges}
          ariaLabelConfig={{'controls.zoomIn.ariaLabel': 'Phóng to sơ đồ', 'controls.zoomOut.ariaLabel': 'Thu nhỏ sơ đồ', 'controls.fitView.ariaLabel': 'Vừa màn hình'}}
          fitView fitViewOptions={{padding: 0.2, maxZoom: 0.8}}
          nodesDraggable={false} nodesConnectable={false} edgesReconnectable={false}
          onNodeClick={(_, node) => {
            if (node.id === lotId) return
            if (lots.find(lot => lot.id === node.id)?.historical_only) showHistory(node.id)
            else onOpenLot(node.id)
          }}
          minZoom={0.15} maxZoom={1.5} zoomOnScroll={false} preventScrolling={false}>
          <Background /><Controls showInteractive={false} />
        </ReactFlow>
      </div></div>
      <details><summary>Danh sách {lots.length} lô liên quan</summary>
        <div className="lineage-table-scroll"><table className="data-table source-table"><thead><tr><th>Lô</th><th>Đơn vị giữ</th><th>Địa điểm hiện tại</th><th>Còn lại</th><th>Trạng thái</th></tr></thead>
          <tbody>{lots.map(lot => <tr key={lot.id}><td><button type="button" onClick={() => lot.historical_only ? showHistory(lot.id) : onOpenLot(lot.id)}>{lot.lot_code ?? lot.id.slice(0,8)}</button></td><td>{lot.current_holder_organization_name ?? 'Chỉ xem lịch sử'}</td><td>{lot.historical_only ? '—' : lot.current_location ? `${lot.current_location.name} · ${lot.current_location.address}` : 'Chưa gán địa điểm'}</td><td>{lot.remaining_quantity ?? '—'} {lot.historical_only ? '' : lot.product?.unit}</td><td>{lotStatusLabel(lot.status)}</td></tr>)}</tbody>
        </table></div>
      </details>
      {historyLotId && <div className="panel-box">
        <button type="button" className="ds-button ds-button-secondary" onClick={() => setHistoryLotId(null)}>Đóng lịch sử nguồn</button>
        {historyError ? <p role="alert">{historyError}</p> : <EventTimeline key={historyLotId} lotId={historyLotId} nextCursor={history?.next_cursor} events={history?.events ?? []}
          integrity={history?.integrity} loading={!history} lotName={lots.find(lot => lot.id === historyLotId)?.lot_code ?? historyLotId.slice(0,8)} />}
      </div>}
    </>}
  </section>
}
