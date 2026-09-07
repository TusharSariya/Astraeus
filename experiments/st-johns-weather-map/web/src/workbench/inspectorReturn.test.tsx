import { render, screen } from '@testing-library/react'
import { expect, it } from 'vitest'
import { captureInspectorReturn, restoreInspectorReturn } from './inspectorReturn'

it('restores a remounted dock disclosure and its unique logical opener', () => {
  const view = <section className="sources-view"><label>Find source<input type="search" /></label><details><summary>Readings</summary><button>Inspect returned zero</button></details></section>
  const rendered = render(view)
  screen.getByText('Readings').closest('details')!.open = true
  const target = captureInspectorReturn(screen.getByRole('button'))
  rendered.rerender(<aside>Inspector</aside>)
  rendered.rerender(view)
  restoreInspectorReturn(target)
  expect(screen.getByRole('button', {name:'Inspect returned zero'})).toHaveFocus()
  expect(screen.getByText('Readings').closest('details')?.open).toBe(true)
})

it('does not guess among repeated remounted actions and uses local search', () => {
  const rendered = render(<section className="sources-view"><button>Inspect source</button></section>)
  const target = captureInspectorReturn(screen.getByRole('button'))
  rendered.rerender(<aside>Inspector</aside>)
  rendered.rerender(<section className="sources-view"><input type="search" aria-label="Find source" /><button>Inspect source</button><button>Inspect source</button></section>)
  restoreInspectorReturn(target)
  expect(screen.getByRole('searchbox')).toHaveFocus()
})
