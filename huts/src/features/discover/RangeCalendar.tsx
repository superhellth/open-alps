import { useState } from 'react'
import { formatDayMonthRange } from '@/format/dayMonth.js'
import CalendarField from '@/ui/CalendarField.js'
import MonthCalendar from '@/ui/MonthCalendar.js'

interface RangeCalendarProps {
  startDate: string
  endDate: string
  onChange: (range: { startDate: string; endDate: string }) => void
  disabled: boolean
}

export default function RangeCalendar({ startDate, endDate, onChange, disabled }: RangeCalendarProps) {
  // Holds the first click of a new range until the second click completes it,
  // so a single click never reports an empty endDate to the parent.
  const [pendingStart, setPendingStart] = useState<string | null>(null)
  const [hoverDay, setHoverDay] = useState<string | null>(null)
  const label = startDate === '' || endDate === '' ? 'Zeitraum wählen' : formatDayMonthRange(startDate, endDate)

  // While the second click is pending, the hovered day previews the range it would complete.
  const preview = pendingStart !== null && hoverDay !== null ? [pendingStart, hoverDay].sort() : null
  const rangeStart = preview?.[0] ?? pendingStart ?? startDate
  const rangeEnd = preview?.[1] ?? pendingStart ?? endDate

  return (
    <CalendarField label={label} disabled={disabled} onOpen={() => { setPendingStart(null); setHoverDay(null) }}>
      {(close) => (
        <MonthCalendar
          initialDay={startDate} disabled={disabled}
          rangeStart={rangeStart} rangeEnd={rangeEnd} onHoverDay={setHoverDay}
          onPickDay={(iso) => {
            if (pendingStart === null) { setPendingStart(iso); return }
            onChange(iso < pendingStart ? { startDate: iso, endDate: pendingStart } : { startDate: pendingStart, endDate: iso })
            setPendingStart(null)
            setHoverDay(null)
            close()
          }}
        />
      )}
    </CalendarField>
  )
}
