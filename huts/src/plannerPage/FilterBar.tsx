import { useState } from 'react'
import {
  Accordion, AccordionDetails, AccordionSummary, Box, Button, Checkbox, Chip, FormControlLabel,
  IconButton, LinearProgress, MenuItem, Popover, Select, TextField, Typography,
} from '@mui/material'
import { OPERATOR_LABEL } from '../hutClass.js'
import type { HutOperator } from '../hutClass.js'
import type { TourMode } from '../tourSearch/types.js'
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

const SAC_OPTIONS: { value: number | 'any'; label: string; description: string }[] = [
  { value: 1, label: 'T1 Wandern', description: 'breite Wege, kaum Absturzgefahr' },
  { value: 2, label: 'T2 Bergwandern', description: 'schmale Pfade, Trittsicherheit nötig' },
  { value: 3, label: 'T3 anspruchsvolles Bergwandern', description: 'ausgesetzte Stellen, teils Hände nötig' },
  { value: 'any', label: 'keine Grenze', description: '' },
]

const LEG_TIME_CEILINGS = [5, 7, 9] as const

function todayIso(): string {
  return new Date().toISOString().slice(0, 10)
}

function addDaysIso(iso: string, days: number): string {
  const [y, m, d] = iso.split('-').map(Number)
  return new Date(Date.UTC(y, m - 1, d + days)).toISOString().slice(0, 10)
}

function WegeHuettenSummary({ form }: { form: FormState }) {
  const parts: string[] = []
  if (form.allowViaFerrata) parts.push('Klettersteige an')
  if (form.allowUngraded) parts.push('ungeratete Wege an')
  if (form.allowSelfService) parts.push('Selbstversorger an')
  return <Typography variant="subtitle2">Wege & Hütten{parts.length ? ` · ${parts.join(', ')}` : ''}</Typography>
}

function ErweitertSummary({ form }: { form: FormState }) {
  const parts: string[] = []
  if (form.legAscentCapM !== '') parts.push(`Anstieg ≤ ${form.legAscentCapM} m`)
  if (form.maxEleM !== '') parts.push(`Höhe ≤ ${form.maxEleM} m`)
  return <Typography variant="subtitle2">Erweitert{parts.length ? ` · ${parts.join(', ')}` : ''}</Typography>
}

