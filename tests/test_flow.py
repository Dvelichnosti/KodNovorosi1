from __future__ import annotations

import pytest

from tests.conftest import admin_tokens, auth_headers, login


@pytest.mark.asyncio
async def test_full_listing_lifecycle_and_contacts_visibility(client):
    # 1. Login as a regular user.
    user_tokens = await login(client, 111001, "+79991110001", "Иван")
    user_headers = auth_headers(user_tokens)

    me = await client.get("/api/v1/users/me", headers=user_headers)
    assert me.status_code == 200
    assert me.json()["phone_verified"] is True

    # 2. Create an organization; the creator becomes the owner.
    org_response = await client.post(
        "/api/v1/organizations",
        headers=user_headers,
        json={
            "type": "legal_entity",
            "name": "ООО Ромашка",
            "region": "dnr",
            "phone": "+79991110001",
            "description": "Поставка оборудования",
        },
    )
    assert org_response.status_code == 201, org_response.text
    org = org_response.json()
    assert org["members_count"] == 1
    assert org["plan"]["code"] == "free"
    assert org["phone_verified"] is True

    roles = await client.get(
        f"/api/v1/organizations/{org['id']}/roles", headers=user_headers
    )
    assert roles.status_code == 200
    assert len(roles.json()) >= 3

    # 3. Pick a category from the catalog.
    catalog = await client.get("/api/v1/catalog/categories")
    assert catalog.status_code == 200
    roots = catalog.json()
    equipment = next(item for item in roots if item["slug"] == "oborudovanie")
    child = next(
        item for item in equipment["children"] if item["slug"].endswith("proizvodstvennoe")
    )

    # The child inherits the required `condition` attribute from the root.
    detail = await client.get(f"/api/v1/catalog/categories/{child['id']}")
    assert detail.status_code == 200
    inherited = {item["key"]: item for item in detail.json()["inherited_attributes"]}
    assert inherited["condition"]["is_required"] is True

    # 4. Create a draft listing.
    listing_response = await client.post(
        "/api/v1/listings",
        headers=user_headers,
        json={
            "title": "Станок токарный в отличном состоянии",
            "description": "Продаём производственный токарный станок, 2020 год выпуска.",
            "category_id": child["id"],
            "type": "sale",
            "region": "dnr",
            "city": "Донецк",
            "price": 250000,
            "attributes": {"condition": "used", "year": 2020},
            "organization_id": org["id"],
            "contact_phone": "+79991110001",
        },
    )
    assert listing_response.status_code == 201, listing_response.text
    listing = listing_response.json()
    assert listing["status"] == "draft"
    assert listing["contacts_available"] is True

    # Drafts are not visible in the public search.
    public_search = await client.get("/api/v1/listings")
    assert public_search.status_code == 200
    assert public_search.json()["total"] == 0

    # 5. Submit for moderation.
    submitted = await client.post(
        f"/api/v1/listings/{listing['id']}/submit", headers=user_headers
    )
    assert submitted.status_code == 200, submitted.text
    assert submitted.json()["status"] == "pending"

    # 6. Admin logs in with TOTP and approves the listing.
    mfa_tokens = await admin_tokens(client)
    mfa_headers = auth_headers(mfa_tokens)

    queue = await client.get(
        "/api/v1/admin/listings", headers=mfa_headers, params={"status": "pending"}
    )
    assert queue.status_code == 200, queue.text
    assert any(item["id"] == listing["id"] for item in queue.json()["items"])

    approved = await client.post(
        f"/api/v1/admin/listings/{listing['id']}/approve", headers=mfa_headers
    )
    assert approved.status_code == 200, approved.text
    assert approved.json()["status"] == "active"
    assert approved.json()["expires_at"] is not None

    # 7. Public search finds the listing, but hides contacts.
    public_search = await client.get(
        "/api/v1/listings", params={"q": "токарный", "region": "dnr"}
    )
    assert public_search.status_code == 200, public_search.text
    payload = public_search.json()
    assert payload["total"] == 1
    public_item = payload["items"][0]
    assert public_item["contacts"] is None
    assert public_item["contacts_available"] is False

    # Attribute filters work for inherited attributes.
    attr_search = await client.get(
        "/api/v1/listings",
        params={"attr.condition": "used", "attr.year.min": 2019, "attr.year.max": 2021},
    )
    assert attr_search.status_code == 200
    assert attr_search.json()["total"] == 1

    # 8. The same card shows contacts to an authenticated user.
    authorized_card = await client.get(
        f"/api/v1/listings/{listing['id']}", headers=user_headers
    )
    assert authorized_card.status_code == 200
    card = authorized_card.json()
    assert card["contacts_available"] is True
    assert card["contacts"]["phone"] == "+79991110001"
    assert card["views_count"] >= 1

    # 9. Refresh-token rotation and reuse detection.
    first_refresh = user_tokens["refresh_token"]
    rotated = await client.post(
        "/api/v1/auth/refresh", json={"refresh_token": first_refresh}
    )
    assert rotated.status_code == 200, rotated.text
    assert rotated.json()["refresh_token"] != first_refresh

    reuse = await client.post(
        "/api/v1/auth/refresh", json={"refresh_token": first_refresh}
    )
    assert reuse.status_code == 401
    assert reuse.json()["error"]["code"] == "refresh_reuse_detected"

    # The whole family is revoked, including the token issued by rotation.
    revoked = await client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": rotated.json()["refresh_token"]},
    )
    assert revoked.status_code == 401


@pytest.mark.asyncio
async def test_admin_api_requires_totp(client):
    tokens = await login(client, 999001, "+79990000001", "Admin")
    headers = auth_headers(tokens)
    assert tokens["requires_totp"] is True

    response = await client.get("/api/v1/admin/stats", headers=headers)
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "mfa_required"


@pytest.mark.asyncio
async def test_listing_limit_for_private_person(client, monkeypatch):
    from app.core.config import settings

    monkeypatch.setattr(settings, "private_active_listing_limit", 1)

    user_tokens = await login(client, 111002, "+79991110002", "Пётр")
    headers = auth_headers(user_tokens)

    catalog = await client.get("/api/v1/catalog/categories")
    equipment = next(
        item for item in catalog.json() if item["slug"] == "oborudovanie"
    )

    ids = []
    for index in range(2):
        created = await client.post(
            "/api/v1/listings",
            headers=headers,
            json={
                "title": f"Объявление номер {index}",
                "description": "Описание объявления для проверки лимита публикаций.",
                "category_id": equipment["id"],
                "type": "sale",
                "region": "lnr",
                "attributes": {"condition": "new"},
            },
        )
        assert created.status_code == 201, created.text
        ids.append(created.json()["id"])

    first = await client.post(f"/api/v1/listings/{ids[0]}/submit", headers=headers)
    assert first.status_code == 200, first.text

    second = await client.post(f"/api/v1/listings/{ids[1]}/submit", headers=headers)
    assert second.status_code == 403
    assert second.json()["error"]["code"] == "listing_limit_reached"
