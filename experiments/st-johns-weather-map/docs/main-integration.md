# Experimental weather-map main integration

The owner explicitly authorized merging the existing weather-map PR stack into
main in the September 6, 2026 session. This consolidates the existing experiment
and supporting research; it does not promote any normative specification,
source admission or production release status. Experimental responses preserve
`operational: false`. Uncommitted root-worktree changes are excluded.

## Included PR heads

Every head below is an ancestor of the integration branch before its final
squash into main. The repository permits squash merges only, so the original
stacked PRs are superseded by the integration PR after the merge.

| PR | Pinned head |
| --- | --- |
| #31 | `e0bfc2c9e22bca9138f5a20cf3fb6f19408ba19d` |
| #32 | `af35c8435e6f070abb6dc65851826c81b3c37f1d` |
| #33 | `181170e4c4e7f7654da7d5ce28212c8ab768bbd2` |
| #34 | `954dfbb68866eeeaf0d26f6f3570aa7f5bd61eac` |
| #35 | `f5682ee9dde43f7ec141a70e156835de8c238529` |
| #36 | `3bc7ca8af493f0df98f5d8e442a58ca3864eab5a` |
| #37 | `f84b7725732432cd585a364381472210c0e47af6` |
| #128 | `fe9a24fd7fea47be6e9996b710f4f0deb98f1c5e` |
| #129 | `17bae937979670c58f86ae4c9ecaca384003e8b3` |
| #130 | `e1d134155a7009e5577cb820d89bcde791087167` |
| #131 | `fa8d368a066a601735d125b5a7234e386f4b591f` |
| #132 | `d9eccbff11dbae14185c0ae83d7e4acd3d059b9a` |
| #138 | `19a48dd88a476c0799aeda226ac403f8ece89570` |
| #139 | `0c5d629763a7046772fcc1df7d1b4635b2db01a8` |
| #146 | `3b63aa0a9bf37ffb8e0696bcff81eb53aa0516ae` |
| #149 | `21d48439858a96289dac5fca8e925d07f0a2cdbc` |
| #151 | `9bc0dd90d4102d96a20b086e6b7ba0f70911a4a0` |
| #156 | `d0ad3eee1ffb74c41abc5737c63c9cafffe06d68` |

This also includes the previously merged GFZ #152, GOES completion #154 and
SST #155 through their parent heads. Source-specific admission, freshness,
coverage and unavailable-provider limitations remain recorded by those changes.

## Integration corrections

- Preserve the updated ECMWF index URL tests alongside ECCC ensemble tests.
- Combine the space-weather and GOES registry declarations: 36 reach records
  and 31 statically discovered adapter identities, without scheduling isolated
  candidates merely because the audit discovers their classes.
- Remove duplicate provenance revision declarations introduced independently by
  SST and Open-Meteo, and regenerate the client catalogue from combined fields.
- Run the existing valid-time purge in periodic and one-shot worker maintenance.
- Commit metadata removal with queued deletion work; acknowledge claimed work
  only after object deletion or requeue failures in the same transaction.
  Interrupted claims roll back and successful deletes may replay idempotently.
- Close and remove stale/LRU API cache copies, including files from an earlier
  process and JSON copies, under the existing 32-entry cache ceiling.
- Correct pre-existing OpenSpec task grouping and repeat existing requirement
  wording in the body where the strict validator requires it. No rule changes.

## Verification

- `cd api && uv run pytest -o addopts='' -q`: 1,666 passed, 40 skipped.
- `PATH="$PWD/api/.venv/bin:$PATH" make test-registry`: profile audit valid;
  236 registry tests passed.
- `cd web && npm ci && npm test -- --run && npm run build`: 410 tests passed;
  TypeScript/Vite build passed. Existing large-bundle warning remains.
- `openspec validate --all --strict`: all 52 items passed.
- Repository `specctl.py validate`: zero errors and zero warnings; all 17
  specification-validator unit tests passed.
- `docker compose config --quiet`: passed.
- `git diff --check`: passed.
- All 18 open PR heads are included; history inspection found no provider-payload
  blobs over 100 KB. Large blobs are catalogue/research metadata, source code
  and the dependency lockfile. No live provider recapture was needed.

`WEATHER_SQL_TEST_CONTAINER=wx-main-integration-proof make test-sql` passed
against disposable PostgreSQL/PostGIS, including interrupted-claim rollback.
API skips include opt-in live/stack checks and unavailable optional runtimes;
this is local integration verification, not a deployed-stack acceptance claim.
The prior acquisition receipts remain the evidence for their dated captures.
The separate demand/preflight audit questions in the handoff remain follow-ups.
