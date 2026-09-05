# Tasks

## 1. Authority reconciliation

- [x] 1.1 Reconcile all 288 roster rows into an authority matrix, preserving
      exact target tickets, eligibility, access gates and recorded dispositions.
      Verify: `python3 tools/specs/build_source_contract_matrix.py` reports 288
      rows and rejects loss, duplication or accidental operational state.
- [x] 1.2 Identify accepted authority separately from proposed V1 target shape
      and current experiment contracts. Result: governance alone is accepted;
      no behavior-bearing V1 ingestion contract currently authorizes production.
- [x] 1.3 Record the evidence-window and source-registry contract conflicts that
      require owner resolution under GOV-SPEC-005.
- [ ] 1.4 Obtain owner decisions on the evidence window, registry/admission
      baseline and this shared source contract. Do not self-promote status.

## 2. Per-source contract instances

- [ ] 2.1 For each eligible product/access path, instantiate the accepted
      contract with exact fields, access, identity, units, geometry, masks,
      limits, charge surfaces, failure semantics, API shape and rollback.
- [ ] 2.2 Keep experiments isolated and every source `operational: false` until
      owner acceptance and the complete evidence gate.

## 3. Shared verification

- [ ] 3.1 Add reusable fixture, live-smoke, artifact, API-readback and negative-
      path helpers after the owner accepts the contract surface they verify.
- [ ] 3.2 Require each integration ticket to attach exact commands and evidence
      for every selected field/member/lead; a partial proof does not close a
      family or count as admission.

## 4. Gate

- [x] 4.1 Validate the generated matrix, strict changed OpenSpec, repository
      specification graph and whitespace.

