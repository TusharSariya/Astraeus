#!/usr/bin/env node
// Generate `web/src/fieldFamilies.ts` from the field catalogue in
// `registry/fields.py`.
//
// Why a generated copy exists at all: the interface must show a family's title
// and note and a member's definition beside the key, and `/point` and
// `/catalog` carry only `family` and `key`. Rather than invent wording in the
// client — the one thing this change exists to prevent — the catalogue's own
// words are copied in, mechanically, and a test (`field-family-catalogue`)
// fails the build when the copy drifts from `registry/fields.py` or from
// `registry/fields.schema.json`.
//
// The copy is metadata ONLY: titles, notes, group definitions, per-key
// quantity/units/level/description. It is never consulted to decide which
// family a served value belongs to — that comes from the response's own
// `family`, and an absent one is `ungrouped`.
//
//   node scripts/generate-field-families.mjs           # write the copy
//   node scripts/generate-field-families.mjs --check   # exit 1 if stale

import { createHash } from 'node:crypto'
import { execFileSync } from 'node:child_process'
import { readFileSync, writeFileSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const here = dirname(fileURLToPath(import.meta.url))
const webRoot = resolve(here, '..')
const experimentRoot = resolve(webRoot, '..')
const target = resolve(webRoot, 'src/fieldFamilies.ts')
const schemaPath = resolve(experimentRoot, 'registry/fields.schema.json')

/** The catalogue as `registry/fields.py` publishes it. The exact command the
 *  change's tasks name, run from the experiment root so `registry` imports. */
export function readCatalogue() {
  const stdout = execFileSync(
    'python3',
    ['-c', 'from registry import fields; import json; print(json.dumps(fields.catalogue()))'],
    { cwd: experimentRoot, encoding: 'utf8', maxBuffer: 64 * 1024 * 1024 },
  )
  return JSON.parse(stdout)
}

export function readSchema() {
  return readFileSync(schemaPath, 'utf8')
}

function sha256(value) {
  return createHash('sha256').update(value).digest('hex')
}

/** The subset the interface renders, in a stable order. Everything the client
 *  never shows is left out on purpose: a copy that carries less drifts less. */
export function buildCopy(catalogue, schemaText) {
  const families = [...catalogue.families]
    .sort((a, b) => a.name.localeCompare(b.name))
    .map((family) => ({
      name: family.name,
      title: family.title,
      note: family.note,
      groups: Object.fromEntries(Object.entries(family.groups ?? {}).sort(([a], [b]) => a.localeCompare(b))),
    }))
  const fields = [...catalogue.fields]
    .sort((a, b) => a.key.localeCompare(b.key))
    .map((field) => ({
      key: field.key,
      family: field.family,
      quantity: field.quantity,
      units: field.units,
      level: field.level ?? null,
      comparabilityGroup: field.comparability_group ?? null,
      description: field.description,
    }))
  const copy = {
    version: catalogue.catalogue_version,
    asOf: catalogue.as_of,
    // Both inputs are in the fingerprint: a schema change that renames a
    // property the copy carries must fail the staleness test too, even when
    // the emitted values happen to be identical.
    fingerprint: sha256(JSON.stringify({ families, fields, schema: sha256(schemaText) })),
    families,
    fields,
  }
  return copy
}

const HEADER = `// GENERATED FILE — do not edit by hand.
//
// Written by \`web/scripts/generate-field-families.mjs\` from the field
// catalogue in \`registry/fields.py\` and the shape in
// \`registry/fields.schema.json\`. Regenerate with:
//
//     cd web && node scripts/generate-field-families.mjs
//
// \`src/field-family-catalogue.test.ts\` fails when this file is stale.
//
// This is DISPLAY METADATA ONLY: a family's title and note, a member's
// definition. A served value's family always comes from the response's own
// \`family\`; nothing here is ever used to guess one from a key's spelling.
`

export function render(copy) {
  const body = JSON.stringify(copy, null, 2)
  return `${HEADER}
export interface CatalogueFamilyCopy {
  name: string
  title: string
  note: string
  /** The comparability groups inside the family: the definitions that decide
   *  whether two members may share a ramp, an axis or a difference. */
  groups: Record<string, string>
}

export interface CatalogueFieldCopy {
  key: string
  family: string
  quantity: string
  units: string
  level: string | null
  comparabilityGroup: string | null
  description: string
}

export interface FieldCatalogueCopy {
  version: string
  asOf: string
  /** sha256 over the copied subset and the schema; the staleness test's hinge. */
  fingerprint: string
  families: CatalogueFamilyCopy[]
  fields: CatalogueFieldCopy[]
}

export const FIELD_CATALOGUE_COPY: FieldCatalogueCopy = ${body}

export const CATALOGUE_FAMILIES: Record<string, CatalogueFamilyCopy> = Object.fromEntries(
  FIELD_CATALOGUE_COPY.families.map((family) => [family.name, family]),
)

export const CATALOGUE_FIELDS: Record<string, CatalogueFieldCopy> = Object.fromEntries(
  FIELD_CATALOGUE_COPY.fields.map((field) => [field.key, field]),
)
`
}

function main() {
  const check = process.argv.includes('--check')
  const copy = buildCopy(readCatalogue(), readSchema())
  const rendered = render(copy)
  if (!check) {
    writeFileSync(target, rendered)
    process.stdout.write(`wrote ${target}: ${copy.families.length} families, ${copy.fields.length} fields, catalogue ${copy.version} (${copy.asOf})\n`)
    return
  }
  let existing = null
  try {
    existing = readFileSync(target, 'utf8')
  } catch {
    process.stderr.write(`${target} does not exist; run: node scripts/generate-field-families.mjs\n`)
    process.exit(1)
  }
  if (existing !== rendered) {
    process.stderr.write(
      `${target} is stale against registry/fields.py or registry/fields.schema.json.\n` +
      `Expected fingerprint ${copy.fingerprint}. Regenerate with: node scripts/generate-field-families.mjs\n`,
    )
    process.exit(1)
  }
  process.stdout.write(`fresh: ${copy.families.length} families, ${copy.fields.length} fields, fingerprint ${copy.fingerprint}\n`)
}

if (process.argv[1] && resolve(process.argv[1]) === resolve(fileURLToPath(import.meta.url))) main()
