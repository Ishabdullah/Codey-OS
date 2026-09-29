---
name: migrate-aigentik-bool01-int-widening-approved
description: NEW-454 _bool01/_nullable_bool01 widened to accept bare int 0/1 in migrate_aigentik.py — approved r1
metadata:
  type: project
---

NEW-454 round 1: `_bool01()` / `_nullable_bool01()` in `restoricon_core/migrate_aigentik.py`
now also accept bare int `0`/`1` (Aigentik B2-fin-1 write-through writes ints to profile.json).

**Why approved:** bool branch stays first (isinstance(True,int) trap avoided); `isinstance(v,int) and v in (0,1)`
guard correctly rejects `1.0` (float), `2`/`-1` (range), `"1"`/`"true"` (str); nullable still returns None for None.
Verified by direct python exec of all edge cases. Widening only converts previously-erroring inputs to accepted —
cannot regress previously-passing behavior. All 10 call sites are 0/1 CHECK columns incl dnc_status. 5 new tests
are real discriminators (test_map_profile_rejects_float_one fails a naive `v in (0,1)` impl). `pytest tests/test_restoricon_core/` = 436 passed.

**How to apply:** if this logic is touched again, re-run the edge-case exec; string "0"/"1" are deliberately NOT accepted.
