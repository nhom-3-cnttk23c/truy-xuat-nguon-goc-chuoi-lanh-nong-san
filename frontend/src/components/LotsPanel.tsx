import { useEffect, useState } from 'react'
import { getEvents, getLots } from '../services/api'
import type { Lot, LotEvent } from '../types'
import { EventTimeline } from './EventTimeline'

interface LotsPanelProps {
  canReadLots: boolean
  canReadEvents?: boolean
}

export function LotsPanel({ canReadLots, canReadEvents = true }: LotsPanelProps) {
  const [lots, setLots] = useState<Lot[]>([])
  const [loading, setLoading] = useState(canReadLots)
  const [error, setError] = useState<string | null>(null)

  const [selectedLot, setSelectedLot] = useState<Lot | null>(null)
  const [lotEvents, setLotEvents] = useState<LotEvent[]>([])
  const [loadingEvents, setLoadingEvents] = useState(false)

  const refresh = async () => {
    setLoading(true)
    setError(null)
    try {
      const data = await getLots()
      setLots(data)
      if (selectedLot && !data.some((l) => l.id === selectedLot.id)) {
        setSelectedLot(null)
        setLotEvents([])
      }
    } catch (err) {
      setError(
        err instanceof Error ? err.message : 'Không thể tải danh sách lô'
      )
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    if (!canReadLots) return
    let active = true

    getLots()
      .then((data) => {
        if (active) {
          setLots(data)
          if (data.length > 0) {
            setSelectedLot((prev) => prev ?? data[0])
          }
        }
      })
      .catch((err: unknown) => {
        if (active) {
          setError(
            err instanceof Error ? err.message : 'Không thể tải danh sách lô'
          )
        }
      })
      .finally(() => {
        if (active) setLoading(false)
      })

    return () => {
      active = false
    }
  }, [canReadLots])

  useEffect(() => {
    if (!selectedLot || !canReadEvents) {
      return
    }

    let active = true

    getEvents()
      .then((allEvents) => {
        if (active) {
          const filtered = allEvents
            .filter((e) => e.lot_id === selectedLot.id)
            .sort((a, b) => a.sequence_number - b.sequence_number)
          setLotEvents(filtered)
        }
      })
      .catch(() => {
        if (active) setLotEvents([])
      })
      .finally(() => {
        if (active) setLoadingEvents(false)
      })

    return () => {
      active = false
    }
  }, [selectedLot, canReadEvents])



  if (!canReadLots) {
    return (
      <section className="panel-card panel-box" role="status">
        Tài khoản này không có quyền xem danh sách lô.
      </section>
    )
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem' }}>
      <section
        className="data-table-wrapper panel-card"
        aria-labelledby="lots-table-title"
      >
        <div className="data-table-header">
          <div>
            <h2 id="lots-table-title" className="section-title">
              Danh sách lô hàng ({lots.length})
            </h2>
            <p className="panel-sub">
              Nhấp vào một lô hàng để xem nhật ký sự kiện bất biến (Append-only)
            </p>
          </div>
          <button
            type="button"
            className="ds-button ds-button-secondary ds-button-sm"
            onClick={() => void refresh()}
            disabled={loading}
          >
            {loading ? 'Đang tải...' : 'Làm mới'}
          </button>
        </div>

        {error && (
          <div className="alert-box alert-error table-alert" role="alert">
            {error}
          </div>
        )}

        <div className="table-scroll">
          <table className="data-table">
            <thead>
              <tr>
                <th scope="col">Mã lô</th>
                <th scope="col">Tên lô</th>
                <th scope="col">Mã thửa đất</th>
                <th scope="col">Thao tác</th>
              </tr>
            </thead>
            <tbody>
              {loading ? (
                <tr>
                  <td colSpan={4} className="cell-center" aria-busy="true">
                    Đang tải danh sách lô...
                  </td>
                </tr>
              ) : lots.length === 0 ? (
                <tr>
                  <td colSpan={4} className="cell-center">
                    Tổ chức chưa có lô nào được khai báo.
                  </td>
                </tr>
              ) : (
                lots.map((lot) => {
                  const isSelected = selectedLot?.id === lot.id
                  return (
                    <tr
                      key={lot.id}
                      style={{
                        cursor: 'pointer',
                        backgroundColor: isSelected
                          ? 'rgba(37, 99, 235, 0.05)'
                          : undefined,
                      }}
                      onClick={() => setSelectedLot(lot)}
                    >
                      <td>
                        <code title={lot.id}>
                          {lot.id.slice(0, 8)}...{lot.id.slice(-6)}
                        </code>
                      </td>
                      <th scope="row" className="cell-strong">
                        {lot.name}
                      </th>
                      <td>
                        <code title={lot.farm_id}>
                          {lot.farm_id.slice(0, 8)}...{lot.farm_id.slice(-6)}
                        </code>
                      </td>
                      <td>
                        <button
                          type="button"
                          className={`ds-button ds-button-sm ${
                            isSelected ? 'ds-button-brand' : 'ds-button-secondary'
                          }`}
                          onClick={(e) => {
                            e.stopPropagation()
                            setSelectedLot(lot)
                          }}
                        >
                          {isSelected ? 'Đang chọn' : 'Xem chuỗi sự kiện'}
                        </button>
                      </td>
                    </tr>
                  )
                })
              )}
            </tbody>
          </table>
        </div>
      </section>

      {/* N3-21 Immutable Event Timeline */}
      {selectedLot && canReadEvents && (
        <section className="panel-card panel-box">
          <EventTimeline
            events={lotEvents}
            lotName={selectedLot.name}
            loading={loadingEvents}
          />
        </section>
      )}
    </div>
  )
}
