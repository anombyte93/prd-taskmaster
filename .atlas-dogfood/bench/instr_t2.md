# Subtask T2: make _parse_version return a fixed-length 3-tuple

Work in the current repo (prd-taskmaster-public). Edit ONLY
`prd_taskmaster/mode_recommend.py` — specifically the `_parse_version` function.

## The bug
`_parse_version` currently returns a tuple whose length depends on the input
(e.g. "1.2" -> (1, 2)). Variable-length tuples mis-compare: (1, 2) < (1, 2, 0)
is True in Python, so version "1.2" wrongly sorts as OLDER than "1.2.0" even
though they are equal. This can trip minimum-version gates.

## Required behaviour (normalize to exactly 3 integer components)
- "1.2.3"   -> (1, 2, 3)
- "1.2"     -> (1, 2, 0)        # pad missing components with 0
- "1"       -> (1, 0, 0)
- "v2.0"    -> (2, 0, 0)        # leading 'v' stripped (existing behaviour)
- "1.2.3-rc1" -> (1, 2, 3)      # pre-release suffix ignored (existing behaviour)
- "1.2.3.4" -> (1, 2, 3)        # truncate extra components to 3
- "garbage" / "" / "1.two.3" -> (0, 0, 0)   # parse failure fallback
The returned tuple must ALWAYS have length 3.

## Hard constraints
- Edit ONLY `prd_taskmaster/mode_recommend.py`. Do NOT touch any file under tests/.
- Pure stdlib; keep the function's docstring accurate.

## Acceptance (must pass before you declare done)
    python -m pytest tests/core/test_parse_version_tuple.py -q
    ruff check prd_taskmaster/mode_recommend.py
Iterate until pytest is all-green AND ruff says "All checks passed".
