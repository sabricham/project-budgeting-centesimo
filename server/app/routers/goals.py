"""Obiettivi di risparmio (§2.9).

L'obiettivo è una "etichetta" sopra un conto `savings_goal`: nessuna contabilità
parallela, `current_amount` è il saldo del conto collegato. Un conto può essere legato a
un solo obiettivo alla volta.
"""

from __future__ import annotations

import datetime as dt
from decimal import Decimal

from fastapi import APIRouter, status
from sqlalchemy import select

from app import schemas
from app.auth.deps import CurrentUser, DbSession
from app.enums import AccountType
from app.errors import Conflict, Invalid
from app.models import Account, Goal
from app.routers.common import apply_updates, check_concurrency, get_owned
from app.services.balances import ZERO, cash_balances, q2

router = APIRouter(prefix="/goals", tags=["goals"])


def _months_between(today: dt.date, target: dt.date) -> int:
    months = (target.year - today.year) * 12 + (target.month - today.month)
    if target.day > today.day:
        months += 1
    return max(months, 0)


async def _serialize(session: DbSession, user_id: int, goals: list[Goal]) -> list[dict]:
    if not goals:
        return []
    account_ids = [g.linked_account_id for g in goals]
    balances = await cash_balances(session, user_id, account_ids=account_ids)
    names = {
        r.id: r.name
        for r in await session.execute(
            select(Account.id, Account.name).where(Account.id.in_(account_ids))
        )
    }

    today = dt.date.today()
    out = []
    for goal in goals:
        current = q2(balances.get(goal.linked_account_id, ZERO))
        target = q2(goal.target_amount)
        missing = target - current

        months_remaining = None
        monthly_required = None
        if goal.target_date:
            months_remaining = _months_between(today, goal.target_date)
            if missing > 0:
                # con scadenza già passata (o questo mese) serve tutto subito
                monthly_required = q2(missing / Decimal(months_remaining or 1))
            else:
                monthly_required = ZERO

        out.append(
            {
                "id": goal.id,
                "name": goal.name,
                "target_amount": target,
                "target_date": goal.target_date,
                "linked_account_id": goal.linked_account_id,
                "linked_account_name": names.get(goal.linked_account_id),
                "icon": goal.icon,
                "color": goal.color,
                "current_amount": current,
                "progress": float(current / target) if target else 0.0,
                "monthly_required": monthly_required,
                "months_remaining": months_remaining,
                "created_at": goal.created_at,
                "updated_at": goal.updated_at,
            }
        )
    return out


@router.get("", response_model=list[schemas.GoalOut])
async def list_goals(user: CurrentUser, session: DbSession) -> list[dict]:
    goals = list(
        await session.scalars(select(Goal).where(Goal.user_id == user.id).order_by(Goal.name))
    )
    return await _serialize(session, user.id, goals)


@router.post("", response_model=schemas.GoalOut, status_code=status.HTTP_201_CREATED)
async def create_goal(payload: schemas.GoalCreate, user: CurrentUser, session: DbSession) -> dict:
    account = await get_owned(session, Account, payload.linked_account_id, user.id, label="Conto")
    if account.type != AccountType.savings_goal.value:
        raise Invalid(
            "Un obiettivo va collegato a un conto di tipo `savings_goal`: crea il conto "
            "dedicato e spostaci i soldi con un trasferimento (§2.3)"
        )
    existing = await session.scalar(select(Goal).where(Goal.linked_account_id == account.id))
    if existing is not None:
        raise Conflict(
            f"Il conto '{account.name}' è già collegato all'obiettivo '{existing.name}'",
            code="account_already_linked",
        )

    goal = Goal(user_id=user.id, **payload.model_dump())
    session.add(goal)
    await session.commit()
    await session.refresh(goal)
    return (await _serialize(session, user.id, [goal]))[0]


@router.get("/{goal_id}", response_model=schemas.GoalOut)
async def get_goal(goal_id: int, user: CurrentUser, session: DbSession) -> dict:
    goal = await get_owned(session, Goal, goal_id, user.id, label="Obiettivo")
    return (await _serialize(session, user.id, [goal]))[0]


@router.patch("/{goal_id}", response_model=schemas.GoalOut)
async def update_goal(
    goal_id: int, payload: schemas.GoalUpdate, user: CurrentUser, session: DbSession
) -> dict:
    goal = await get_owned(session, Goal, goal_id, user.id, label="Obiettivo")
    check_concurrency(goal, payload.expected_updated_at)
    # il conto collegato non si cambia: si elimina l'obiettivo e se ne crea un altro
    apply_updates(goal, payload)
    await session.commit()
    await session.refresh(goal)
    return (await _serialize(session, user.id, [goal]))[0]


@router.delete("/{goal_id}", status_code=status.HTTP_204_NO_CONTENT, response_model=None)
async def delete_goal(goal_id: int, user: CurrentUser, session: DbSession) -> None:
    goal = await get_owned(session, Goal, goal_id, user.id, label="Obiettivo")
    await session.delete(goal)
    await session.commit()
