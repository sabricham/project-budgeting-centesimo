"""Configurazione dei widget della home (§2.11).

Il backend memorizza solo posizione e `config` (JSONB libero): non sa cosa disegna il
client. Aggiungere un tipo di widget che riusa le metriche esistenti non richiede
nessuna modifica qui.
"""

from __future__ import annotations

from fastapi import APIRouter, status
from sqlalchemy import select

from app import schemas
from app.auth.deps import CurrentUser, DbSession
from app.models import DashboardWidget
from app.routers.common import apply_updates, check_concurrency, get_owned

router = APIRouter(prefix="/dashboard/widgets", tags=["dashboard"])


@router.get("", response_model=list[schemas.WidgetOut])
async def list_widgets(user: CurrentUser, session: DbSession) -> list[DashboardWidget]:
    return list(
        await session.scalars(
            select(DashboardWidget)
            .where(DashboardWidget.user_id == user.id)
            .order_by(DashboardWidget.position_y, DashboardWidget.position_x, DashboardWidget.id)
        )
    )


@router.post("", response_model=schemas.WidgetOut, status_code=status.HTTP_201_CREATED)
async def create_widget(
    payload: schemas.WidgetCreate, user: CurrentUser, session: DbSession
) -> DashboardWidget:
    widget = DashboardWidget(user_id=user.id, **payload.model_dump())
    session.add(widget)
    await session.commit()
    await session.refresh(widget)
    return widget


@router.patch("/{widget_id}", response_model=schemas.WidgetOut)
async def update_widget(
    widget_id: int, payload: schemas.WidgetUpdate, user: CurrentUser, session: DbSession
) -> DashboardWidget:
    widget = await get_owned(session, DashboardWidget, widget_id, user.id, label="Widget")
    check_concurrency(widget, payload.expected_updated_at)
    apply_updates(widget, payload)
    await session.commit()
    await session.refresh(widget)
    return widget


@router.delete("/{widget_id}", status_code=status.HTTP_204_NO_CONTENT, response_model=None)
async def delete_widget(widget_id: int, user: CurrentUser, session: DbSession) -> None:
    widget = await get_owned(session, DashboardWidget, widget_id, user.id, label="Widget")
    await session.delete(widget)
    await session.commit()
