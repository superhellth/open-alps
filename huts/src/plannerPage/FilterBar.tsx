import {
  Accordion, AccordionDetails, AccordionSummary, Box, Button, Checkbox, Chip, FormControlLabel,
  IconButton, LinearProgress, MenuItem, Select, TextField, Tooltip, Typography,
} from '@mui/material'
import { useState } from 'react'
import { ALL_HUT_CLASSES, OPERATOR_LABEL, hutClassKey, hutClassLabel } from '@/data/hutClass.js'
import type { HutOperator } from '@/data/hutClass.js'

const OPERATORS = Object.keys(OPERATOR_LABEL) as HutOperator[]
import type { TourMode } from '../tourSearch/types.js'
import { DEFAULT_FORM, isFilterSelectionValid } from '@/features/discover/formState.js'
import type { FormState } from '@/features/discover/formState.js'
import type { TripDraft } from '@/features/discover/plannerState.js'
import RangeCalendar from './RangeCalendar.js'

interface FilterBarProps {
  form: FormState
  onFormChange: (patch: Partial<FormState>) => void
  draft: TripDraft
  onDraftChange: (patch: Partial<TripDraft>) => void
  disabled: boolean
  searching: boolean
  onErweitertOpenChange?: (open: boolean) => void
}

const SAC_OPTIONS: { value: number | 'any'; label: string; description: string }[] = [
  { value: 1, label: 'T1 Wandern', description: 'breite Wege, kaum Absturzgefahr' },
  { value: 2, label: 'T2 Bergwandern', description: 'schmale Pfade, Trittsicherheit nötig' },
  { value: 3, label: 'T3 anspruchsvolles Bergwandern', description: 'ausgesetzte Stellen, teils Hände nötig' },
  { value: 'any', label: 'keine Grenze', description: '' },
]

const LEG_TIME_CEILINGS = [5, 7, 9] as const

function ErweitertSummary({ form }: { form: FormState }) {
  const parts: string[] = []
  if (form.allowViaFerrata) parts.push('Klettersteige an')
  if (form.allowUngraded) parts.push('ungeratete Wege an')
  ALL_HUT_CLASSES.forEach((c) => {
    const key = hutClassKey(c)
    const wasDefault = DEFAULT_FORM.allowedHutClasses.has(key)
    const isNow = form.allowedHutClasses.has(key)
    if (wasDefault && !isNow) parts.push(`${hutClassLabel(c)} aus`)
    if (!wasDefault && isNow) parts.push(`${hutClassLabel(c)} an`)
  })
  if (form.legAscentCapM !== '') parts.push(`Anstieg ≤ ${form.legAscentCapM} m`)
  if (form.maxEleM !== '') parts.push(`Höhe ≤ ${form.maxEleM} m`)
  return <Typography variant="subtitle2">Erweitert{parts.length ? ` · ${parts.join(', ')}` : ''}</Typography>
}

