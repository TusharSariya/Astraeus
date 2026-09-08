import { useEffect, useRef, useState, type ReactNode } from 'react'
import { VIEWS, type View } from './focusUrl'
import { Popover } from './Popover'
interface Props {
  view: View; dock: View | null; onView: (view: View) => void; onDock: (view: View | null) => void
  focus: ReactNode; status: ReactNode; statusLabel?: string; timeline: ReactNode; views: Record<View, ReactNode>
  onDismissInspector?: () => void; settings?: ReactNode; inspector?: ReactNode; layers?: ReactNode; evidence?: ReactNode; legends?: ReactNode
}
/** Mounted view slots preserve map camera and local view state across navigation/docking. */
export function WorkbenchShell({ view, dock, onView, onDock, focus, status, statusLabel = 'API state', timeline, views, inspector, layers, evidence, legends, settings, onDismissInspector }: Props) {
  const [fullScreen, setFullScreen] = useState<View | null>(null)
  const [panel, setPanel] = useState<'Layers' | 'Evidence' | null>(null)
  const panelOpener = useRef<HTMLButtonElement | null>(null)
  const evidenceButton = useRef<HTMLButtonElement | null>(null)
  const panelHeading = useRef<HTMLHeadingElement | null>(null)
  const returnTo = useRef<HTMLButtonElement | null>(null)
  const previousView = useRef(view)
  const lastVisible = useRef<Partial<Record<View, ReactNode>>>({})
  const shown = fullScreen ?? view
  useEffect(() => {
    const open = () => { panelOpener.current = evidenceButton.current; setPanel('Evidence') }
    window.addEventListener('bench-map-evidence', open)
    return () => window.removeEventListener('bench-map-evidence', open)
  }, [])
  useEffect(() => {
    document.title = `${view} · Avalon Evidence Bench`
    if (previousView.current !== view) { document.getElementById(`view-${view}`)?.focus(); previousView.current = view }
  }, [view])
  useEffect(() => { if (panel && !inspector) panelHeading.current?.focus() }, [panel, !!inspector])
  const exitFullScreen = () => { setFullScreen(null); requestAnimationFrame(() => {
    const opener = returnTo.current; const disclosure = opener?.closest('details')
    if (opener?.isConnected) (disclosure && !disclosure.open ? disclosure.querySelector('summary') : opener)?.focus()
    else document.getElementById('bench-stage')?.focus()
  }) }
  const closePanel = () => { setPanel(null); panelOpener.current?.focus() }
  const openPanel = (name: 'Layers' | 'Evidence', opener: HTMLButtonElement) => { panelOpener.current = opener; if (inspector) { onDismissInspector?.(); setPanel(name) } else setPanel(panel === name ? null : name) }
  return <div className={`bench${fullScreen ? ' bench-fullscreen' : ''}`} onKeyDown={event => {
    if (event.key !== 'Escape' || event.defaultPrevented) return
    if (panel && !inspector) { event.stopPropagation(); closePanel() }
    else if (fullScreen && !(event.target instanceof HTMLInputElement) && !(event.target instanceof HTMLSelectElement)) exitFullScreen()
  }}>
    <svg width="0" height="0" aria-hidden="true" style={{ position: 'absolute' }}><defs><filter id="bench-night-red" colorInterpolationFilters="sRGB"><feColorMatrix type="matrix" values="0.2126 0.7152 0.0722 0 0  0 0 0 0 0  0 0 0 0 0  0 0 0 1 0" /></filter></defs></svg>
    <a className="bench-skip" href="#bench-stage">Skip to evidence</a>
    <header className="bench-focus">
      <div className="bench-brand" title="Avalon Evidence Bench · Experimental, not operational"><h1>Avalon</h1></div>
      <Popover label={`View · ${shown}`} className="bench-view-menu">
        <nav aria-label="Evidence views">{VIEWS.map(name => <div key={name}>
          <button aria-pressed={view === name} onClick={event => { onView(name); if (dock === name) onDock(null); setFullScreen(null); const details = event.currentTarget.closest('details'); if (details) details.open = false; requestAnimationFrame(() => document.getElementById(`view-${name}`)?.focus()) }}>{name}</button>
          {name !== view && <button aria-label={`Dock ${name}`} aria-pressed={dock === name} onClick={() => onDock(dock === name ? null : name)}>Dock</button>}
        </div>)}</nav>
        <button onClick={event => { if (fullScreen) exitFullScreen(); else { returnTo.current = event.currentTarget; setFullScreen(view) } }}>{fullScreen ? 'Return to Bench' : `Expand ${view}`}</button>
      </Popover>
      {focus}
      <Popover title={statusLabel} label={<span role="status">{statusLabel}</span>} className="bench-api-state"><div>{status}</div></Popover>
      <button aria-expanded={panel === 'Layers' && !inspector} onClick={event => openPanel('Layers', event.currentTarget)}>Layers</button>
      <Popover label="Settings" className="bench-settings">{settings}</Popover>
    </header>
    <div className="bench-body">
      <main id="bench-stage" className={`bench-stage${!fullScreen && dock && dock !== view ? ' has-dock' : ''}`} tabIndex={-1}>
        {VIEWS.map(name => {
          const companion = !fullScreen && dock === name && dock !== view
          // Start a view only when requested. Retain its last visible props while
          // hidden so shared-clock changes do not acquire unseen Map frames.
          if (name === shown || companion) lastVisible.current[name] = views[name]
          return <section key={name} hidden={name !== shown && !companion} className={`bench-view ${name === 'Map' ? 'bench-map-view' : ''} ${companion ? 'bench-companion' : 'bench-primary'}`} aria-label={companion ? `${name} companion` : `${name} view`} role={companion ? 'complementary' : undefined}>
            <h2 id={`view-${name}`} className="visually-hidden" tabIndex={-1}>{name}</h2>
            {companion && <div className="bench-view-heading"><strong>{name}</strong><button onClick={() => onDock(null)}>Close {name} dock</button><button onClick={event => { returnTo.current = event.currentTarget; setFullScreen(name) }}>Expand {name}</button></div>}
            {lastVisible.current[name]}
          </section>
        })}
      </main>
      {(shown === 'Map' || dock === 'Map') && <div className="bench-map-tools"><button ref={evidenceButton} aria-expanded={panel === 'Evidence' && !inspector} onClick={event => openPanel('Evidence', event.currentTarget)}>Evidence</button><Popover label="Legends">{legends}</Popover></div>}
      <aside className="bench-overlay" hidden={!panel || !!inspector} aria-label={`${panel ?? 'Map'} overlay`}>
        <div className="bench-view-heading"><h2 ref={panelHeading} tabIndex={-1}>{panel}</h2><button onClick={closePanel}>Close {panel}</button></div>
        <div hidden={panel !== 'Layers'}>{layers}</div><div hidden={panel !== 'Evidence'}>{evidence}</div>
      </aside>
      {inspector && <div className="bench-overlay bench-provenance">{inspector}</div>}
    </div>
    <div className="bench-timeline">{timeline}</div>
  </div>
}
