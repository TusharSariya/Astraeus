/** Preserve the actual opener, including when the one inspector temporarily replaces a dock. */
export function captureInspectorReturn(opener: HTMLButtonElement) {
  const selector = ['.activity-view', '.sources-view', '.native-series', '.sky-instrument', '.bench-map-evidence', '.bench-stack'].find(value => opener.closest(value))
  return { opener, selector, scope: selector ? opener.closest(selector) : null, name: opener.getAttribute('aria-label') ?? opener.textContent }
}
export type InspectorReturn = ReturnType<typeof captureInspectorReturn>
function focus(element: Element | null | undefined) {
  if (!(element instanceof HTMLElement) || !element.isConnected) return false
  element.focus()
  return document.activeElement === element
}
export function restoreInspectorReturn(target: InspectorReturn | null) {
  if (target && focus(target.opener)) return
  const scope = target?.selector ? document.querySelector(target.selector) : null
  // A replaced dock remounts its controls. Do not choose a different sample when
  // only the sample vanished from a still-mounted view (expiry or selection change).
  if (target?.scope && !target.scope.isConnected && scope) {
    const matches = [...scope.querySelectorAll('button')].filter(button => (button.getAttribute('aria-label') ?? button.textContent) === target.name)
    if (matches.length === 1) {
      let parent = matches[0].parentElement
      while (parent && parent !== scope) { if (parent instanceof HTMLDetailsElement) parent.open = true; parent = parent.parentElement }
      if (focus(matches[0])) return
    }
  }
  if (target?.selector === '.sources-view' && focus(scope?.querySelector('input[type="search"]'))) return
  if (target?.selector === '.native-series' && focus(scope?.querySelector('[data-inspector-return]'))) return
  if (target?.selector === '.sky-instrument' && focus(scope?.querySelector('[data-inspector-return]'))) return
  if (target?.selector === '.activity-view' && focus(scope?.querySelector('[data-inspector-return]'))) return
  focus(document.getElementById('bench-stage'))
}
