"""Runtime limits configurable via environment variables.

paper_7bd78579 (hyper_kggen) hit max_iterations=800 with 24/28 files
written — substantive code (300-650 lines/file) but ran out of budget
on a complex 26-py-file plan. Bumping default to 1200 gives ~50% more
headroom for larger reproduction plans without making short ones slower.
"""

import os

import pytest

from workflows.runtime_limits import max_impl_iterations


@pytest.fixture(autouse=True)
def _clear_env(monkeypatch):
    monkeypatch.delenv("PAPER2CODE_MAX_IMPL_ITERATIONS", raising=False)
    yield


def test_default_is_1200():
    assert max_impl_iterations() == 1200


def test_env_override_positive():
    os.environ["PAPER2CODE_MAX_IMPL_ITERATIONS"] = "2000"
    try:
        assert max_impl_iterations() == 2000
    finally:
        del os.environ["PAPER2CODE_MAX_IMPL_ITERATIONS"]


def test_env_override_invalid_falls_back_to_default():
    os.environ["PAPER2CODE_MAX_IMPL_ITERATIONS"] = "not_a_number"
    try:
        assert max_impl_iterations() == 1200
    finally:
        del os.environ["PAPER2CODE_MAX_IMPL_ITERATIONS"]


def test_env_override_zero_or_negative_falls_back():
    os.environ["PAPER2CODE_MAX_IMPL_ITERATIONS"] = "0"
    try:
        assert max_impl_iterations() == 1200
    finally:
        del os.environ["PAPER2CODE_MAX_IMPL_ITERATIONS"]
    os.environ["PAPER2CODE_MAX_IMPL_ITERATIONS"] = "-5"
    try:
        assert max_impl_iterations() == 1200
    finally:
        del os.environ["PAPER2CODE_MAX_IMPL_ITERATIONS"]
