from __future__ import annotations

import pytest

from tests.conftest import admin_tokens, auth_headers, login


@pytest.mark.asyncio
async def test_admin_catalog_plan_role_and_user_management(client):
    mfa_headers = auth_headers(await admin_tokens(client))

    stats = await client.get("/api/v1/admin/stats", headers=mfa_headers)
    assert stats.status_code == 200, stats.text
    assert stats.json()["users_total"] >= 1

    # --- Catalog: category and attribute CRUD -----------------------------
    root = await client.post(
        "/api/v1/admin/catalog/categories",
        headers=mfa_headers,
        json={"name": "Тестовая витрина", "description": "Временная категория"},
    )
    assert root.status_code == 201, root.text
    root_id = root.json()["id"]
    assert root.json()["slug"]

    child = await client.post(
        "/api/v1/admin/catalog/categories",
        headers=mfa_headers,
        json={"name": "Тестовая подкатегория", "parent_id": root_id},
    )
    assert child.status_code == 201, child.text
    child_id = child.json()["id"]

    attribute = await client.post(
        f"/api/v1/admin/catalog/categories/{child_id}/attributes",
        headers=mfa_headers,
        json={
            "key": "test_power",
            "name": "Мощность",
            "type": "number",
            "unit": "кВт",
            "is_required": True,
        },
    )
    assert attribute.status_code == 201, attribute.text
    attribute_id = attribute.json()["id"]

    updated_attribute = await client.patch(
        f"/api/v1/admin/catalog/attributes/{attribute_id}",
        headers=mfa_headers,
        json={"name": "Мощность, кВт", "sort_order": 5},
    )
    assert updated_attribute.status_code == 200, updated_attribute.text
    assert updated_attribute.json()["name"] == "Мощность, кВт"

    detail = await client.get(
        f"/api/v1/admin/catalog/categories/{child_id}", headers=mfa_headers
    )
    assert detail.status_code == 200, detail.text
    assert any(item["key"] == "test_power" for item in detail.json()["attributes"])

    # A category with children cannot be removed.
    blocked_delete = await client.delete(
        f"/api/v1/admin/catalog/categories/{root_id}", headers=mfa_headers
    )
    assert blocked_delete.status_code == 409
    assert blocked_delete.json()["error"]["code"] == "category_has_children"

    assert (
        await client.delete(
            f"/api/v1/admin/catalog/attributes/{attribute_id}", headers=mfa_headers
        )
    ).status_code == 200
    assert (
        await client.delete(
            f"/api/v1/admin/catalog/categories/{child_id}", headers=mfa_headers
        )
    ).status_code == 200
    assert (
        await client.delete(
            f"/api/v1/admin/catalog/categories/{root_id}", headers=mfa_headers
        )
    ).status_code == 200

    # --- Plans ------------------------------------------------------------
    plan = await client.post(
        "/api/v1/admin/plans",
        headers=mfa_headers,
        json={
            "code": "business_test",
            "name": "Бизнес Тест",
            "max_active_listings": 100,
            "price": 990,
            "features": {"promotion": True},
        },
    )
    assert plan.status_code == 201, plan.text
    plan_id = plan.json()["id"]

    duplicate_plan = await client.post(
        "/api/v1/admin/plans",
        headers=mfa_headers,
        json={
            "code": "business_test",
            "name": "Дубль",
            "max_active_listings": 10,
        },
    )
    assert duplicate_plan.status_code == 409
    assert duplicate_plan.json()["error"]["code"] == "plan_exists"

    updated_plan = await client.patch(
        f"/api/v1/admin/plans/{plan_id}",
        headers=mfa_headers,
        json={"price": 1290, "max_active_listings": 150},
    )
    assert updated_plan.status_code == 200, updated_plan.text
    assert updated_plan.json()["price"] == 1290.0
    assert updated_plan.json()["max_active_listings"] == 150

    plans = await client.get("/api/v1/admin/plans", headers=mfa_headers)
    assert plans.status_code == 200, plans.text
    assert any(item["code"] == "business_test" for item in plans.json())

    assert (
        await client.delete(f"/api/v1/admin/plans/{plan_id}", headers=mfa_headers)
    ).status_code == 200

    # --- Platform roles ---------------------------------------------------
    role = await client.post(
        "/api/v1/admin/platform-roles",
        headers=mfa_headers,
        json={
            "code": "test_moderator",
            "name": "Тестовый модератор",
            "permissions": ["users.view", "listings.moderate"],
        },
    )
    assert role.status_code == 201, role.text
    role_id = role.json()["id"]
    assert role.json()["is_system"] is False

    updated_role = await client.patch(
        f"/api/v1/admin/platform-roles/{role_id}",
        headers=mfa_headers,
        json={"name": "Тестовый модератор 2", "permissions": ["users.view"]},
    )
    assert updated_role.status_code == 200, updated_role.text
    assert updated_role.json()["name"] == "Тестовый модератор 2"

    invalid_role = await client.post(
        "/api/v1/admin/platform-roles",
        headers=mfa_headers,
        json={
            "code": "broken_role",
            "name": "Сломанная роль",
            "permissions": ["does.not_exist"],
        },
    )
    assert invalid_role.status_code == 422
    assert invalid_role.json()["error"]["code"] == "unknown_permission"

    assert (
        await client.delete(
            f"/api/v1/admin/platform-roles/{role_id}", headers=mfa_headers
        )
    ).status_code == 200

    # --- User block / unblock --------------------------------------------
    victim_tokens = await login(client, 441001, "+79994410001", "Нарушитель")
    victim_headers = auth_headers(victim_tokens)
    victim_me = await client.get("/api/v1/users/me", headers=victim_headers)
    assert victim_me.status_code == 200
    victim_id = victim_me.json()["id"]

    blocked = await client.post(
        f"/api/v1/admin/users/{victim_id}/block",
        headers=mfa_headers,
        json={"reason": "Спам в объявлениях"},
    )
    assert blocked.status_code == 200, blocked.text

    # Blocking immediately denies the victim's access token.
    revoked = await client.get("/api/v1/users/me", headers=victim_headers)
    assert revoked.status_code == 403
    assert revoked.json()["error"]["code"] == "account_blocked"

    victim = await client.get(f"/api/v1/admin/users/{victim_id}", headers=mfa_headers)
    assert victim.status_code == 200, victim.text
    assert victim.json()["status"] == "blocked"

    unblocked = await client.post(
        f"/api/v1/admin/users/{victim_id}/unblock", headers=mfa_headers
    )
    assert unblocked.status_code == 200, unblocked.text

    # --- Settings ---------------------------------------------------------
    setting = await client.put(
        "/api/v1/admin/settings/test.feature",
        headers=mfa_headers,
        json={"value": {"enabled": True}, "description": "Тестовая настройка"},
    )
    assert setting.status_code == 200, setting.text
    assert setting.json()["value"] == {"enabled": True}

    settings = await client.get("/api/v1/admin/settings", headers=mfa_headers)
    assert settings.status_code == 200, settings.text
    assert any(item["key"] == "test.feature" for item in settings.json())

    # --- Audit trail ------------------------------------------------------
    audit = await client.get(
        "/api/v1/admin/audit",
        headers=mfa_headers,
        params={"entity_type": "plan"},
    )
    assert audit.status_code == 200, audit.text
    actions = {item["action"] for item in audit.json()["items"]}
    assert {"plan.create", "plan.update", "plan.delete"} <= actions
