import { useId, useState } from 'react'
import type { InterpolationMethodItem, InterpolationMethodScore } from './api'

/** The interpolation bench, as a menu.
 *
 *  One method is shown at a time, named on the map by the disclosure, so what
 *  produced the picture is never ambiguous. The list is the server's registry
 *  verbatim: a construction the derivation does not publish can never be
 *  offered here, and a method that has not met real frames yet says so rather
 *  than showing a zero, because "not measured" and "measured and beaten" are
 *  different facts.
 *
 *  Every entry carries the server's own reader copy: one plain sentence, one
 *  "gap" sentence saying what it cannot show, and the cited science under a
 *  collapsed heading. Skill is reported against a FIXED control - a plain
 *  crossfade of the same two frames - together with how sharp the midpoint is
 *  relative to the real frame. The reversed-motion number decides only whether
 *  motion is displayed at all; it ranks nothing here and is not printed.
 *
 *  Generative constructions (carve-out (d)) sit under their own heading, off
 *  by default, and take two clicks: the first arms the entry and says so, the
 *  second selects. One refused by the deployment's kill switch is listed with
 *  the reason and cannot be chosen at all.
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
  const [armed, setArmed] = useState<string | null>(null)
  const panelId = useId()
  const current = methods.find((method) => method.id === active)
  const label = current?.title ?? active
  const plain = ranked(methods.filter((method) => !method.generative))
  const generated = ranked(methods.filter((method) => method.generative))

  const selectGenerated = (method: InterpolationMethodItem) => {
    if (method.generationDisabled || !method.enabled) return
    if (armed === method.id) {
      setArmed(null)
      onSelect(method.id)
    } else {
      setArmed(method.id)
    }
  }

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
            HRDPS&rsquo;s producer treats its hourly cloud timing as uncertain to about an hour (WEonG
            smooths it 0.25/0.5/0.25). Everything here is display between two real frames, never
            evidence.
          </p>
          {error && <p className="method-menu-error">{error}</p>}
          {methods.length === 0 && !error && <p className="method-menu-error">no interpolation methods are published</p>}
          <ul className="method-list">
            {plain.map((method) => (
              <li key={method.id}>
                <label className={method.id === active ? 'method-option on' : 'method-option'}>
                  <input
                    type="radio"
                    name="interpolation-method"
                    value={method.id}
                    checked={method.id === active}
                    disabled={!method.enabled}
                    onChange={() => { setArmed(null); onSelect(method.id) }}
                  />
                  <span className="method-option-name">{method.title}</span>
                </label>
                <MethodCopy method={method} />
              </li>
            ))}
          </ul>
          {generated.length > 0 && (
            <>
              <h3 className="method-group-heading">Generated (off by default)</h3>
              <ul className="method-list">
                {generated.map((method) => {
                  const selectable = method.enabled && !method.generationDisabled
                  const isArmed = armed === method.id
                  return (
                    <li key={method.id}>
                      <div className={method.id === active ? 'method-option on' : 'method-option'}>
                        <button
                          type="button"
                          className={`method-option-confirm${isArmed ? ' armed' : ''}`}
                          aria-pressed={method.id === active}
                          disabled={!selectable}
                          onClick={() => selectGenerated(method)}
                        >
                          {method.id === active ? 'selected' : isArmed ? 'confirm generated?' : 'select'}
                        </button>
                        <span className="method-option-name">
                          {method.title}
                          <em className="method-generated"> generates pixels</em>
                        </span>
                      </div>
                      {method.generationDisabled && (
                        <p className="method-option-unmet">disabled by WEATHER_GENERATED_DISPLAY</p>
                      )}
                      <MethodCopy method={method} />
                    </li>
                  )
                })}
              </ul>
            </>
          )}
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

/** The menu's order: best skill against the FIXED control first, within each
 *  group. Ranking on `improvementOverCrossfade` is the whole point of the
 *  fixed control - the reversed-motion number moves WITH the method and can
 *  order nothing. A method the current cycle has not scored keeps its registry
 *  position at the end of the list rather than being ranked at zero, because
 *  "not measured" and "measured and beaten" are different facts. */
function ranked(methods: InterpolationMethodItem[]): InterpolationMethodItem[] {
  const skill = (method: InterpolationMethodItem): number | null => {
    const best = bestScore(method)
    return best ? best.improvementOverCrossfade : null
  }
  return methods
    .map((method, index) => ({ method, index, skill: skill(method) }))
    .sort((a, b) => {
      if (a.skill === null || b.skill === null) {
        if (a.skill === b.skill) return a.index - b.index
        return a.skill === null ? 1 : -1
      }
      return b.skill - a.skill || a.index - b.index
    })
    .map((entry) => entry.method)
}

/** The best score by the fixed control. */
function bestScore(method: InterpolationMethodItem): InterpolationMethodScore | undefined {
  return [...method.scores].sort((a, b) => b.improvementOverCrossfade - a.improvementOverCrossfade)[0]
}

function scoreLine(method: InterpolationMethodItem): string {
  if (!method.published) return 'not published by the current cycle'
  const best = bestScore(method)
  if (!best) return 'not yet scored'
  const closer = `${(best.improvementOverCrossfade * 100).toFixed(1)}% closer to the real frame than a plain fade`
  const sharpness = best.midpointSharpnessRatio === null ? '' : `; sharpness ${best.midpointSharpnessRatio.toFixed(2)} of real`
  return `${closer}${sharpness} on ${best.variable} (${best.heldOutFrames} frames held out)`
}

function MethodCopy({ method }: { method: InterpolationMethodItem }) {
  return (
    <>
      {(method.plain || method.summary) && <p className="method-option-summary">{method.plain || method.summary}</p>}
      {method.gap && <p className="method-option-gap">Gap: {method.gap}</p>}
      {method.notes && (
        <details className="method-option-science">
          <summary>The science</summary>
          <p>{method.notes}</p>
        </details>
      )}
      {method.requirements.filter((item) => !item.met).map((item) => (
        <p className="method-option-unmet" key={item.name}>
          needs {item.name}: {item.detail}
        </p>
      ))}
      <p className="method-option-score">{scoreLine(method)}</p>
    </>
  )
}
