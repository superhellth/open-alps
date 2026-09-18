import { describe, it, expect } from 'vitest'
import { History, composite, type Edit } from './history.js'

function counterEdit(log: string[], name: string): Edit {
  return { apply: () => log.push(`+${name}`), revert: () => log.push(`-${name}`) }
}

describe('History', () => {
  it('run applies, undo reverts, redo re-applies', () => {
    const log: string[] = []
    const h = new History()
    h.run(counterEdit(log, 'a'))
    expect(h.undo()).toBe(true)
    expect(h.redo()).toBe(true)
    expect(log).toEqual(['+a', '-a', '+a'])
    expect(h.undo() && h.undo()).toBe(false)
  })

  it('a new edit clears the redo stack', () => {
    const h = new History()
    h.run(counterEdit([], 'a'))
    h.undo()
    h.run(counterEdit([], 'b'))
    expect(h.canRedo()).toBe(false)
  })

  it('dirty tracks the saved position, incl. undo back to it', () => {
    const h = new History()
    expect(h.isDirty()).toBe(false)
    h.run(counterEdit([], 'a'))
    expect(h.isDirty()).toBe(true)
    h.markSaved()
    expect(h.isDirty()).toBe(false)
    h.run(counterEdit([], 'b'))
    h.undo()
    expect(h.isDirty()).toBe(false)
    h.undo()
    expect(h.isDirty()).toBe(true)
  })

  it('saved state lost when redo branch is discarded', () => {
    const h = new History()
    h.run(counterEdit([], 'a'))
    h.markSaved()
    h.undo()
    h.run(counterEdit([], 'b'))
    h.undo()
    expect(h.isDirty()).toBe(true)
  })

  it('composite applies in order and reverts in reverse', () => {
    const log: string[] = []
    const c = composite([counterEdit(log, 'a'), counterEdit(log, 'b')])
    c.apply()
    c.revert()
    expect(log).toEqual(['+a', '+b', '-b', '-a'])
  })
})
