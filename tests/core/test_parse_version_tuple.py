"""Acceptance gate (dogfood bench T2): _parse_version must return a fixed-length
3-tuple so version comparisons are correct.

Real bug: variable-length tuples mis-compare — (1,2) < (1,2,0) is True in Python,
so version "1.2" wrongly reads as OLDER than "1.2.0" (they are equal), which can
trip min-version gates. Worker must normalize to exactly 3 components.

This file is the fixed contract; the worker may NOT edit it.
"""

import pytest

from prd_taskmaster.mode_recommend import _parse_version as pv


@pytest.mark.parametrize("s,expected", [
    ("1.2.3", (1, 2, 3)),
    ("1.2", (1, 2, 0)),
    ("1", (1, 0, 0)),
    ("v2.0", (2, 0, 0)),
    ("1.2.3-rc1", (1, 2, 3)),
    ("1.2.3.4", (1, 2, 3)),     # extra components truncated to 3
    ("garbage", (0, 0, 0)),
    ("", (0, 0, 0)),
    ("1.two.3", (0, 0, 0)),
])
def test_parse_version_normalizes_to_3_tuple(s, expected):
    out = pv(s)
    assert out == expected
    assert len(out) == 3


def test_equal_versions_compare_equal_regression():
    # the actual bug this task fixes
    assert pv("1.2") == pv("1.2.0")
    assert not (pv("1.2") < pv("1.2.0"))


def test_ordering_still_correct():
    assert pv("1.2.0") < pv("1.3.0")
    assert pv("1.9.0") < pv("1.10.0")
    assert pv("2.0.0") > pv("1.99.99")
