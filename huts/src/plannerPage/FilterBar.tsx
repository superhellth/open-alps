import { Accordion, AccordionDetails, AccordionSummary, Alert, Box, Checkbox, FormControlLabel, LinearProgress, MenuItem, Select, TextField, Typography } from '@mui/material'
import { OPERATOR_LABEL } from '../hutClass.js'
import type { HutOperator } from '../hutClass.js'
import { LEG_COUNT_SLIDER_MAX, LEG_COUNT_SLOW_WARNING_THRESHOLD } from '../tourSearch/limits.js'
import type { TourMode } from '../tourSearch/types.js'
import DraftRangeSlider from './DraftRangeSlider.js'
import { isFilterSelectionValid } from './formState.js'
import type { FormState } from './formState.js'
import type { TripDraft } from './plannerState.js'

interface FilterBarProps {
  form: FormState
  onFormChange: (patch: Partial<FormState>) => void
  draft: TripDraft
  onDraftChange: (patch: Partial<TripDraft>) => void
  disabled: boolean
  searching: boolean
}

export default function FilterBar({ form, onFormChange, draft, onDraftChange, disabled, searching }: FilterBarProps) {
  const toggleOperator = (op: HutOperator, on: boolean) => {
    const next = new Set(form.allowedOperators)
    if (on) next.add(op)
    else next.delete(op)
    onFormChange({ allowedOperators: next })
  }
  const check = (label: string, checked: boolean, onChange: (v: boolean) => void) => (
    <FormControlLabel
      sx={{ display: 'block' }} label={label}
      control={<Checkbox size="small" checked={checked} disabled={disabled} onChange={(e) => onChange(e.target.checked)} />}
    />
  )

  return (
    <Box component="form" onSubmit={(e) => e.preventDefault()} sx={{ p: 2, display: 'flex', flexDirection: 'column', gap: 1.5 }}>
      {disabled && <Typography color="text.secondary">Wegenetz wird geladen …</Typography>}

      <Select
        size="small" value={form.mode} disabled={disabled} inputProps={{ 'aria-label': 'Anreise' }}
        onChange={(e) => onFormChange({ mode: e.target.value as TourMode })}
      >
        <MenuItem value="car">Auto (Rundtour zum Ausgangspunkt)</MenuItem>
        <MenuItem value="transit">ÖPNV (offene Strecke)</MenuItem>
        <MenuItem value="village">Start im Bergsteigerdorf (offene Strecke)</MenuItem>
      </Select>

      <DraftRangeSlider
        label="Tage" value={form.legCountRange} min={2} max={LEG_COUNT_SLIDER_MAX} step={1} disabled={disabled}
        format={([a, b]) => `${a}–${b}`} onCommit={(legCountRange) => onFormChange({ legCountRange })}
        note={(d) => d[1] > LEG_COUNT_SLOW_WARNING_THRESHOLD
          ? <Alert severity="warning">Hohe Etappenzahl kann die Suche spürbar verlangsamen.</Alert>
          : null}
      />
      <DraftRangeSlider
        label="Gehzeit pro Tag (Std)" value={form.legTimeRange} min={1} max={12} step={0.5} disabled={disabled}
        format={([a, b]) => `${a}–${b}`} onCommit={(legTimeRange) => onFormChange({ legTimeRange })}
      />

      <Select
        size="small" value={form.sacCeiling} disabled={disabled} inputProps={{ 'aria-label': 'Schwierigkeit' }}
        onChange={(e) => onFormChange({ sacCeiling: e.target.value === 'any' ? 'any' : Number(e.target.value) })}
      >
        <MenuItem value={1}>T1 Wandern</MenuItem>
        <MenuItem value={2}>T2 Bergwandern</MenuItem>
        <MenuItem value={3}>T3 anspruchsvolles Bergwandern</MenuItem>
        <MenuItem value="any">beliebig</MenuItem>
      </Select>
      {check('auch ungeratete Wege erlauben', form.allowUngraded, (allowUngraded) => onFormChange({ allowUngraded }))}
      {check('Klettersteige erlauben', form.allowViaFerrata, (allowViaFerrata) => onFormChange({ allowViaFerrata }))}

      <Box>
        <Typography variant="subtitle2">Hüttenarten</Typography>
        {(Object.keys(OPERATOR_LABEL) as HutOperator[]).map((op) => (
          <Box key={op}>{check(OPERATOR_LABEL[op], form.allowedOperators.has(op), (on) => toggleOperator(op, on))}</Box>
        ))}
        {check('Bewirtschaftete Hütten', form.allowServiced, (allowServiced) => onFormChange({ allowServiced }))}
        {check('Selbstversorgerhütten (unbewirtschaftet, ggf. Schlüssel nötig)', form.allowSelfService, (allowSelfService) => onFormChange({ allowSelfService }))}
        {!isFilterSelectionValid(form) && (
          <Typography variant="caption" color="error">
            Mindestens ein Betreiber und eine Betriebsart müssen ausgewählt sein.
          </Typography>
        )}
      </Box>

      <Box sx={{ display: 'flex', gap: 1 }}>
        <TextField
          size="small" type="date" label="Startdatum (erste Nacht)" value={draft.startDate} disabled={disabled}
          slotProps={{ inputLabel: { shrink: true } }} onChange={(e) => onDraftChange({ startDate: e.target.value })}
        />
        <TextField
          size="small" type="number" label="Personen" value={draft.partySize} disabled={disabled}
          slotProps={{ htmlInput: { min: 1, max: 9 } }} sx={{ width: 100 }}
          onChange={(e) => onDraftChange({ partySize: Math.min(9, Math.max(1, Number(e.target.value) || 1)) })}
        />
      </Box>
      {draft.startDate && check('nur Touren mit Verfügbarkeit', form.onlyAvailable, (onlyAvailable) => onFormChange({ onlyAvailable }))}

      <Accordion disableGutters elevation={0} sx={{ border: '1px solid', borderColor: 'divider', '&:before': { display: 'none' } }}>
        <AccordionSummary sx={{ minHeight: 0 }}><Typography variant="subtitle2">Erweiterte Optionen</Typography></AccordionSummary>
        <AccordionDetails sx={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
          <TextField
            size="small" type="number" label="Wunsch-Tageszahl (Sortierung)" disabled={disabled}
            value={form.targetLegCount ?? ''} slotProps={{ htmlInput: { min: 2, max: LEG_COUNT_SLIDER_MAX } }}
            onChange={(e) => onFormChange({ targetLegCount: e.target.value === '' ? null : Number(e.target.value) })}
          />
          <TextField
            size="small" type="number" label="Anstiegslimit pro Etappe (m, leer = unbegrenzt)" disabled={disabled}
            value={form.legAscentCapM} slotProps={{ htmlInput: { min: 0 } }}
            onChange={(e) => onFormChange({ legAscentCapM: e.target.value })}
          />
          <TextField
            size="small" type="number" label="Maximalhöhe (m, leer = unbegrenzt)" disabled={disabled}
            value={form.maxEleM} onChange={(e) => onFormChange({ maxEleM: e.target.value })}
          />
        </AccordionDetails>
      </Accordion>

      <Box sx={{ height: 4 }}>{searching && <LinearProgress aria-label="Suche läuft" />}</Box>
    </Box>
  )
}
