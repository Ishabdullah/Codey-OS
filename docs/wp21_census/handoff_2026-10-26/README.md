# Saved WP2.1 stop checkpoint — 2026-10-26

Read ../../WP2_1_HANDOFF_2026-10-26.md for the current state and resume order.

checkpoint.tar.gz preserves the complete incremental classification_units directory, relevant author/reviewer histories and source hashes, merge/stale/gate preparation, the approved B1 adapter and its failed-review predecessor, and the actual B1 run's raw output/phase/runtime records. All paths are relative to the original scratch root. artifact_manifest.json lists every archived regular file and its SHA256; the archive was read back and every entry verified. No symlinks or SQLite database contents are included. No scripts were run from this publication directory.

This is an uncommitted evidence backup, not independent classification/result/package approval. C5_FRESH3 is author-complete but awaiting review. C6_FRESH has159/181 rows and an explicit22-row resume checkpoint; old labels are unread. B1's16-case result awaits independent audit. Earlier approved classification and V-A publications are sibling directories; they remain separate and unchanged.

Prefer existing /data/data/com.termux/files/usr/tmp/wp21_closure_next/ when available. If scratch is lost, verify the archive SHA256 against the manifest and extract into a new owned scratch directory, never over the repository or existing evidence. Reconstruct frozen_source_770dc66 using local git archive770dc6639e4100ea3215fca07d923769a8290078 and verify every file against frozen_source_manifest.json. Adapt scratch-location references explicitly and re-review runtime setup before further product replay; never execute these adapters directly from the repository. Do not redo completed source-first maps because an old absolute path changed.

Raw trailing TSV cells and literal output whitespace are preserved. Further replay/source/gate work must follow project review and isolation rules. No closure, new risk acceptance or live integration is claimed.
