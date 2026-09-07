# Selected desktop designs and apply order

This index consolidates the existing owner selections under Wayfinder #38 and
issue #55. It does not ask the owner to choose those layouts again, promote
prototype data into live evidence, or introduce new scientific behavior. Acceptance is recorded in [acceptance.md](acceptance.md).

| Area | Existing decision | Review asset |
| --- | --- | --- |
| Bench and Focus | [#39](https://github.com/TusharSariya/Astraeus/issues/39#issuecomment-5529784058): one stage, optional dock, shared place/time | [Shell prototype](https://github.com/TusharSariya/Astraeus/tree/prototype/shell-focus/experiments/st-johns-weather-map/web/public/prototypes) |
| Map | [#46](https://github.com/TusharSariya/Astraeus/issues/46#issuecomment-5532224119): legend as stack, off-map comparison | [Map prototype](https://github.com/TusharSariya/Astraeus/tree/prototype/map-stack/experiments/st-johns-weather-map/web/public/prototypes) |
| Provenance | [#40](https://github.com/TusharSariya/Astraeus/issues/40#issuecomment-5546998086): ledger and docked inspector, SVG glyphs | [Provenance prototype](https://github.com/TusharSariya/Astraeus/tree/prototype/provenance/experiments/st-johns-weather-map/web/public/prototypes) |
| Tokens | [#41](https://github.com/TusharSariya/Astraeus/issues/41): Hyperlegible C; red-on-black night supersedes Activity ember | [Canonical tokens](https://github.com/TusharSariya/Astraeus/tree/prototype/tokens/experiments/st-johns-weather-map/web/public/prototypes), [Figma library](https://www.figma.com/design/iPnQepf49VPoYovf9eMCNc) |
| Series | [#50](https://github.com/TusharSariya/Astraeus/issues/50#issuecomment-5548103502): Overview and temporary Compare | [Series prototype](https://github.com/TusharSariya/Astraeus/tree/prototype/series/experiments/st-johns-weather-map/web/public/prototypes) |
| Sky | [#51](https://github.com/TusharSariya/Astraeus/issues/51#issuecomment-5548244041): A Horizon instrument | [Sky prototype](https://github.com/TusharSariya/Astraeus/tree/prototype/sky/experiments/st-johns-weather-map/web/public/prototypes) |
| Activity | [#59](https://github.com/TusharSariya/Astraeus/issues/59): C Operational stack, component sheet D | [Selected artboard 1c and sheet 1d](https://claude.ai/design/p/7856b5dc-a351-43e0-ab3a-bf1b1e5f9a5f) |
| Sources | [#52](https://github.com/TusharSariya/Astraeus/issues/52#issuecomment-5548442947): Ledger default, Family finder, Coverage lanes | [Prototype and verification record](https://github.com/TusharSariya/Astraeus/issues/52#issuecomment-5548390196) |
| Station/point presentation | [#58](https://github.com/TusharSariya/Astraeus/issues/58#issuecomment-5548645284): Layer-led | Linked prototype in the decision record |
| Arbitrary point | [#67](https://github.com/TusharSariya/Astraeus/issues/67#issuecomment-5548841040): explicit site adoption, no borrowed horizon | Linked prototype in the decision record |
| Run selection | [#68](https://github.com/TusharSariya/Astraeus/issues/68#issuecomment-5548937642): scoped latest/previous/temporary comparison | Linked prototype in the decision record |
| Accessibility | [#69](https://github.com/TusharSariya/Astraeus/issues/69#issuecomment-5549029840): inspector focus entry/return and semantic alternatives | Repaired prototypes and bounded keyboard evidence in the decision record |

## Apply order and cross-change reconciliation

1. Keep the merged timestamp-demand source services and existing client logic.
   Do not require archived artifacts, scheduled ingestion or shared persistence
   to construct the shell.
2. Implement shared Focus/URL state, Bench, Map stack, selected tokens and the
   common provenance inspector against fixed API responses and a fixed clock.
3. Preserve existing working panels while implementing each selected view body.
   The selected Series, change-check, registry and imagery API capabilities
   are accepted through PR #256 under the same owner authorization. Do not manufacture missing endpoints in the client.
4. Wire Activity to server-returned verdicts under its owning #48/#49 contracts.
   This frontend change authorizes no new grading curves, safety decisions or
   score calculations. Camera eligibility remains truthful absence until the
   separate access/placement decision is resolved. Phone #53 remains deferred.
5. Verify all five selected views, shared Focus, source/provenance continuity,
   native gaps, failed reads, keyboard return and three themes. A shell-only
   merge or temporary unavailable body does not close the full desktop work.

The old Map prototype's generic frame tolerance does not override later
source-specific accepted timing, expiry or generated-display restrictions.
Use the actual served frame and fail closed when a drawable frame is absent.
The #41 red-on-black tokens supersede the older Activity ember colors only;
its selected layout and non-colour state encoding remain intact.