export default function FilterBar({ form, onFormChange, draft, onDraftChange, disabled, searching, onErweitertOpenChange }: FilterBarProps) {
  const [erweitertOpen, setErweitertOpen] = useState(false)
  const setErweitert = (open: boolean) => { setErweitertOpen(open); onErweitertOpenChange?.(open) }
  const operatorOn = (op: HutOperator) => form.allowedHutClasses.has(hutClassKey({ operator: op, serviced: true }))
  const selfIncluded = ALL_HUT_CLASSES.some((c) => !c.serviced && form.allowedHutClasses.has(hutClassKey(c)))

  const toggleOperator = (op: HutOperator, on: boolean) => {
    const next = new Set(form.allowedHutClasses)
    const servicedKey = hutClassKey({ operator: op, serviced: true })
    const selfKey = hutClassKey({ operator: op, serviced: false })
    if (on) {
      next.add(servicedKey)
      if (selfIncluded) next.add(selfKey)
    } else {
      next.delete(servicedKey)
      next.delete(selfKey)
    }
    onFormChange({ allowedHutClasses: next })
  }
  const toggleSelfIncluded = (on: boolean) => {
    const next = new Set(form.allowedHutClasses)
    OPERATORS.forEach((op) => {
      if (!operatorOn(op)) return
      const selfKey = hutClassKey({ operator: op, serviced: false })
      if (on) next.add(selfKey)
      else next.delete(selfKey)
    })
    onFormChange({ allowedHutClasses: next })
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

      <Box sx={{ display: 'flex', gap: 2 }}>
        <Box sx={{ flex: 1, minWidth: 0 }}>
          <Typography variant="subtitle2">Wann?</Typography>
          <RangeCalendar
            startDate={draft.startDate} endDate={draft.endDate} disabled={disabled}
            onChange={(range) => onDraftChange(range)}
          />
        </Box>

        <Box>
          <Typography variant="subtitle2">Wie viele?</Typography>
          <Box sx={{ display: 'flex', gap: 1, alignItems: 'center' }}>
            <Typography>{draft.partySize} Pers.</Typography>
            <Button size="small" variant="outlined" color="secondary" disabled={disabled || draft.partySize <= 1}
              sx={{ width: 40, height: 40, minWidth: 0, p: 0 }}
              onClick={() => onDraftChange({ partySize: draft.partySize - 1 })}>−</Button>
            <Button size="small" variant="outlined" color="secondary" disabled={disabled || draft.partySize >= 25}
              sx={{ width: 40, height: 40, minWidth: 0, p: 0 }}
              onClick={() => onDraftChange({ partySize: draft.partySize + 1 })}>+</Button>
          </Box>
        </Box>
      </Box>

      <Box>
        {check('Verfügbarkeit prüfen', form.onlyAvailable, (onlyAvailable) => onFormChange({ onlyAvailable }))}
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

      <Accordion
        disableGutters elevation={0} square expanded={erweitertOpen} onChange={(_, isExpanded) => setErweitert(isExpanded)}
        sx={{ bgcolor: 'transparent', '&:before': { display: 'none' } }}
      >
        <AccordionSummary
          expandIcon={<Typography sx={{ color: 'primary.main', fontWeight: 'bold' }} aria-hidden>{erweitertOpen ? '−' : '+'}</Typography>}
          sx={{
            px: 1, mx: -1, borderRadius: 1, minHeight: 0, '&.Mui-expanded': { minHeight: 0 },
            '&:hover': { bgcolor: 'action.hover' },
            '& .MuiAccordionSummary-content': { margin: '4px 0', '&.Mui-expanded': { margin: '4px 0' } },
            '& .MuiAccordionSummary-expandIconWrapper.Mui-expanded': { transform: 'none' },
          }}
        >
          <ErweitertSummary form={form} />
        </AccordionSummary>
        <AccordionDetails sx={{ display: 'flex', flexDirection: 'column', gap: 1, p: 0, pt: 1 }}>
          {check('Klettersteige erlauben', form.allowViaFerrata, (allowViaFerrata) => onFormChange({ allowViaFerrata }))}
          {check('auch ungeratete Wege erlauben', form.allowUngraded, (allowUngraded) => onFormChange({ allowUngraded }))}
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5, mt: 1 }}>
            <Typography variant="subtitle2">Hüttenarten</Typography>
            <Tooltip
              title="Sonstige: nicht vom Alpenverein betriebene Hütten. Selbstversorgerhütten sind unbewirtschaftet, meist Selbstverpflegung, ggf. Schlüssel beim Verein holen."
              placement="top" arrow
            >
              <IconButton size="small" aria-label="Was bedeuten die Hüttenarten?">
                <Typography component="span">?</Typography>
              </IconButton>
            </Tooltip>
          </Box>
          {OPERATORS.map((op) => check(OPERATOR_LABEL[op], operatorOn(op), (on) => toggleOperator(op, on)))}
          {check('auch Selbstversorgerhütten einschließen', selfIncluded, toggleSelfIncluded)}
          {!isFilterSelectionValid(form) && (
            <Typography variant="caption" color="error">
              Mindestens eine Hüttenart muss ausgewählt sein.
            </Typography>
          )}
          <Typography variant="subtitle2" sx={{ mt: 1 }}>Höhe</Typography>
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
