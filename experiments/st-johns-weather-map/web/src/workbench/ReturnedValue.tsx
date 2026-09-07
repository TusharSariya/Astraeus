/** Readable structure for returned data; labels retain provider keys and no units are inferred. */
export function ReturnedValue({ value }: { value: unknown }) {
  if (value === null) return <span>Not supplied (null)</span>
  if (value === undefined) return <span>Not supplied</span>
  if (value === '') return <span>Empty text</span>
  if (Array.isArray(value)) return value.length
    ? <ol className="bench-returned-list">{value.map((item, index) => <li key={index}><ReturnedValue value={item} /></li>)}</ol>
    : <span>No entries returned</span>
  if (typeof value === 'object') {
    const entries = Object.entries(value)
    return entries.length ? <dl className="bench-returned-fields">{entries.map(([key, item]) => <div key={key}><dt>{key.replaceAll('_', ' ')}</dt><dd><ReturnedValue value={item} /></dd></div>)}</dl> : <span>No properties returned</span>
  }
  return <span>{String(value)}</span>
}

export function readableGeometry(value: unknown): unknown {
  if (!value || typeof value !== 'object' || !('type' in value) || !('coordinates' in value)) return value
  const coordinates = value.coordinates
  if (value.type !== 'Point' || !Array.isArray(coordinates) || coordinates.length !== 2 || !coordinates.every(item => typeof item === 'number' && Number.isFinite(item))) return value
  return { 'Geometry type': 'Point', Longitude: coordinates[0], Latitude: coordinates[1] }
}
