export interface Edit {
  apply(): void
  revert(): void
}

export function composite(edits: Edit[]): Edit {
  return {
    apply: () => edits.forEach((e) => e.apply()),
    revert: () => [...edits].reverse().forEach((e) => e.revert()),
  }
}

export class History {
  private done: Edit[] = []
  private undone: Edit[] = []
  private savedPos = 0

  run(edit: Edit): void {
    edit.apply()
    if (this.savedPos > this.done.length) this.savedPos = -1
    this.done.push(edit)
    this.undone = []
  }

  undo(): boolean {
    const edit = this.done.pop()
    if (!edit) return false
    edit.revert()
    this.undone.push(edit)
    return true
  }

  redo(): boolean {
    const edit = this.undone.pop()
    if (!edit) return false
    edit.apply()
    this.done.push(edit)
    return true
  }

  canUndo(): boolean {
    return this.done.length > 0
  }

  canRedo(): boolean {
    return this.undone.length > 0
  }

  markSaved(): void {
    this.savedPos = this.done.length
  }

  isDirty(): boolean {
    return this.done.length !== this.savedPos
  }
}
