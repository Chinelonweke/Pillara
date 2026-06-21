# tests/integration/test_medications.py

import pytest
from httpx import AsyncClient


@pytest.fixture
async def profile_id(client: AsyncClient, auth_headers: dict) -> str:
    response = await client.get("/api/v1/profiles/", headers=auth_headers)
    return response.json()[0]["id"]


class TestMedicationCRUD:

    @pytest.mark.asyncio
    async def test_add_medication(self, client: AsyncClient, auth_headers: dict, profile_id: str):
        response = await client.post(
            f"/api/v1/medications/?profile_id={profile_id}",
            headers=auth_headers,
            json={"name": "Ibuprofen", "dosage": "400mg", "frequency": "twice daily"},
        )
        assert response.status_code == 201
        data = response.json()
        assert data["name"] == "Ibuprofen"

    @pytest.mark.asyncio
    async def test_duplicate_medication_rejected(self, client: AsyncClient, auth_headers: dict, profile_id: str):
        payload = {"name": "Aspirin"}
        first = await client.post(f"/api/v1/medications/?profile_id={profile_id}", headers=auth_headers, json=payload)
        assert first.status_code == 201

        second = await client.post(f"/api/v1/medications/?profile_id={profile_id}", headers=auth_headers, json=payload)
        assert second.status_code == 409

    @pytest.mark.asyncio
    async def test_update_medication_mass_assignment_blocked(
        self, client: AsyncClient, auth_headers: dict, profile_id: str
    ):
        """
        SECURITY: Attempting to send profile_id or id in the update body
        must not change ownership — those fields are silently ignored.
        """
        create_resp = await client.post(
            f"/api/v1/medications/?profile_id={profile_id}",
            headers=auth_headers,
            json={"name": "Metformin"},
        )
        med_id = create_resp.json()["id"]

        update_resp = await client.patch(
            f"/api/v1/medications/{med_id}",
            headers=auth_headers,
            json={
                "notes": "Take with food",
                "profile_id": "some-other-profile-id",  # should be ignored
                "id": "different-id",  # should be ignored
            },
        )
        assert update_resp.status_code == 200
        assert update_resp.json()["id"] == med_id  # unchanged
        assert update_resp.json()["profile_id"] == profile_id  # unchanged

    @pytest.mark.asyncio
    async def test_soft_delete_medication(self, client: AsyncClient, auth_headers: dict, profile_id: str):
        create_resp = await client.post(
            f"/api/v1/medications/?profile_id={profile_id}",
            headers=auth_headers,
            json={"name": "Lisinopril"},
        )
        med_id = create_resp.json()["id"]

        delete_resp = await client.delete(f"/api/v1/medications/{med_id}", headers=auth_headers)
        assert delete_resp.status_code == 200

        # Medication should not appear in default (active-only) list
        list_resp = await client.get(f"/api/v1/medications/?profile_id={profile_id}", headers=auth_headers)
        med_ids = [m["id"] for m in list_resp.json()]
        assert med_id not in med_ids

    @pytest.mark.asyncio
    async def test_unauthenticated_request_rejected(self, client: AsyncClient, profile_id: str):
        response = await client.get(f"/api/v1/medications/?profile_id={profile_id}")
        assert response.status_code == 401