import { useId, type ReactNode } from 'react'

// Only typographic shortening of explicit display names; quantities and qualifiers stay intact.
export function compactLayerName(title: string) {
  return title.replace(/^(HRDPS(?:-WEonG)?|RDPS|GDPS|GFS|GEFS|GEPS|GOES-East|GOES-West)\s+(?!·)/, '$1 · ')
}

/** Native primary button keeps Enter/Space semantics separate from details. */
export function LayerRow({ title, label = compactLayerName(title), selected, state, status, onPrimary, onDetails, visibility, primaryRef }: {
  title: string; label?: string; selected?: boolean; state?: string; status: string
  onPrimary: (opener: HTMLButtonElement) => void
  onDetails: (opener: HTMLButtonElement) => void
  visibility?: ReactNode; primaryRef?: (node: HTMLButtonElement | null) => void
}) {
  const statusId = useId()
  const compactStatus: Record<string, string> = {
    'Checking layer catalogue': 'Checking',
    'Catalogue request failed · availability unknown': 'Unknown',
    'Not in current catalogue · imagery not requested': 'Not listed',
    'Unavailable · no frame drawn': 'No frame',
    'No features returned': 'Empty',
    'Loading frame': 'Loading',
  }
  return <div className="dense-layer-row" onContextMenu={event => {
    event.preventDefault()
    const primary = event.currentTarget.querySelector<HTMLButtonElement>('.dense-layer-primary')
    if (primary) onDetails(primary)
  }} onKeyDown={event => {
    if (event.key === 'ContextMenu' || (event.shiftKey && event.key === 'F10')) {
      event.preventDefault(); event.stopPropagation()
      const primary = event.currentTarget.querySelector<HTMLButtonElement>('.dense-layer-primary')
      if (primary) onDetails(primary)
    }
  }}>
    {visibility}
    <button ref={primaryRef} className="dense-layer-primary" title={state ? `${title} · ${state}` : title} aria-label={title} aria-describedby={statusId} aria-description={state ? `${state}. Activate to cycle selection.` : 'Open source details.'} aria-pressed={selected} onClick={event => onPrimary(event.currentTarget)}>
      {selected !== undefined && <span className="dense-selection" aria-hidden="true">{state === 'Data only' ? '◐' : selected ? '●' : '○'}</span>}
      <span className="dense-layer-name">{label}</span>
      <span id={statusId} className="bench-layer-state" title={status}><span aria-hidden="true">{compactStatus[status] ?? status}</span><span className="visually-hidden">{status}</span></span>
    </button>
    <button className="dense-layer-details" aria-label={`Details for ${title}`} title={`Details for ${title}`} onClick={event => {
      const primary = event.currentTarget.parentElement?.querySelector<HTMLButtonElement>('.dense-layer-primary')
      if (primary) onDetails(primary)
    }}>⋯</button>
  </div>
}