export default function FilterBar({ form, onFormChange, draft, onDraftChange, disabled, searching }: FilterBarProps) {
  const [helpAnchor, setHelpAnchor] = useState<HTMLElement | null>(null)

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
  const dated = draft.startDate !== '' && draft.endDate !== ''

  return (
    <Box component="form" onSubmit={(e) => e.preventDefault()} sx={{ p: 2, display: 'flex', flexDirection: 'column', gap: 1.5 }}>
      {disabled && <Typography color="text.secondary">Wegenetz wird geladen …</Typography>}

      <Box>
        <Typography variant="subtitle2">Anreise</Typography>
        <Select
          size="small" fullWidth value={form.mode} disabled={disabled} inputProps={{ 'aria-label': 'Anreise' }}
          onChange={(e) => onFormChange({ mode: e.target.value as TourMode })}
        >
          <MenuItem value="car">Auto (Rundtour zum Ausgangspunkt)</MenuItem>
          <MenuItem value="transit">ÖPNV (offene Strecke)</MenuItem>
          <MenuItem value="village">Start im Bergsteigerdorf (offene Strecke)</MenuItem>
        </Select>
      </Box>

      <Box>
        <Typography variant="subtitle2">Wann?</Typography>
        {dated ? (
          <>
            <Box sx={{ display: 'flex', gap: 1 }}>
              <TextField
                size="small" type="date" label="Von" value={draft.startDate} disabled={disabled}
                slotProps={{ inputLabel: { shrink: true } }} onChange={(e) => onDraftChange({ startDate: e.target.value })}
              />
              <TextField
                size="small" type="date" label="Bis" value={draft.endDate} disabled={disabled}
                slotProps={{ inputLabel: { shrink: true } }} onChange={(e) => onDraftChange({ endDate: e.target.value })}
              />
            </Box>
            <Button size="small" onClick={() => onDraftChange({ startDate: '', endDate: '' })}>ohne Datum</Button>
          </>
        ) : (
          <>
            <Box sx={{ display: 'flex', gap: 1, alignItems: 'center' }}>
              <Typography>{draft.dayCount} Tage</Typography>
              <Button size="small" variant="outlined" color="secondary" disabled={disabled || draft.dayCount <= 2}
                onClick={() => onDraftChange({ dayCount: draft.dayCount - 1 })}>−</Button>
              <Button size="small" variant="outlined" color="secondary" disabled={disabled}
                onClick={() => onDraftChange({ dayCount: draft.dayCount + 1 })}>+</Button>
              <Chip
                label="flexibel ±1 Tag" clickable disabled={disabled}
                color={draft.flexible ? 'primary' : 'default'}
                onClick={() => onDraftChange({ flexible: !draft.flexible })}
              />
            </Box>
            <Button size="small" onClick={() => onDraftChange({ startDate: todayIso(), endDate: addDaysIso(todayIso(), draft.dayCount - 1) })}>
              Datum wählen
            </Button>
          </>
        )}
      </Box>

      <Box>
        <Typography variant="subtitle2">Wie viele?</Typography>
        <Box sx={{ display: 'flex', gap: 1, alignItems: 'center' }}>
          <Typography>{draft.partySize} Pers.</Typography>
          <Button size="small" variant="outlined" color="secondary" disabled={disabled || draft.partySize <= 1}
            onClick={() => onDraftChange({ partySize: draft.partySize - 1 })}>−</Button>
          <Button size="small" variant="outlined" color="secondary" disabled={disabled || draft.partySize >= 9}
            onClick={() => onDraftChange({ partySize: draft.partySize + 1 })}>+</Button>
        </Box>
      </Box>

      <Box>
        <Typography variant="subtitle2">Gehzeit pro Tag</Typography>
        <Box sx={{ display: 'flex', gap: 1 }}>
          {LEG_TIME_CEILINGS.map((h) => (
            <Chip
              key={h} label={`bis ${h} h`} clickable disabled={disabled}
              color={form.legTimeCeilingH === h ? 'primary' : 'default'}
              onClick={() => onFormChange({ legTimeCeilingH: h })}
              aria-pressed={form.legTimeCeilingH === h}
            />
          ))}
        </Box>
      </Box>

      <Box>
        <Typography variant="subtitle2">Höchste Schwierigkeit</Typography>
        <Select
          size="small" fullWidth value={form.sacCeiling} disabled={disabled} inputProps={{ 'aria-label': 'Schwierigkeit' }}
          onChange={(e) => onFormChange({ sacCeiling: e.target.value === 'any' ? 'any' : Number(e.target.value) })}
        >
          {SAC_OPTIONS.map((o) => (
            <MenuItem key={o.value} value={o.value}>
              <Box>
                <Typography variant="body2">{o.label}</Typography>
                {o.description && <Typography variant="caption" color="text.secondary">{o.description}</Typography>}
              </Box>
            </MenuItem>
          ))}
        </Select>
      </Box>

      <Accordion disableGutters elevation={0} sx={{ border: '1px solid', borderColor: 'divider', '&:before': { display: 'none' } }}>
        <AccordionSummary sx={{ minHeight: 0 }}><WegeHuettenSummary form={form} /></AccordionSummary>
        <AccordionDetails sx={{ display: 'flex', flexDirection: 'column', gap: 1 }}>
          {check('auch ungeratete Wege erlauben', form.allowUngraded, (allowUngraded) => onFormChange({ allowUngraded }))}
          {check('Klettersteige erlauben', form.allowViaFerrata, (allowViaFerrata) => onFormChange({ allowViaFerrata }))}
          <Typography variant="subtitle2" sx={{ mt: 1 }}>Hüttenarten</Typography>
          {(Object.keys(OPERATOR_LABEL) as HutOperator[]).map((op) => (
            <Box key={op}>{check(OPERATOR_LABEL[op], form.allowedOperators.has(op), (on) => toggleOperator(op, on))}</Box>
          ))}
          {check('Bewirtschaftete Hütten', form.allowServiced, (allowServiced) => onFormChange({ allowServiced }))}
          <Box sx={{ display: 'flex', alignItems: 'center' }}>
            {check('Selbstversorgerhütten', form.allowSelfService, (allowSelfService) => onFormChange({ allowSelfService }))}
            <IconButton size="small" aria-label="Was ist eine Selbstversorgerhütte?" onClick={(e) => setHelpAnchor(e.currentTarget)}>
              <Typography component="span">?</Typography>
            </IconButton>
          </Box>
          <Popover open={helpAnchor !== null} anchorEl={helpAnchor} onClose={() => setHelpAnchor(null)}>
            <Typography sx={{ p: 1.5, maxWidth: 280 }}>
              Unbewirtschaftet, meist Selbstverpflegung, ggf. Schlüssel beim Verein holen.
            </Typography>
          </Popover>
          {!isFilterSelectionValid(form) && (
            <Typography variant="caption" color="error">
              Mindestens ein Betreiber und eine Betriebsart müssen ausgewählt sein.
            </Typography>
          )}
        </AccordionDetails>
      </Accordion>

      {dated && check('Verfügbarkeit prüfen', form.onlyAvailable, (onlyAvailable) => onFormChange({ onlyAvailable }))}
      {dated && form.onlyAvailable && (
        <Chip
          label="auch volle Touren zeigen" clickable
          color={form.showFullToo ? 'primary' : 'default'}
          onClick={() => onFormChange({ showFullToo: !form.showFullToo })}
        />
      )}

      <Accordion disableGutters elevation={0} sx={{ border: '1px solid', borderColor: 'divider', '&:before': { display: 'none' } }}>
        <AccordionSummary sx={{ minHeight: 0 }}><ErweitertSummary form={form} /></AccordionSummary>
        <AccordionDetails sx={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
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
