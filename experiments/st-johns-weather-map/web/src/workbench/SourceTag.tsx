import tokens from './providerTokens.json'

/** Selected presentation slots, never a provenance or admission inference. */
export function sourceStyle(id: string | null | undefined) {
  const provider = tokens.sources.find((entry) => entry.sources.includes(id ?? ''))
  const slot = provider?.slot ?? 8
  const index = provider?.sources.indexOf(id ?? '') ?? -1
  const model = tokens.modelStyles[index] ?? 'solid'
  return { slot, model, group: provider?.provider ?? 'Other' }
}
export function sourceAttributes(id: string | null | undefined) {
  const { slot, model } = sourceStyle(id)
  return { 'data-provider-slot': slot, 'data-model-style': model }
}
export function SourceTag({ id }: { id: string | null | undefined }) {
  return <span className="bench-source-tag" {...sourceAttributes(id)} title={`${sourceStyle(id).group} presentation slot; source identity is printed`}><svg viewBox="0 0 28 12" width="28" height="12" aria-hidden="true"><path d="M1 6H27" fill="none" stroke="currentColor" strokeWidth="2" /></svg><span>{id ?? 'Source not supplied'}</span></span>
}
