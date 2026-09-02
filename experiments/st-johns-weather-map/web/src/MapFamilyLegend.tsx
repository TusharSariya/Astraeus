import { layerFamily, layerFieldKey } from './api'
import {
  UNGROUPED_FAMILY,
  comparabilityGroupDefinition,
  familyNote,
  familyTitle,
  fieldDefinition,
  groupByFamily,
  layerComparability,
  resolveStorage,
  STORAGE_DESCRIPTIONS,
  STORAGE_LABELS,
} from './fieldFamily'
import type { LayerItem } from './types'

/** What the ramp on the map is a ramp OF.
 *
 *  A colour scale is meaningless without the definition it was drawn against,
 *  and two members of one family are drawn against different definitions: HRDPS
 *  cloud weights each layer by how much light it stops, GFS cloud is a
 *  geometric overlap that counts thin cirrus in full. Switching the map from
 *  one to the other therefore has to change what the legend SAYS, not only
 *  which image is fetched — otherwise the same scale appears to hold for two
 *  quantities that never shared one. */
export function LayerLegendDefinition({ layer }: { layer: LayerItem }) {
  const family = layerFamily(layer)
  const key = layerFieldKey(layer)
  const definition = comparabilityGroupDefinition(family, key)
  return (
    <p className="legend-definition" data-testid="legend-definition" data-field-key={key ?? ''} data-family={family}>
      <b>{familyTitle(family)}</b> · <code>{key ?? 'no catalogue key'}</code>
      {' — '}
      {definition ?? fieldDefinition(key)}
    </p>
  )
}

/** The active layers grouped by family, with the statement that has to appear
 *  whenever two of them are members of one family: they are separate scales.
 *
 *  Layers carry no comparability list — `/layers` serves none — so the pair is
 *  judged by the catalogue's own comparability group for each key. An unstated
 *  pair is treated exactly as a differing one: nothing is presented as a shared
 *  scale on the strength of a definition the catalogue copy could not name. */
export function ActiveFamilyLegends({ layers }: { layers: LayerItem[] }) {
  if (layers.length === 0) return null
  const groups = groupByFamily(layers, layerFamily)
  return (
    <div className="legend-families" data-testid="legend-families">
      {groups.map((group) => {
        const members = group.members
        const pairs = members.flatMap((left, index) => members.slice(index + 1).map((right) => ({ left, right })))
        const conflicting = group.family === UNGROUPED_FAMILY
          ? []
          : pairs.filter(({ left, right }) => layerComparability(layerFieldKey(left), layerFieldKey(right)) !== 'same')
        return (
          <section key={group.family} className="legend-family" aria-label={`${group.title} legends`} data-family={group.family}>
            <h5>{group.title}</h5>
            {members.map((layer) => (
              <div key={layer.id} className="legend-family-member">
                <b>{layer.title}</b>
                <LayerLegendDefinition layer={layer} />
                <LayerStorageLine layer={layer} />
              </div>
            ))}
            {conflicting.length > 0 && (
              <p className="legend-not-comparable" role="note" data-not-comparable="true">
                {conflicting.map(({ left, right }) => `${left.title} and ${right.title}`).join('; ')} are members of the
                {' '}{group.title} family measured by different definitions. Their colour scales are separate and are not
                one ramp; the two are never differenced here.
                {group.note ? ` ${group.note}` : ''}
              </p>
            )}
          </section>
        )
      })}
    </div>
  )
}

/** A layer whose field this deployment does not store, said as such on the map
 *  legend — distinct from a layer that simply has no frame at this instant. */
export function LayerStorageLine({ layer }: { layer: LayerItem }) {
  const storage = resolveStorage(layer.storage)
  if (!storage || storage === 'stored') return null
  return (
    <p className="legend-storage" data-storage={storage}>
      <b>{STORAGE_LABELS[storage]}</b> — {STORAGE_DESCRIPTIONS[storage]}
    </p>
  )
}

/** The same statement as prose, for the map's text alternative. */
export function describeLayerFamilySentence(layer: LayerItem): string {
  const family = layerFamily(layer)
  const key = layerFieldKey(layer)
  if (family === UNGROUPED_FAMILY) {
    return `Field family: none declared for this layer, so it is not grouped with any other. Key ${key ?? 'not declared'}.`
  }
  const note = familyNote(family)
  return `Field family ${familyTitle(family)}, member ${key ?? 'key not declared'}: ${comparabilityGroupDefinition(family, key) ?? fieldDefinition(key)}${note ? ` ${note}` : ''}`
}
