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


@pytest.mark.asyncio
async def test_fuzzy_pass_continues_after_per_word_exception():
    """
    Regression test for the bug where an exception on any word in the fuzzy
    pass (Pass 2) aborted the entire sweep — later words were never tried
    even if they would have resolved correctly.

    Pass 1 (exact match) already had per-word exception isolation.
    Pass 2 (fuzzy) did not, causing one timeout or malformed response to
    silently drop all remaining candidate words.

    Strategy: rxnorm_lookup is a nested function inside resolve_to_generic
    so it cannot be patched directly. Instead we patch httpx.AsyncClient to:
    - Return empty exact-match results for all words (forcing the fuzzy pass)
    - Raise ConnectionError on the fuzzy search for "badword"
    - Return a valid rxcui for "paracetamol" on the fuzzy search

    Word order matters: the algorithm sweeps candidate words right-to-left,
    so "BadWord" must be the *rightmost* word (tried first) — otherwise
    Paracetamol would resolve on the first try and BadWord would never be
    reached, defeating the point of the test. We also match on the exact
    "name" param (not a substring check) so the full two-word phrase
    "Paracetamol BadWord" used in Step 1's direct lookup doesn't accidentally
    match either branch.

    Before the fix: ConnectionError on badword aborted the fuzzy loop entirely.
    After the fix: the loop continues and resolves paracetamol correctly.
    """
    from unittest.mock import AsyncMock, patch, MagicMock
    from services.drug_name_resolver import resolve_to_generic

    get_call_count = {"n": 0}

    async def smart_get(url, **kwargs):
        get_call_count["n"] += 1
        params = kwargs.get("params", {})
        name_param = params.get("name", "").lower()

        # Properties lookup after resolving rxcui — checked first, since this
        # call passes no params and would otherwise fall into the "no search
        # param" branch below and get treated as an exact-pass miss.
        if "/rxcui/161/properties" in url:
            mock = MagicMock()
            mock.json.return_value = {"properties": {"name": "Acetaminophen"}}
            return mock

        # Exact match pass (search=0) — always return empty so fuzzy pass runs
        if params.get("search") == 0 or "search" not in params:
            mock = MagicMock()
            mock.json.return_value = {"idGroup": {"rxnormId": []}}
            return mock

        # Fuzzy pass (search=1) — exact name match, not substring, so the
        # full "paracetamol badword" phrase from Step 1 doesn't collide.
        if name_param == "badword":
            raise ConnectionError("Simulated timeout on badword fuzzy lookup")

        if name_param == "paracetamol":
            mock = MagicMock()
            mock.json.return_value = {"idGroup": {"rxnormId": ["161"]}}
            return mock

        mock = MagicMock()
        mock.json.return_value = {"idGroup": {"rxnormId": []}}
        return mock

    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)
    mock_client.get = AsyncMock(side_effect=smart_get)

    with patch("httpx.AsyncClient", return_value=mock_client):
        result = await resolve_to_generic("Paracetamol BadWord")

    # The fuzzy pass must have continued past badword and resolved paracetamol
    assert result == "acetaminophen", (
        f"Expected acetaminophen but got {result!r}. "
        f"The fuzzy pass likely aborted on the badword exception instead of continuing."
    )
    # httpx.get was called multiple times — proving the loop did not abort early
    assert get_call_count["n"] >= 2, (
        f"httpx.get was called only {get_call_count['n']} time(s) — "
        f"expected multiple calls (exact pass + fuzzy pass for multiple words)"
    )