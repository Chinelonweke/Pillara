# tests/unit/test_drug_name_resolver.py
#
# Regression tests for two drug-identity bugs in the RxNorm word-extraction
# fallback (services/drug_name_resolver.py):
# 1. Salt suffixes ("Sodium", "Tartrate", ...) resolve to a real RxNorm rxcui
#    on their own, so the right-to-left match could pick the SALT FORM instead
#    of the actual active ingredient (e.g. "Diclofenac Sodium" -> "sodium").
# 2. A name with two independently-resolving ingredient words (a combination
#    product, e.g. "Amoxicillin Cloxacillin") silently kept only one match and
#    dropped the other, producing a confident answer about the wrong drug.
#
# All RxNorm HTTP calls are mocked — no network access.

from unittest.mock import AsyncMock, patch

import pytest

from services.drug_name_resolver import resolve_to_generic


def _rxcui_response(rxcui):
    """RxNorm /rxcui.json shape."""
    return {"idGroup": {"rxnormId": [rxcui] if rxcui else []}}


def _properties_response(name):
    """RxNorm /rxcui/{id}/properties.json shape."""
    return {"properties": {"name": name}}


class _FakeResponse:
    def __init__(self, payload):
        self._payload = payload

    def json(self):
        return self._payload


def _make_client_mock(lookup: dict):
    """
    lookup: {name.lower(): (rxcui, generic_name) or None}
    Simulates both the rxcui.json and properties.json RxNorm endpoints for
    exact-match (search=0) calls, keyed by the "name" query param.
    """
    async def fake_get(url, params=None, **kwargs):
        if url.endswith("/rxcui.json"):
            name = (params or {}).get("name", "").lower()
            match = lookup.get(name)
            return _FakeResponse(_rxcui_response(match[0] if match else None))
        if "/properties.json" in url:
            rxcui = url.rsplit("/", 2)[1]
            for match in lookup.values():
                if match and str(match[0]) == rxcui:
                    return _FakeResponse(_properties_response(match[1]))
            return _FakeResponse(_properties_response("unknown"))
        return _FakeResponse({})

    client = AsyncMock()
    client.get = AsyncMock(side_effect=fake_get)
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=False)
    return client


@pytest.mark.asyncio
async def test_salt_suffix_not_mistaken_for_active_ingredient():
    """'Diclofenac Sodium' must resolve to diclofenac, not sodium."""
    lookup = {
        "diclofenac sodium": None,          # full string: no exact match
        "diclofenac": ("11614", "diclofenac"),
        "sodium": ("9853", "sodium"),        # a real RxNorm ingredient on its own
    }
    with patch("httpx.AsyncClient", return_value=_make_client_mock(lookup)):
        result = await resolve_to_generic("Diclofenac Sodium")

    assert result == "diclofenac"


@pytest.mark.asyncio
async def test_combination_drug_not_silently_reduced_to_one_ingredient():
    """A name with two independently-resolving ingredients must not silently
    drop one — it should surface both rather than confidently return only one."""
    lookup = {
        "amoxicillin cloxacillin": None,     # full string: no exact match
        "amoxicillin": ("723", "amoxicillin"),
        "cloxacillin": ("2183", "cloxacillin"),
    }
    with patch("httpx.AsyncClient", return_value=_make_client_mock(lookup)):
        result = await resolve_to_generic("Amoxicillin Cloxacillin")

    assert "amoxicillin" in result
    assert "cloxacillin" in result


@pytest.mark.asyncio
async def test_single_ingredient_brand_still_resolves_normally():
    """Regression guard: a normal single-ingredient brand name must still
    resolve to just that ingredient (no false 'combination' detection)."""
    lookup = {
        "emzor paracetamol": None,
        "paracetamol": ("161", "acetaminophen"),
    }
    with patch("httpx.AsyncClient", return_value=_make_client_mock(lookup)):
        result = await resolve_to_generic("Emzor Paracetamol")

    assert result == "acetaminophen"
