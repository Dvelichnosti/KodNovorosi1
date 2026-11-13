from __future__ import annotations

import pytest

from tests.conftest import admin_tokens, auth_headers, login


async def create_org(client, headers: dict, name: str) -> dict:
    response = await client.post(
        "/api/v1/organizations",
        headers=headers,
        json={
            "type": "legal_entity",
            "name": name,
            "region": "dnr",
            "phone": "+79996660001",
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


async def create_and_submit_listing(client, headers: dict, org_id: str) -> dict:
    catalog = await client.get("/api/v1/catalog/categories")
    assert catalog.status_code == 200
    equipment = next(
        item for item in catalog.json() if item["slug"] == "oborudovanie"
    )
    child = next(
        item
        for item in equipment["children"]
        if item["slug"].endswith("proizvodstvennoe")
    )

    created = await client.post(
        "/api/v1/listings",
        headers=headers,
        json={
            "title": "Промышленный пресс для металла",
            "description": "Продаём промышленный пресс, состояние рабочее, 2019 год.",
            "category_id": child["id"],
            "type": "sale",
            "region": "dnr",
            "city": "Донецк",
            "price": 480000,
            "attributes": {"condition": "used", "year": 2019},
            "organization_id": org_id,
            "contact_phone": "+79996660001",
        },
    )
    assert created.status_code == 201, created.text
    listing = created.json()

    submitted = await client.post(
        f"/api/v1/listings/{listing['id']}/submit", headers=headers
    )
    assert submitted.status_code == 200, submitted.text
    return listing


async def approve(client, mfa_headers: dict, listing_id: str) -> dict:
    response = await client.post(
        f"/api/v1/admin/listings/{listing_id}/approve", headers=mfa_headers
    )
    assert response.status_code == 200, response.text
    return response.json()


async def role_by_name(client, headers: dict, org_id: str, name: str) -> dict:
    response = await client.get(
        f"/api/v1/organizations/{org_id}/roles", headers=headers
    )
    assert response.status_code == 200, response.text
    return next(item for item in response.json() if item["name"] == name)


@pytest.mark.asyncio
async def test_favorites_and_complaint_moderation(client):
    owner_tokens = await login(client, 331001, "+79993310001", "Владелец")
    owner_headers = auth_headers(owner_tokens)
    visitor_tokens = await login(client, 331002, "+79993310002", "Посетитель")
    visitor_headers = auth_headers(visitor_tokens)

    org = await create_org(client, owner_headers, "ООО Прессы")
    listing = await create_and_submit_listing(client, owner_headers, org["id"])

    mfa_headers = auth_headers(await admin_tokens(client))
    active = await approve(client, mfa_headers, listing["id"])
    assert active["status"] == "active"
    assert active["favorites_count"] == 0

    # A visitor sees contacts but has no favorites yet.
    card = await client.get(f"/api/v1/listings/{listing['id']}", headers=visitor_headers)
    assert card.status_code == 200, card.text
    assert card.json()["contacts_available"] is True
    assert card.json()["is_favorite"] is False

    # Add to favorites: idempotent and reflected in the listing and the list.
    added = await client.post(
        f"/api/v1/listings/{listing['id']}/favorite", headers=visitor_headers
    )
    assert added.status_code == 200, added.text
    repeated = await client.post(
        f"/api/v1/listings/{listing['id']}/favorite", headers=visitor_headers
    )
    assert repeated.status_code == 200

    favorites = await client.get("/api/v1/users/me/favorites", headers=visitor_headers)
    assert favorites.status_code == 200, favorites.text
    assert favorites.json()["total"] == 1
    assert favorites.json()["items"][0]["id"] == listing["id"]
    assert favorites.json()["items"][0]["is_favorite"] is True

    refreshed = await client.get(
        f"/api/v1/listings/{listing['id']}", headers=visitor_headers
    )
    assert refreshed.json()["favorites_count"] == 1
    assert refreshed.json()["is_favorite"] is True

    removed = await client.delete(
        f"/api/v1/listings/{listing['id']}/favorite", headers=visitor_headers
    )
    assert removed.status_code == 200, removed.text
    assert (
        await client.get("/api/v1/users/me/favorites", headers=visitor_headers)
    ).json()["total"] == 0
    assert (
        await client.get(f"/api/v1/listings/{listing['id']}", headers=visitor_headers)
    ).json()["favorites_count"] == 0

    # The owner cannot complain about their own listing.
    own = await client.post(
        f"/api/v1/listings/{listing['id']}/complaints",
        headers=owner_headers,
        json={"reason": "spam"},
    )
    assert own.status_code == 409
    assert own.json()["error"]["code"] == "own_listing_complaint"

    # Invalid reasons are rejected before a complaint is stored.
    invalid = await client.post(
        f"/api/v1/listings/{listing['id']}/complaints",
        headers=visitor_headers,
        json={"reason": "not-a-reason"},
    )
    assert invalid.status_code == 422
    assert invalid.json()["error"]["code"] == "invalid_complaint_reason"

    # A visitor files a valid complaint.
    complaint_response = await client.post(
        f"/api/v1/listings/{listing['id']}/complaints",
        headers=visitor_headers,
        json={"reason": "fraud", "comment": "Просят предоплату без договора"},
    )
    assert complaint_response.status_code == 201, complaint_response.text
    complaint = complaint_response.json()
    visitor_me = await client.get("/api/v1/users/me", headers=visitor_headers)
    assert visitor_me.status_code == 200
    assert complaint["status"] == "new"
    assert complaint["complainant"]["id"] == visitor_me.json()["id"]

    # A member of the listing's organization cannot complain about it.
    viewer_role = await role_by_name(client, owner_headers, org["id"], "Только просмотр")
    invitation = await client.post(
        f"/api/v1/organizations/{org['id']}/invitations",
        headers=owner_headers,
        json={"role_id": viewer_role["id"]},
    )
    assert invitation.status_code == 201, invitation.text
    accepted = await client.post(
        f"/api/v1/invitations/{invitation.json()['token']}/accept",
        headers=visitor_headers,
    )
    assert accepted.status_code == 200, accepted.text

    own_org = await client.post(
        f"/api/v1/listings/{listing['id']}/complaints",
        headers=visitor_headers,
        json={"reason": "spam"},
    )
    assert own_org.status_code == 409
    assert own_org.json()["error"]["code"] == "own_org_complaint"

    # Admins take the complaint into work and resolve it.
    queue = await client.get(
        "/api/v1/admin/complaints",
        headers=mfa_headers,
        params={"status": "new"},
    )
    assert queue.status_code == 200, queue.text
    assert any(item["id"] == complaint["id"] for item in queue.json()["items"])

    taken = await client.post(
        f"/api/v1/admin/complaints/{complaint['id']}/take", headers=mfa_headers
    )
    assert taken.status_code == 200, taken.text
    assert taken.json()["status"] == "in_review"

    resolved = await client.post(
        f"/api/v1/admin/complaints/{complaint['id']}/resolve",
        headers=mfa_headers,
        json={"status": "resolved", "resolution": "Объявление проверено, нарушений нет."},
    )
    assert resolved.status_code == 200, resolved.text
    assert resolved.json()["status"] == "resolved"
    assert resolved.json()["resolution"].startswith("Объявление проверено")

    # Every moderation decision is audited.
    audit = await client.get(
        "/api/v1/admin/audit",
        headers=mfa_headers,
        params={"action": "complaint.resolve"},
    )
    assert audit.status_code == 200, audit.text
    assert audit.json()["total"] >= 1
    assert any(
        item["entity_id"] == complaint["id"] for item in audit.json()["items"]
    )
