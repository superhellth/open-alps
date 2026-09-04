import { describe, it, expect } from 'vitest'
import { hutClassLabel, hutClassBadge, OPERATOR_LABEL, OPERATOR_COLOR, PARTNER_LABEL, PARTNER_COLOR } from './hutClass.js'

describe('hutClassLabel', () => {
  it('labels a serviced AV hut without a Selbstversorger suffix', () => {
    expect(hutClassLabel({ operator: 'av', serviced: true })).toBe('AV-Hütte')
  })
  it('labels an AV Selbstversorgerhütte with both facts, not collapsed into a third bucket', () => {
    expect(hutClassLabel({ operator: 'av', serviced: false })).toBe('AV-Hütte (Selbstversorger)')
  })
  it('labels a serviced non-AV hut', () => {
    expect(hutClassLabel({ operator: 'sonstige', serviced: true })).toBe('Sonstige Hütte')
  })
  it('labels a non-AV Selbstversorgerhütte', () => {
    expect(hutClassLabel({ operator: 'sonstige', serviced: false })).toBe('Sonstige Hütte (Selbstversorger)')
  })
})

describe('hutClassBadge', () => {
  it('badges operator and servicing independently for all four combinations', () => {
    expect(hutClassBadge({ operator: 'av', serviced: true })).toBe('AV')
    expect(hutClassBadge({ operator: 'av', serviced: false })).toBe('AV·SV')
    expect(hutClassBadge({ operator: 'sonstige', serviced: true })).toBe('SO')
    expect(hutClassBadge({ operator: 'sonstige', serviced: false })).toBe('SO·SV')
  })
})

describe('lookups stay label-complete', () => {
  it('OPERATOR_LABEL covers both operators', () => {
    expect(OPERATOR_LABEL.av).toBe('AV-Hütte')
    expect(OPERATOR_LABEL.sonstige).toBe('Sonstige Hütte')
  })
  it('OPERATOR_COLOR gives a distinct, non-empty colour per operator', () => {
    expect(OPERATOR_COLOR.av).toMatch(/^#/)
    expect(OPERATOR_COLOR.sonstige).toMatch(/^#/)
    expect(OPERATOR_COLOR.av).not.toBe(OPERATOR_COLOR.sonstige)
  })
  it('PARTNER_LABEL uses the AV program name, never "Dorfhütte"', () => {
    expect(PARTNER_LABEL).toBe('Partnerbetrieb (Bergsteigerdorf)')
    expect(PARTNER_LABEL).not.toMatch(/Dorfhütte/)
  })
  it('PARTNER_COLOR is set and distinct from both operator colours', () => {
    expect(PARTNER_COLOR).toMatch(/^#/)
    expect(PARTNER_COLOR).not.toBe(OPERATOR_COLOR.av)
    expect(PARTNER_COLOR).not.toBe(OPERATOR_COLOR.sonstige)
  })
})
