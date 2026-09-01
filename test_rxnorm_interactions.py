"""
Test RxNorm Drug Interaction API directly from your machine.
Run: python test_rxnorm_interactions.py
"""
import asyncio
import httpx

async def test():
    async with httpx.AsyncClient(timeout=10.0) as client:
        print("Step 1: Get rxcui for warfarin...")
        r = await client.get(
            "https://rxnav.nlm.nih.gov/REST/rxcui.json",
            params={"name": "warfarin", "search": 1}
        )
        warfarin_id = r.json().get("idGroup", {}).get("rxnormId", [None])[0]
        print(f"  Warfarin rxcui: {warfarin_id}")

        print("Step 2: Get rxcui for ibuprofen...")
        r = await client.get(
            "https://rxnav.nlm.nih.gov/REST/rxcui.json",
            params={"name": "ibuprofen", "search": 1}
        )
        ibuprofen_id = r.json().get("idGroup", {}).get("rxnormId", [None])[0]
        print(f"  Ibuprofen rxcui: {ibuprofen_id}")

        print("Step 3: Check interaction API...")
        r = await client.get(
            "https://rxnav.nlm.nih.gov/REST/interaction/list.json",
            params={"rxcuis": f"{warfarin_id} {ibuprofen_id}"}
        )
        print(f"  Status: {r.status_code}")
        print(f"  Body: {r.text[:500]}")

        print("\nStep 4: Try single drug interaction endpoint...")
        r = await client.get(
            "https://rxnav.nlm.nih.gov/REST/interaction/interaction.json",
            params={"rxcui": warfarin_id}
        )
        print(f"  Status: {r.status_code}")
        print(f"  Body: {r.text[:500]}")

asyncio.run(test())