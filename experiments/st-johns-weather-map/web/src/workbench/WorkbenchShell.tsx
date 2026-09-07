import { useEffect, useRef, useState, type ReactNode } from 'react'
import { VIEWS, type View } from './focusUrl'

interface Props {
  view: View
  dock: View | null
  onView: (view: View) => void
  onDock: (view: View | null) => void
  focus: ReactNode
  status: ReactNode
  timeline: ReactNode
  views: Record<View, ReactNode>
  inspector?: ReactNode
}

/** One Focus owner, one stage and at most one companion. View bodies do not own clocks. */
export function WorkbenchShell({ view, dock, onView, onDock, focus, status, timeline, views, inspector }: Props) {
  const [fullScreen, setFullScreen] = useState<View | null>(null)
  const returnTo = useRef<HTMLButtonElement | null>(null)
  const stage = useRef<HTMLHeadingElement | null>(null)
  const previousView = useRef(view)
  useEffect(() => {
    document.title = `${view} · Avalon Evidence Bench`
    if (previousView.current !== view) { stage.current?.focus(); previousView.current = view }
  }, [view])
  const exitFullScreen = () => {
    setFullScreen(null)
    requestAnimationFrame(() => {
      if (returnTo.current?.isConnected) returnTo.current.focus()
      else stage.current?.focus()
    })
  }
  const shown = fullScreen ?? view
  return <div className={`bench${fullScreen ? ' bench-fullscreen' : ''}`} onKeyDown={(event) => {
    if (event.key === 'Escape' && fullScreen && !event.defaultPrevented && !(event.target instanceof HTMLInputElement) && !(event.target instanceof HTMLSelectElement)) {
      event.stopPropagation(); exitFullScreen()
    }
  }}>
    <svg width="0" height="0" aria-hidden="true" style={{ position: 'absolute' }}><defs><filter id="bench-night-red" colorInterpolationFilters="sRGB"><feColorMatrix type="matrix" values="0.2126 0.7152 0.0722 0 0  0 0 0 0 0  0 0 0 0 0  0 0 0 1 0" /></filter></defs></svg>
    <a className="bench-skip" href="#bench-stage">Skip to evidence</a>
    <header className="bench-focus">{focus}</header>
    <div className="bench-status" role="status">{status}</div>
    <div className="bench-body">
      {!fullScreen && <nav className="bench-rail" aria-label="Evidence views">
        {VIEWS.map((name, index) => <div key={name}>
          <button aria-pressed={view === name} onClick={() => { onView(name); if (dock === name) onDock(null) }}><span aria-hidden="true">0{index + 1}</span>{name}</button>
          {name !== view && <button className="bench-dock-control" aria-label={`Dock ${name}`} aria-pressed={dock === name} onClick={() => onDock(dock === name ? null : name)}>Dock</button>}
        </div>)}
      </nav>}
      <main id="bench-stage" className="bench-stage" tabIndex={-1}>
        <div className="bench-view-heading"><h2 ref={stage} tabIndex={-1}>{shown}</h2>
          <button onClick={(event) => { if (fullScreen) exitFullScreen(); else { returnTo.current = event.currentTarget; setFullScreen(view) } }}>{fullScreen ? 'Return to Bench' : `Expand ${view}`}</button>
        </div>
        {views[shown]}
      </main>
      {inspector || (!fullScreen && dock && dock !== view && <aside className="bench-companion" aria-label={`${dock} companion`}>
        <div className="bench-view-heading"><h2>{dock}</h2><button onClick={() => onDock(null)}>Close {dock} dock</button><button onClick={(event) => { returnTo.current = event.currentTarget; setFullScreen(dock) }}>Expand {dock}</button></div>
        {views[dock]}
      </aside>)}
    </div>
    <div className="bench-timeline">{timeline}</div>
  </div>
}
