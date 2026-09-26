/** Returns the cached promise for `key`, starting it with `load` on a miss. A promise that rejects is
 *  evicted, so the next call retries instead of repeating the failure for the rest of the session. */
export function cachedPromise<K, V>(cache: Map<K, Promise<V>>, key: K, load: () => Promise<V>): Promise<V> {
  let cached = cache.get(key)
  if (!cached) {
    const started = load()
    cached = started
    cache.set(key, started)
    started.catch(() => {
      if (cache.get(key) === started) cache.delete(key)
    })
  }
  return cached
}
