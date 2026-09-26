import { Box, Divider } from '@mui/material'
import type { AppData } from '@/data/buildAppData.js'
import type { BookingStatus, Trip } from '@/trip/trip.js'
import type { TripLegs } from '@/trip/tripLegs.js'
import StageList from './StageList.js'
import TripFooter from './TripFooter.js'
import TripHeader from './TripHeader.js'
import type { TripEditor } from './TripEditor.js'
import { useTripAvailability } from './useTripAvailability.js'
import { styles } from './TripPanel.styles.js'

export interface TripPanelProps {
  trip: Trip
  tripLegs: TripLegs
  data: AppData
  startLabel: (startId: number) => string
  isDraft: boolean
  onChange: (trip: Trip) => void
  onSave: (name: string) => void
  onUnsave: () => void
  onBack: () => void
  backLabel: string
  highlightedLeg: number | null
  onHoverLeg: (index: number | null) => void
  editor: TripEditor
  editMode: boolean
  onEditModeChange: (on: boolean) => void
  warnings?: string[]
  onShare?: () => void
}

/** The open trip as three sections: header (name, totals, dates), stages, notes. */
export default function TripPanel({
  trip, tripLegs, data, startLabel, isDraft, onChange, onSave, onUnsave, onBack, backLabel, highlightedLeg, onHoverLeg,
  editor, editMode, onEditModeChange, warnings, onShare,
}: TripPanelProps) {
  const nightViews = useTripAvailability(trip, tripLegs.hutIndices, data.hutOhrsByIndex)
  return (
    <Box sx={styles.root}>
      <TripHeader
        trip={trip} tripLegs={tripLegs} hutOhrsByIndex={data.hutOhrsByIndex} isDraft={isDraft}
        onChange={onChange} onSave={onSave} onUnsave={onUnsave} onBack={onBack} backLabel={backLabel} onShare={onShare}
      />
      <Divider />
      <StageList
        trip={trip} tripLegs={tripLegs} hutNameById={data.hutNameById} hutOhrsByIndex={data.hutOhrsByIndex}
        startLabel={startLabel} nightViews={nightViews} highlightedLeg={highlightedLeg} onHoverLeg={onHoverLeg}
        editor={editor} editMode={editMode} onEditModeChange={onEditModeChange} warnings={warnings}
        onNightStatusChange={(night: number, status: BookingStatus) =>
          onChange({ ...trip, nights: trip.nights.map((n, i) => (i === night ? { status } : n)) })}
      />
      <Divider />
      <TripFooter trip={trip} onChange={onChange} />
    </Box>
  )
}
