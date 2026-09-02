import { execFileSync } from 'node:child_process'
import { fileURLToPath } from 'node:url'
import { dirname, resolve } from 'node:path'
import { describe, expect, it } from 'vitest'
import { FIELD_CATALOGUE_COPY, CATALOGUE_FAMILIES, CATALOGUE_FIELDS } from './fieldFamilies'

const webRoot = resolve(dirname(fileURLToPath(import.meta.url)), '..')

/** The interface keeps a copy of the catalogue's display metadata — family
 *  titles and notes, per-key definitions — because `/point` and `/catalog`
 *  carry only `family` and `key` and the page must not invent the words that
 *  say what a member measures. A copy is a liability the moment it drifts, so
 *  this is the test that makes it one the build catches: it re-derives the copy
 *  from `registry/fields.py` and `registry/fields.schema.json` and fails when
 *  what is checked in differs by a single character. */
describe('the field family copy is the catalogue, not a paraphrase of it', () => {
  it('is not stale against registry/fields.py or registry/fields.schema.json', () => {
    // `--check` re-runs `python3 -c "from registry import fields; ..."` and the
    // schema read, rebuilds the file and compares. It exits non-zero — failing
    // this test — when the copy is stale, and also when the catalogue cannot be
    // read at all, which is the right answer: an unverifiable copy is not a
    // verified one.
    const output = execFileSync('node', ['scripts/generate-field-families.mjs', '--check'], { cwd: webRoot, encoding: 'utf8' })
    expect(output).toContain('fresh:')
    expect(output).toContain(FIELD_CATALOGUE_COPY.fingerprint)
  })

  it('carries the families and members the interface groups by', () => {
    expect(FIELD_CATALOGUE_COPY.families.length).toBeGreaterThan(0)
    expect(FIELD_CATALOGUE_COPY.fields.length).toBeGreaterThan(0)
    expect(CATALOGUE_FAMILIES.cloud_cover.title).toBe('Cloud cover')
    // The three cloud keys the catalogue split apart. If a future catalogue
    // merges any pair of them back under one key, this fails, which is the
    // whole reason the change exists.
    for (const key of ['total_cloud_opacity', 'total_cloud_geometric', 'total_cloud_mean_6h']) {
      expect(CATALOGUE_FIELDS[key].family).toBe('cloud_cover')
    }
    const groups = new Set(['total_cloud_opacity', 'total_cloud_geometric', 'total_cloud_mean_6h'].map((key) => CATALOGUE_FIELDS[key].comparabilityGroup))
    expect(groups.size).toBe(3)
    // `total_cloud` itself is gone: it was three quantities under one key.
    expect(CATALOGUE_FIELDS.total_cloud).toBeUndefined()
  })
})
