# HGCROC event skim (`DataPrep -X`)

`-X` enables `Analyses::SkimHGCROCData()`. An event passes when **any** tile
has `GetRawTOA() > 0` or `GetLocalTriggerBit() == 1`. Every tile in a passing
event is retained, including tiles that do not individually satisfy either
condition. Empty events and events with no qualifying tile are omitted.

The trigger decision must be complete before removing tiles. Previously,
trigger evaluation and deletion shared one loop: tiles preceding the first
qualifying tile were deleted, while that tile and the rest of the event
survived. The output therefore depended on tile order.

The corrected routine first scans all tiles, then removes tiles only from
events that fail the event-level decision. Trigger conditions, tile payloads,
accepted-event ordering, geometry and calibration metadata are unchanged.

## Where it is used

The FullSetE_1 Yall examples run `DataPrep -X` in `select-e1`, after initial
MIP extraction and before refinements. All five refinements read the selected
event file. The shell helper's `saveNewMuon` mode also invokes `-X`; its
`default` initial MIP mode does not. Availability of either mode in a script
does not establish which mode was used in a historical production campaign.

The [published MIP calibration note](https://github.com/FriederikeBock/epic-LFHCal-TB-ana-docu/blob/main/calibration/mip-calibration.md),
reviewed on 2026-09-22, explicitly includes `saveNewMuon` in its November 2025
and April 2026 HGCROC instructions, with both full-file and skimmed-file
refinement options. Those instructions do not record which path was actually
used for the May 2026 SPS H2 FullSetE_1 reference calibration.

Existing skimmed outputs cannot recover deleted tiles. To assess this fix,
rebuild DataPrep and rerun selection from the pre-skim MIP event file, then
rerun dependent refinements into a fresh output directory. This correction
does not require repeating conversion, pedestal extraction or initial MIP
fitting when their matching input/output files are retained. Preserve the
previous results as the comparison baseline.

## Regression test

With `BUILD_TESTING=ON`, the `hgcroc_skim_write`, `hgcroc_skim_run`, and
`hgcroc_skim_read` CTest fixtures create synthetic HGCROC events, run the real
DataPrep executable with `-X`, and verify the output. TOA and local-bit triggers
at the first, middle and last tile test order independence; untriggered and
empty events test rejection and resetting the decision between events.
The verification checks retained tile order and payload, not just event counts.

Run `ctest --test-dir build -R hgcroc_skim --output-on-failure` after building
`DataPrep` and `test_hgcroc_skim`.
