from __future__ import annotations

import pytest

from tests.conftest import auth_headers, login


async def create_org(client, headers: dict, name: str = "ООО Вектор") -> dict:
    response = await client.post(
        "/api/v1/organizations",
        headers=headers,
        json={
            "type": "legal_entity",
            "name": name,
            "region": "dnr",
            "phone": "+79995550001",
            "description": "Тестовая организация",
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


async def role_by_name(client, headers: dict, org_id: str, name: str) -> dict:
    response = await client.get(
        f"/api/v1/organizations/{org_id}/roles", headers=headers
    )
    assert response.status_code == 200, response.text
    return next(item for item in response.json() if item["name"] == name)


async def invite_and_accept(
    client,
    owner_headers: dict,
    member_headers: dict,
    org_id: str,
    role_id: str,
    *,
    telegram_id: int | None = None,
) -> dict:
    created = await client.post(
        f"/api/v1/organizations/{org_id}/invitations",
        headers=owner_headers,
        json={"role_id": role_id, "telegram_id": telegram_id},
    )
    assert created.status_code == 201, created.text
    invitation = created.json()

    accepted = await client.post(
        f"/api/v1/invitations/{invitation['token']}/accept", headers=member_headers
    )
    assert accepted.status_code == 200, accepted.text
    assert accepted.json()["members_count"] == 2
    return invitation


@pytest.mark.asyncio
async def test_custom_role_invitation_and_member_lifecycle(client):
    owner_tokens = await login(client, 222001, "+79992220001", "Владелец")
    owner_headers = auth_headers(owner_tokens)
    member_tokens = await login(client, 222002, "+79992220002", "Сотрудник")
    member_headers = auth_headers(member_tokens)

    org = await create_org(client, owner_headers)
    org_id = org["id"]
    owner_me = await client.get("/api/v1/users/me", headers=owner_headers)
    assert owner_me.status_code == 200
    owner_user_id = owner_me.json()["id"]

    # Owner creates a custom role.
    created_role = await client.post(
        f"/api/v1/organizations/{org_id}/roles",
        headers=owner_headers,
        json={"name": "Менеджер продаж", "permissions": ["listing.create", "listing.edit"]},
    )
    assert created_role.status_code == 201, created_role.text
    custom_role = created_role.json()
    assert custom_role["is_system"] is False
    assert custom_role["members_count"] == 0

    # Duplicate role name is rejected.
    duplicate = await client.post(
        f"/api/v1/organizations/{org_id}/roles",
        headers=owner_headers,
        json={"name": "Менеджер продаж", "permissions": []},
    )
    assert duplicate.status_code == 409
    assert duplicate.json()["error"]["code"] == "role_exists"

    # Unknown permission code is rejected.
    unknown = await client.post(
        f"/api/v1/organizations/{org_id}/roles",
        headers=owner_headers,
        json={"name": "Странная роль", "permissions": ["nope.nope"]},
    )
    assert unknown.status_code == 422
    assert unknown.json()["error"]["code"] == "unknown_permission"

    # The invited user becomes an active member.
    invitation = await invite_and_accept(
        client,
        owner_headers,
        member_headers,
        org_id,
        custom_role["id"],
        telegram_id=222002,
    )

    members = await client.get(
        f"/api/v1/organizations/{org_id}/members", headers=member_headers
    )
    assert members.status_code == 200, members.text
    assert len(members.json()) == 2
    member_row = next(item for item in members.json() if item["user_id"] != owner_user_id)
    assert member_row["role"]["id"] == custom_role["id"]

    # A member without `org.manage_roles` cannot create roles.
    denied = await client.post(
        f"/api/v1/organizations/{org_id}/roles",
        headers=member_headers,
        json={"name": "Попытка эскалации", "permissions": ["org.manage_roles"]},
    )
    assert denied.status_code == 403
    assert denied.json()["error"]["code"] == "permission_denied"
    assert denied.json()["error"]["details"]["required"] == "org.manage_roles"

    # The role is in use, so it cannot be deleted.
    in_use = await client.delete(
        f"/api/v1/organizations/{org_id}/roles/{custom_role['id']}",
        headers=owner_headers,
    )
    assert in_use.status_code == 409
    assert in_use.json()["error"]["code"] == "role_in_use"
    assert in_use.json()["error"]["details"]["members_count"] == 1

    # Role update works and invalidates cached permissions.
    renamed = await client.patch(
        f"/api/v1/organizations/{org_id}/roles/{custom_role['id']}",
        headers=owner_headers,
        json={"name": "Старший менеджер", "permissions": ["listing.create"]},
    )
    assert renamed.status_code == 200, renamed.text
    assert renamed.json()["name"] == "Старший менеджер"

    # An unused role can be deleted.
    unused_role = await client.post(
        f"/api/v1/organizations/{org_id}/roles",
        headers=owner_headers,
        json={"name": "Временная роль", "permissions": []},
    )
    assert unused_role.status_code == 201, unused_role.text
    deleted = await client.delete(
        f"/api/v1/organizations/{org_id}/roles/{unused_role.json()['id']}",
        headers=owner_headers,
    )
    assert deleted.status_code == 200, deleted.text

    # Owner reassigns the member to another role.
    viewer_role = await role_by_name(client, owner_headers, org_id, "Только просмотр")
    reassigned = await client.patch(
        f"/api/v1/organizations/{org_id}/members/{member_row['user_id']}",
        headers=owner_headers,
        json={"role_id": viewer_role["id"]},
    )
    assert reassigned.status_code == 200, reassigned.text
    assert reassigned.json()["role"]["id"] == viewer_role["id"]

    # The invitation cannot be accepted twice.
    again = await client.post(
        f"/api/v1/invitations/{invitation['token']}/accept", headers=member_headers
    )
    assert again.status_code == 410
    assert again.json()["error"]["code"] == "invitation_not_pending"

    # Removing the member revokes access immediately.
    removed = await client.delete(
        f"/api/v1/organizations/{org_id}/members/{member_row['user_id']}",
        headers=owner_headers,
    )
    assert removed.status_code == 200, removed.text

    denied_after_removal = await client.get(
        f"/api/v1/organizations/{org_id}", headers=member_headers
    )
    assert denied_after_removal.status_code == 403
    assert denied_after_removal.json()["error"]["code"] == "not_org_member"


@pytest.mark.asyncio
async def test_invitation_owner_mismatch_and_revocation(client):
    owner_tokens = await login(client, 223001, "+79992230001", "Владелец")
    owner_headers = auth_headers(owner_tokens)
    invited_tokens = await login(client, 223002, "+79992230002", "Приглашённый")
    invited_headers = auth_headers(invited_tokens)
    stranger_tokens = await login(client, 223003, "+79992230003", "Посторонний")
    stranger_headers = auth_headers(stranger_tokens)

    org = await create_org(client, owner_headers, name="ООО Приглашения")
    org_id = org["id"]
    viewer_role = await role_by_name(client, owner_headers, org_id, "Только просмотр")

    created = await client.post(
        f"/api/v1/organizations/{org_id}/invitations",
        headers=owner_headers,
        json={"role_id": viewer_role["id"], "telegram_id": 223002},
    )
    assert created.status_code == 201, created.text
    invitation = created.json()
    assert invitation["invite_url"].startswith("https://t.me/")

    mismatch = await client.post(
        f"/api/v1/invitations/{invitation['token']}/accept", headers=stranger_headers
    )
    assert mismatch.status_code == 403
    assert mismatch.json()["error"]["code"] == "invitation_owner_mismatch"

    listed = await client.get(
        f"/api/v1/organizations/{org_id}/invitations", headers=owner_headers
    )
    assert listed.status_code == 200, listed.text
    assert len(listed.json()) == 1
    assert listed.json()[0]["status"] == "pending"

    revoked = await client.delete(
        f"/api/v1/organizations/{org_id}/invitations/{invitation['id']}",
        headers=owner_headers,
    )
    assert revoked.status_code == 200, revoked.text

    accepted = await client.post(
        f"/api/v1/invitations/{invitation['token']}/accept", headers=invited_headers
    )
    assert accepted.status_code == 410
    assert accepted.json()["error"]["code"] == "invitation_not_pending"


@pytest.mark.asyncio
async def test_permission_escalation_and_owner_transfer(client):
    owner_tokens = await login(client, 224001, "+79992240001", "Владелец")
    owner_headers = auth_headers(owner_tokens)
    hr_tokens = await login(client, 224002, "+79992240002", "Кадровик")
    hr_headers = auth_headers(hr_tokens)

    org = await create_org(client, owner_headers, name="ООО Кадры")
    org_id = org["id"]

    hr_role = await client.post(
        f"/api/v1/organizations/{org_id}/roles",
        headers=owner_headers,
        json={
            "name": "Кадровик",
            "permissions": ["org.manage_roles", "org.manage_members"],
        },
    )
    assert hr_role.status_code == 201, hr_role.text

    await invite_and_accept(
        client, owner_headers, hr_headers, org_id, hr_role.json()["id"]
    )

    # A member cannot grant a permission they do not hold.
    escalation = await client.post(
        f"/api/v1/organizations/{org_id}/roles",
        headers=hr_headers,
        json={"name": "Биллинг", "permissions": ["billing.manage"]},
    )
    assert escalation.status_code == 403
    assert escalation.json()["error"]["code"] == "permission_escalation"

    # The owner's role is immutable through the members endpoint.
    owner_member = next(
        item
        for item in (
            await client.get(
                f"/api/v1/organizations/{org_id}/members", headers=owner_headers
            )
        ).json()
        if item["is_owner"]
    )
    owner_role_change = await client.patch(
        f"/api/v1/organizations/{org_id}/members/{owner_member['user_id']}",
        headers=hr_headers,
        json={"role_id": hr_role.json()["id"]},
    )
    assert owner_role_change.status_code == 409
    assert owner_role_change.json()["error"]["code"] == "owner_role_immutable"

    # Only the owner may transfer ownership.
    hr_me = await client.get("/api/v1/users/me", headers=hr_headers)
    assert hr_me.status_code == 200
    hr_user_id = hr_me.json()["id"]

    not_owner = await client.post(
        f"/api/v1/organizations/{org_id}/transfer-owner",
        headers=hr_headers,
        json={"user_id": owner_member["user_id"]},
    )
    assert not_owner.status_code == 403
    assert not_owner.json()["error"]["code"] == "owner_required"

    transferred = await client.post(
        f"/api/v1/organizations/{org_id}/transfer-owner",
        headers=owner_headers,
        json={"user_id": hr_user_id},
    )
    assert transferred.status_code == 200, transferred.text

    # The new owner cannot remove themselves through the members endpoint.
    self_remove = await client.delete(
        f"/api/v1/organizations/{org_id}/members/{hr_user_id}", headers=hr_headers
    )
    assert self_remove.status_code == 409
    assert self_remove.json()["error"]["code"] == "owner_cannot_be_removed"

    # Ownership is transferred back, then the former employee is removed.
    back = await client.post(
        f"/api/v1/organizations/{org_id}/transfer-owner",
        headers=hr_headers,
        json={"user_id": owner_member["user_id"]},
    )
    assert back.status_code == 200, back.text

    removed = await client.delete(
        f"/api/v1/organizations/{org_id}/members/{hr_user_id}", headers=owner_headers
    )
    assert removed.status_code == 200, removed.text


@pytest.mark.asyncio
async def test_organization_inn_verification_and_duplicates(client):
    first_tokens = await login(client, 225001, "+79992250001", "Первый")
    first_headers = auth_headers(first_tokens)
    second_tokens = await login(client, 225002, "+79992250002", "Второй")
    second_headers = auth_headers(second_tokens)

    org = await create_org(client, first_headers, name="ООО ИНН")
    org_id = org["id"]

    invalid = await client.post(
        f"/api/v1/organizations/{org_id}/verification/inn",
        headers=first_headers,
        json={"inn": "7707083894"},
    )
    assert invalid.status_code == 422
    assert invalid.json()["error"]["code"] == "invalid_inn"

    verified = await client.post(
        f"/api/v1/organizations/{org_id}/verification/inn",
        headers=first_headers,
        json={"inn": "7707083893"},
    )
    assert verified.status_code == 200, verified.text
    assert verified.json()["inn"] == "7707083893"
    assert verified.json()["verification_level"] == "inn"

    other = await create_org(client, second_headers, name="ООО Дубликат")
    duplicate = await client.post(
        f"/api/v1/organizations/{other['id']}/verification/inn",
        headers=second_headers,
        json={"inn": "7707083893"},
    )
    assert duplicate.status_code == 409
    assert duplicate.json()["error"]["code"] == "inn_taken"
