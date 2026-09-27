/** Resolves persisted hut GUIDs to the current payload's positional hut indices. The manifest's
 *  hutIds are GUIDs in payload order; only the GUID is stable across pipeline reruns, so anything
 *  saved must store GUIDs and resolve them here on load. A GUID absent from the current payload
 *  resolves to null; callers must drop or flag that reference rather than substitute another hut. */
export function resolveHutGuids(hutIds: readonly string[], guids: readonly string[]): (number | null)[] {
  const indexByGuid = new Map(hutIds.map((guid, i) => [guid, i] as const))
  return guids.map((guid) => indexByGuid.get(guid) ?? null)
}

export function hutGuidsForIndices(hutIds: readonly string[], indices: readonly number[]): string[] {
  return indices.map((i) => hutIds[i])
}
