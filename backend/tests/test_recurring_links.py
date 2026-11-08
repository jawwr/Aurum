"""Transactions <-> recurring payments link (many transactions to one
payment): linking on create/update/bulk, posting a payment either as a new
transaction or from an existing one, and — the main rule — a payment counts
as paid only while a transaction linked to it exists (deleting or unlinking
the last one makes it unpaid again). Transaction and payment types are
deliberately NOT required to match.
"""
from datetime import date

import pytest
from httpx import AsyncClient

from tests.helpers import txn_payload

TODAY = date.today().isoformat()
OLD = "2020-01-15"


async def _recurring(
    client: AsyncClient, account_id: int, description: str = "Rent", type_: str = "expense", frequency: str = "monthly"
) -> dict:
    resp = await client.post(
        "/recurring",
        json={
            "account_id": account_id,
            "type": type_,
            "amount": "100",
            "description": description,
            "frequency": frequency,
            "anchor_date": TODAY,
        },
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


async def _state(client: AsyncClient, recurring_id: int) -> dict:
    items = (await client.get("/recurring")).json()
    return next(item for item in items if item["id"] == recurring_id)


async def _transaction(client: AsyncClient, account_id: int, **overrides) -> dict:
    resp = await client.post("/transactions", json=txn_payload(account_id, **overrides))
    assert resp.status_code == 201, resp.text
    return resp.json()


async def _all_transactions(client: AsyncClient) -> list[dict]:
    return (await client.get("/transactions", params={"page_size": 200})).json()["items"]


# --- linking on create -------------------------------------------------------


async def test_create_transaction_without_recurring_has_no_link(client: AsyncClient, account_id):
    recurring = await _recurring(client, account_id)

    transaction = await _transaction(client, account_id, date=TODAY)

    assert transaction["recurring_transaction_id"] is None
    assert (await _state(client, recurring["id"]))["is_paid_current_period"] is False


async def test_create_transaction_linked_to_recurring_marks_it_paid(client: AsyncClient, account_id):
    recurring = await _recurring(client, account_id)

    transaction = await _transaction(client, account_id, date=TODAY, recurring_transaction_id=recurring["id"])

    assert transaction["recurring_transaction_id"] == recurring["id"]
    state = await _state(client, recurring["id"])
    assert state["last_posted_date"] == TODAY
    assert state["is_paid_current_period"] is True


async def test_create_transaction_with_unknown_recurring_is_rejected(client: AsyncClient, account_id):
    resp = await client.post("/transactions", json=txn_payload(account_id, recurring_transaction_id=999999))

    assert resp.status_code == 400
    assert (await client.get("/transactions")).json()["total"] == 0


async def test_many_transactions_can_share_one_recurring(client: AsyncClient, account_id):
    recurring = await _recurring(client, account_id)

    first = await _transaction(client, account_id, date=OLD, recurring_transaction_id=recurring["id"])
    second = await _transaction(client, account_id, date=TODAY, recurring_transaction_id=recurring["id"])

    linked = {t["id"] for t in await _all_transactions(client) if t["recurring_transaction_id"] == recurring["id"]}
    assert linked == {first["id"], second["id"]}


async def test_linking_an_older_transaction_never_moves_the_schedule_back(client: AsyncClient, account_id):
    recurring = await _recurring(client, account_id)
    await _transaction(client, account_id, date=TODAY, recurring_transaction_id=recurring["id"])

    await _transaction(client, account_id, date=OLD, recurring_transaction_id=recurring["id"])

    assert (await _state(client, recurring["id"]))["last_posted_date"] == TODAY


async def test_transaction_type_does_not_have_to_match_recurring_type(client: AsyncClient, account_id):
    income_recurring = await _recurring(client, account_id, description="Salary", type_="income")
    savings = (await client.post("/accounts", json={"name": "Savings", "type": "savings", "currency": "RUB"})).json()

    expense = await client.post(
        "/transactions", json=txn_payload(account_id, date=TODAY, recurring_transaction_id=income_recurring["id"])
    )
    transfer = await client.post(
        "/transactions",
        json=txn_payload(
            account_id,
            type="transfer",
            transfer_account_id=savings["id"],
            date=TODAY,
            recurring_transaction_id=income_recurring["id"],
        ),
    )

    assert expense.status_code == 201
    assert transfer.status_code == 201
    assert transfer.json()["recurring_transaction_id"] == income_recurring["id"]


async def test_bulk_create_links_and_marks_recurring_paid(client: AsyncClient, account_id):
    recurring = await _recurring(client, account_id)

    resp = await client.post(
        "/transactions/bulk",
        json={
            "items": [
                txn_payload(account_id, date=TODAY, recurring_transaction_id=recurring["id"]),
                txn_payload(account_id, date=OLD),
            ]
        },
    )

    assert resp.status_code == 201
    assert (await _state(client, recurring["id"]))["is_paid_current_period"] is True
    linked = [t for t in await _all_transactions(client) if t["recurring_transaction_id"] == recurring["id"]]
    assert len(linked) == 1


async def test_bulk_create_with_unknown_recurring_creates_nothing(client: AsyncClient, account_id):
    resp = await client.post(
        "/transactions/bulk",
        json={
            "items": [
                txn_payload(account_id, description="fine row"),
                txn_payload(account_id, description="bad row", recurring_transaction_id=999999),
            ]
        },
    )

    assert resp.status_code == 400
    assert (await client.get("/transactions")).json()["total"] == 0


# --- changing the link with PATCH --------------------------------------------


async def test_update_can_link_an_existing_transaction(client: AsyncClient, account_id):
    recurring = await _recurring(client, account_id)
    transaction = await _transaction(client, account_id, date=TODAY)

    resp = await client.patch(f"/transactions/{transaction['id']}", json={"recurring_transaction_id": recurring["id"]})

    assert resp.status_code == 200
    assert resp.json()["recurring_transaction_id"] == recurring["id"]
    state = await _state(client, recurring["id"])
    assert state["last_posted_date"] == TODAY
    assert state["is_paid_current_period"] is True


async def test_update_without_the_field_keeps_the_link(client: AsyncClient, account_id):
    recurring = await _recurring(client, account_id)
    transaction = await _transaction(client, account_id, date=TODAY, recurring_transaction_id=recurring["id"])

    resp = await client.patch(f"/transactions/{transaction['id']}", json={"description": "renamed"})

    assert resp.status_code == 200
    assert resp.json()["recurring_transaction_id"] == recurring["id"]
    assert (await _state(client, recurring["id"]))["is_paid_current_period"] is True


async def test_update_with_null_unlinks_and_makes_recurring_unpaid(client: AsyncClient, account_id):
    recurring = await _recurring(client, account_id)
    transaction = await _transaction(client, account_id, date=TODAY, recurring_transaction_id=recurring["id"])

    resp = await client.patch(f"/transactions/{transaction['id']}", json={"recurring_transaction_id": None})

    assert resp.status_code == 200
    assert resp.json()["recurring_transaction_id"] is None
    state = await _state(client, recurring["id"])
    assert state["last_posted_date"] is None
    assert state["is_paid_current_period"] is False


async def test_unlinking_one_of_two_keeps_the_recurring_paid(client: AsyncClient, account_id):
    recurring = await _recurring(client, account_id)
    first = await _transaction(client, account_id, date=TODAY, recurring_transaction_id=recurring["id"])
    await _transaction(client, account_id, date=TODAY, recurring_transaction_id=recurring["id"])

    await client.patch(f"/transactions/{first['id']}", json={"recurring_transaction_id": None})

    assert (await _state(client, recurring["id"]))["is_paid_current_period"] is True


async def test_update_to_unknown_recurring_is_rejected(client: AsyncClient, account_id):
    transaction = await _transaction(client, account_id)

    resp = await client.patch(f"/transactions/{transaction['id']}", json={"recurring_transaction_id": 999999})

    assert resp.status_code == 400


async def test_moving_a_transaction_to_another_recurring_updates_both(client: AsyncClient, account_id):
    rent = await _recurring(client, account_id, description="Rent")
    gym = await _recurring(client, account_id, description="Gym")
    transaction = await _transaction(client, account_id, date=TODAY, recurring_transaction_id=rent["id"])

    resp = await client.patch(f"/transactions/{transaction['id']}", json={"recurring_transaction_id": gym["id"]})

    assert resp.status_code == 200
    assert (await _state(client, rent["id"]))["is_paid_current_period"] is False
    assert (await _state(client, gym["id"]))["is_paid_current_period"] is True


async def test_moving_a_linked_transaction_to_an_old_date_makes_recurring_unpaid(client: AsyncClient, account_id):
    recurring = await _recurring(client, account_id)
    transaction = await _transaction(client, account_id, date=TODAY, recurring_transaction_id=recurring["id"])

    await client.patch(f"/transactions/{transaction['id']}", json={"date": OLD})

    state = await _state(client, recurring["id"])
    assert state["last_posted_date"] == OLD
    assert state["is_paid_current_period"] is False



async def test_patching_an_older_transaction_onto_recurring_does_not_move_the_schedule_back(
    client: AsyncClient, account_id
):
    recurring = await _recurring(client, account_id)
    await _transaction(client, account_id, date=TODAY, recurring_transaction_id=recurring["id"])
    old = await _transaction(client, account_id, date=OLD)

    resp = await client.patch(f"/transactions/{old['id']}", json={"recurring_transaction_id": recurring["id"]})

    assert resp.status_code == 200
    assert (await _state(client, recurring["id"]))["last_posted_date"] == TODAY


# --- deleting a transaction ---------------------------------------------------


async def test_deleting_the_only_linked_transaction_makes_recurring_unpaid(client: AsyncClient, account_id):
    recurring = await _recurring(client, account_id)
    transaction = await _transaction(client, account_id, date=TODAY, recurring_transaction_id=recurring["id"])
    assert (await _state(client, recurring["id"]))["is_paid_current_period"] is True

    resp = await client.delete(f"/transactions/{transaction['id']}")

    assert resp.status_code == 204
    state = await _state(client, recurring["id"])
    assert state["last_posted_date"] is None
    assert state["is_paid_current_period"] is False
    assert state["is_due"] is True


async def test_deleting_one_of_several_linked_transactions_keeps_the_recurring_paid(client: AsyncClient, account_id):
    recurring = await _recurring(client, account_id)
    first = await _transaction(client, account_id, date=TODAY, recurring_transaction_id=recurring["id"])
    await _transaction(client, account_id, date=TODAY, recurring_transaction_id=recurring["id"])

    await client.delete(f"/transactions/{first['id']}")

    assert (await _state(client, recurring["id"]))["is_paid_current_period"] is True


async def test_deleting_the_newest_linked_transaction_falls_back_to_the_previous_one(client: AsyncClient, account_id):
    recurring = await _recurring(client, account_id)
    await _transaction(client, account_id, date=OLD, recurring_transaction_id=recurring["id"])
    newest = await _transaction(client, account_id, date=TODAY, recurring_transaction_id=recurring["id"])

    await client.delete(f"/transactions/{newest['id']}")

    state = await _state(client, recurring["id"])
    assert state["last_posted_date"] == OLD
    assert state["is_paid_current_period"] is False


async def test_deleting_an_unlinked_transaction_does_not_touch_recurring(client: AsyncClient, account_id):
    recurring = await _recurring(client, account_id)
    await _transaction(client, account_id, date=TODAY, recurring_transaction_id=recurring["id"])
    unrelated = await _transaction(client, account_id, date=TODAY)

    await client.delete(f"/transactions/{unrelated['id']}")

    assert (await _state(client, recurring["id"]))["is_paid_current_period"] is True


async def test_recurring_can_be_posted_again_after_its_transaction_is_deleted(client: AsyncClient, account_id):
    recurring = await _recurring(client, account_id)
    posted = await client.post(f"/recurring/{recurring['id']}/post")
    assert posted.status_code == 201
    assert posted.json()["is_paid_current_period"] is True
    transaction = next(t for t in await _all_transactions(client) if t["recurring_transaction_id"] == recurring["id"])

    await client.delete(f"/transactions/{transaction['id']}")
    reposted = await client.post(f"/recurring/{recurring['id']}/post")

    assert reposted.status_code == 201
    assert reposted.json()["is_paid_current_period"] is True


async def test_deleting_a_recurring_keeps_its_transactions_unlinked(client: AsyncClient, account_id):
    recurring = await _recurring(client, account_id)
    transaction = await _transaction(client, account_id, date=TODAY, recurring_transaction_id=recurring["id"])

    resp = await client.delete(f"/recurring/{recurring['id']}")

    assert resp.status_code == 204
    remaining = next(t for t in await _all_transactions(client) if t["id"] == transaction["id"])
    assert remaining["recurring_transaction_id"] is None


@pytest.mark.parametrize("frequency", ["weekly", "monthly", "yearly"])
async def test_deleting_the_linked_transaction_resets_paid_for_every_frequency(
    client: AsyncClient, account_id, frequency
):
    recurring = await _recurring(client, account_id, frequency=frequency)
    transaction = await _transaction(client, account_id, date=TODAY, recurring_transaction_id=recurring["id"])
    assert (await _state(client, recurring["id"]))["is_paid_current_period"] is True

    await client.delete(f"/transactions/{transaction['id']}")

    assert (await _state(client, recurring["id"]))["is_paid_current_period"] is False



# --- posting a payment -----------------------------------------------------


async def test_post_without_transaction_creates_a_linked_transaction(client: AsyncClient, account_id):
    recurring = await _recurring(client, account_id)

    resp = await client.post(f"/recurring/{recurring['id']}/post")

    assert resp.status_code == 201
    assert resp.json()["is_paid_current_period"] is True
    created = [t for t in await _all_transactions(client) if t["description"] == "Rent"]
    assert len(created) == 1
    assert created[0]["recurring_transaction_id"] == recurring["id"]
    assert created[0]["date"] == TODAY


async def test_post_accepts_an_explicit_null_transaction_id(client: AsyncClient, account_id):
    recurring = await _recurring(client, account_id)

    resp = await client.post(f"/recurring/{recurring['id']}/post", json={"transaction_id": None})

    assert resp.status_code == 201
    created = [t for t in await _all_transactions(client) if t["description"] == "Rent"]
    assert len(created) == 1
    assert created[0]["recurring_transaction_id"] == recurring["id"]


async def test_post_with_existing_transaction_links_it_without_creating_another(client: AsyncClient, account_id):
    recurring = await _recurring(client, account_id)
    existing = await _transaction(client, account_id, description="Paid by hand", date=TODAY)

    resp = await client.post(f"/recurring/{recurring['id']}/post", json={"transaction_id": existing["id"]})

    assert resp.status_code == 201
    assert resp.json()["is_paid_current_period"] is True
    transactions = await _all_transactions(client)
    assert len(transactions) == 1
    assert transactions[0]["id"] == existing["id"]
    assert transactions[0]["recurring_transaction_id"] == recurring["id"]


async def test_post_with_an_old_existing_transaction_does_not_mark_the_current_period_paid(
    client: AsyncClient, account_id
):
    recurring = await _recurring(client, account_id)
    old = await _transaction(client, account_id, date=OLD)

    resp = await client.post(f"/recurring/{recurring['id']}/post", json={"transaction_id": old["id"]})

    assert resp.status_code == 201
    assert resp.json()["last_posted_date"] == OLD
    assert resp.json()["is_paid_current_period"] is False


async def test_post_existing_is_rejected_when_already_paid_this_period(client: AsyncClient, account_id):
    recurring = await _recurring(client, account_id)
    await client.post(f"/recurring/{recurring['id']}/post")
    other = await _transaction(client, account_id, description="Another", date=TODAY)

    resp = await client.post(f"/recurring/{recurring['id']}/post", json={"transaction_id": other["id"]})

    assert resp.status_code == 409
    untouched = next(t for t in await _all_transactions(client) if t["id"] == other["id"])
    assert untouched["recurring_transaction_id"] is None


async def test_post_with_unknown_transaction_returns_404_and_changes_nothing(client: AsyncClient, account_id):
    recurring = await _recurring(client, account_id)

    resp = await client.post(f"/recurring/{recurring['id']}/post", json={"transaction_id": 999999})

    assert resp.status_code == 404
    state = await _state(client, recurring["id"])
    assert state["last_posted_date"] is None
    assert state["is_paid_current_period"] is False


async def test_post_for_unknown_recurring_returns_404(client: AsyncClient, account_id):
    transaction = await _transaction(client, account_id)

    resp = await client.post("/recurring/999999/post", json={"transaction_id": transaction["id"]})

    assert resp.status_code == 404


async def test_post_existing_may_have_a_different_type_than_the_recurring(client: AsyncClient, account_id, categories):
    recurring = await _recurring(client, account_id, type_="expense")
    income = await _transaction(
        client, account_id, type="income", category_id=categories["Salary"]["id"], date=TODAY
    )

    resp = await client.post(f"/recurring/{recurring['id']}/post", json={"transaction_id": income["id"]})

    assert resp.status_code == 201
    assert resp.json()["is_paid_current_period"] is True


async def test_post_existing_relinks_it_away_from_its_previous_recurring(client: AsyncClient, account_id):
    rent = await _recurring(client, account_id, description="Rent")
    gym = await _recurring(client, account_id, description="Gym")
    transaction = await _transaction(client, account_id, date=TODAY, recurring_transaction_id=rent["id"])

    resp = await client.post(f"/recurring/{gym['id']}/post", json={"transaction_id": transaction["id"]})

    assert resp.status_code == 201
    assert (await _state(client, rent["id"]))["is_paid_current_period"] is False
    assert (await _state(client, gym["id"]))["is_paid_current_period"] is True
    relinked = next(t for t in await _all_transactions(client) if t["id"] == transaction["id"])
    assert relinked["recurring_transaction_id"] == gym["id"]


# --- backup ----------------------------------------------------------------


async def test_backup_roundtrip_preserves_the_recurring_link(client: AsyncClient, account_id):
    recurring = await _recurring(client, account_id)
    transaction = await _transaction(client, account_id, date=TODAY, recurring_transaction_id=recurring["id"])

    payload = (await client.get("/backup/export")).json()
    exported = next(t for t in payload["transactions"] if t["id"] == transaction["id"])
    assert exported["recurring_transaction_id"] == recurring["id"]

    import_resp = await client.post("/backup/import", json=payload)
    assert import_resp.status_code == 200, import_resp.text

    restored = next(t for t in await _all_transactions(client) if t["id"] == transaction["id"])
    assert restored["recurring_transaction_id"] == recurring["id"]
    assert (await _state(client, recurring["id"]))["is_paid_current_period"] is True


async def test_backup_import_rejects_unknown_recurring_transaction_id(client: AsyncClient, account_id):
    recurring = await _recurring(client, account_id)
    transaction = await _transaction(client, account_id, date=TODAY, recurring_transaction_id=recurring["id"])
    payload = (await client.get("/backup/export")).json()
    for row in payload["transactions"]:
        if row["id"] == transaction["id"]:
            row["recurring_transaction_id"] = 999999

    resp = await client.post("/backup/import", json=payload)

    assert resp.status_code == 400


async def test_backup_without_the_field_still_imports(client: AsyncClient, account_id):
    await _transaction(client, account_id, date=TODAY)
    payload = (await client.get("/backup/export")).json()
    for row in payload["transactions"]:
        row.pop("recurring_transaction_id", None)

    resp = await client.post("/backup/import", json=payload)

    assert resp.status_code == 200, resp.text
    assert all(t["recurring_transaction_id"] is None for t in await _all_transactions(client))

