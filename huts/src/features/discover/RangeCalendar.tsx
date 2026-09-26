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
  const label = startDate === '' || endDate === '' ? 'Zeitraum wählen' : formatDayMonthRange(startDate, endDate)

  return (
    <CalendarField label={label} disabled={disabled} onOpen={() => setPendingStart(null)}>
      {(close) => (
        <MonthCalendar
          initialDay={startDate} disabled={disabled}
          rangeStart={pendingStart ?? startDate} rangeEnd={pendingStart ?? endDate}
          onPickDay={(iso) => {
            if (pendingStart === null) { setPendingStart(iso); return }
            onChange(iso < pendingStart ? { startDate: iso, endDate: pendingStart } : { startDate: pendingStart, endDate: iso })
            setPendingStart(null)
            close()
          }}
        />
      )}
    </CalendarField>
  )
}
