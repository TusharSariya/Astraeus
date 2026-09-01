import { useId, useState } from 'react'
import type { InterpolationMethodItem } from './api'

/** The interpolation bench, as a menu.
 *
 *  One method is shown at a time, named on the map by the disclosure, so what
 *  produced the picture is never ambiguous. The list is the server's registry
 *  verbatim: a construction the derivation does not publish can never be
 *  offered here, and a method that has not met real frames yet says so rather
 *  than showing a zero, because "not measured" and "measured and beaten" are
 *  different facts.
 *
 *  Skill is reported against a reversed-motion control, not against a
 *  crossfade: any blend of two warps is smoother than the average of two
 *  frames, and a smoother field scores better against almost anything, so
 *  only the control says whether the direction carried information.
 */
export function MethodMenu({
  methods,
  active,
  onSelect,
  notices,
  error,
}: {
  methods: InterpolationMethodItem[]
  active: string
  onSelect: (methodId: string) => void
  notices: string[]
  error: string | null
}) {
  const [open, setOpen] = useState(false)
  const panelId = useId()
  const current = methods.find((method) => method.id === active)
  const label = current?.title ?? active

  return (
    <div className="method-menu">
      <button
        type="button"
        className="method-menu-toggle"
        aria-expanded={open}
        aria-controls={panelId}
        onClick={() => setOpen((value) => !value)}
      >
        Interpolation: <strong>{label}</strong>
      </button>
      {open && (
        <div className="method-menu-panel" id={panelId} role="group" aria-label="Interpolation method">
          <p className="method-menu-note">
            Display construction only. Every method here advects — they draw the same retrieved
            frames and differ in how those frames are warped and mixed between them. A plain
            cross-dissolve is not a choice on this list: it is the disclosed fallback wherever no
            motion was derived, or where the two warps say cloud grew in place rather than moved.
            Scores are held-out reconstructions of real frames, against the same construction with
            its motion reversed.
          </p>
          {error && <p className="method-menu-error">{error}</p>}
          {methods.length === 0 && !error && <p className="method-menu-error">no interpolation methods are published</p>}
          <ul className="method-list">
            {methods.map((method) => {
              const best = [...method.scores].sort(
                (a, b) => b.improvementOverReversedFlow - a.improvementOverReversedFlow,
              )[0]
              return (
                <li key={method.id}>
                  <label className={method.id === active ? 'method-option on' : 'method-option'}>
                    <input
                      type="radio"
                      name="interpolation-method"
                      value={method.id}
                      checked={method.id === active}
                      disabled={!method.enabled}
                      onChange={() => onSelect(method.id)}
                    />
                    <span className="method-option-name">
                      {method.title}
                      {method.generative && <em className="method-generated"> generates pixels</em>}
                    </span>
                  </label>
                  {method.summary && <p className="method-option-summary">{method.summary}</p>}
                  <p className="method-option-score">
                    {!method.published
                      ? 'not published by the current cycle'
                      : best
                        ? `best held-out skill ${(best.improvementOverReversedFlow * 100).toFixed(1)}% over the reversed-motion control on ${best.variable} (${best.heldOutFrames} frames held out)`
                        : 'published, not yet scored against a held-out frame'}
                  </p>
                </li>
              )
            })}
          </ul>
          {notices.map((notice) => (
            <p className="method-menu-error" key={notice}>
              {notice}
            </p>
          ))}
        </div>
      )}
    </div>
  )
}
