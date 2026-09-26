import { Box } from '@mui/material'
import type { AppData } from '@/data/buildAppData.js'
import type { Trip } from '@/trip/trip.js'
import type { ProfilePosition, TripLegs } from '@/trip/tripLegs.js'
import HeightProfile from './HeightProfile.js'
import StageList from './StageList.js'
import TripHeader from './TripHeader.js'
import type { TripEditor } from './TripEditor.js'
import { useTripAvailability } from './useTripAvailability.js'
import { useTripElevation } from './useTripElevation.js'
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
  /** Names at the night boundaries: start label, each hut, exit label. */
  stopNames: string[]
  onHoverProfile: (position: ProfilePosition | null) => void
  editor: TripEditor
  editMode: boolean
  onEditModeChange: (on: boolean) => void
  warnings?: string[]
  onShare?: () => void
}

/** The open trip as three sections: header (name, totals, dates), height profile and stages. */
export default function TripPanel({
  trip, tripLegs, data, startLabel, isDraft, onChange, onSave, onUnsave, onBack, backLabel, highlightedLeg, onHoverLeg,
  stopNames, onHoverProfile, editor, editMode, onEditModeChange, warnings, onShare,
}: TripPanelProps) {
  const nightViews = useTripAvailability(trip, tripLegs.hutIndices, data.hutOhrsByIndex)
  const elevation = useTripElevation(tripLegs)
  return (
    <Box sx={styles.root}>
      <TripHeader
        trip={trip} tripLegs={tripLegs} hutOhrsByIndex={data.hutOhrsByIndex} isDraft={isDraft}
        onChange={onChange} onSave={onSave} onUnsave={onUnsave} onBack={onBack} backLabel={backLabel} onShare={onShare}
      />
      <HeightProfile
        elevation={elevation} stops={stopNames} highlightedLeg={highlightedLeg}
        onHoverLeg={onHoverLeg} onHoverPosition={onHoverProfile}
      />
      <StageList
        trip={trip} tripLegs={tripLegs} hutNameById={data.hutNameById} hutOhrsByIndex={data.hutOhrsByIndex}
        startLabel={startLabel} nightViews={nightViews} highlightedLeg={highlightedLeg} onHoverLeg={onHoverLeg}
        editor={editor} editMode={editMode} onEditModeChange={onEditModeChange} warnings={warnings}
      />
    </Box>
  )
}
