import uuid

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from app.core.deps import CurrentUser, DbSession
from app.models.strategy import Strategy, StrategyVersion
from app.quant.schema import validate_definition
from app.schemas.strategy import (
    StrategyCreate,
    StrategyOut,
    StrategyUpdate,
    StrategyVersionOut,
    VersionCreate,
)
from app.templates import get_explore, get_templates

router = APIRouter(tags=["strategies"])


@router.get("/strategies/explore")
async def explore_catalog(category: str | None = None):
    """Prebuilt algo gallery with category facets (Stratzy-style explore)."""
    data = get_explore()
    if category and category != "all":
        data = {
            **data,
            "algos": [a for a in data["algos"] if a["category"] == category],
        }
        data["total"] = len(data["algos"])
    return data


@router.get("/strategies/templates")
async def list_templates():
    return get_templates()


def _ensure_valid_definition(definition) -> None:
    """Definitions are validated at the door so engines can trust stored data."""
    if definition is None:
        return
    errors, _ = validate_definition(definition)
    if errors:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={"message": "Invalid strategy definition", "errors": errors[:10]},
        )


async def _get_owned_strategy(db, strategy_id: uuid.UUID, user) -> Strategy:
    result = await db.execute(
        select(Strategy).where(Strategy.id == strategy_id, Strategy.user_id == user.id)
    )
    strategy = result.scalar_one_or_none()
    if strategy is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Strategy not found")
    return strategy


@router.get("/strategies", response_model=list[StrategyOut])
async def list_strategies(db: DbSession, current_user: CurrentUser) -> list[Strategy]:
    result = await db.execute(
        select(Strategy).where(Strategy.user_id == current_user.id).order_by(Strategy.updated_at.desc())
    )
    return list(result.scalars().all())


@router.post("/strategies", response_model=StrategyOut, status_code=status.HTTP_201_CREATED)
async def create_strategy(payload: StrategyCreate, db: DbSession, current_user: CurrentUser) -> Strategy:
    _ensure_valid_definition(payload.definition)
    strategy = Strategy(**payload.model_dump(), user_id=current_user.id)
    db.add(strategy)
    await db.flush()
    version = StrategyVersion(
        strategy_id=strategy.id,
        version_number=1,
        definition=payload.definition,
        changelog="Initial version",
    )
    db.add(version)
    await db.commit()
    await db.refresh(strategy)
    return strategy


@router.get("/strategies/{strategy_id}", response_model=StrategyOut)
async def get_strategy(strategy_id: uuid.UUID, db: DbSession, current_user: CurrentUser) -> Strategy:
    return await _get_owned_strategy(db, strategy_id, current_user)


@router.api_route(
    "/strategies/{strategy_id}",
    response_model=StrategyOut,
    methods=["PUT", "PATCH"],
)
async def update_strategy(
    strategy_id: uuid.UUID,
    payload: StrategyUpdate,
    db: DbSession,
    current_user: CurrentUser,
) -> Strategy:
    strategy = await _get_owned_strategy(db, strategy_id, current_user)
    updates = payload.model_dump(exclude_unset=True)
    if updates.get("definition") is not None:
        _ensure_valid_definition(updates["definition"])
    definition_changed = "definition" in updates and updates["definition"] != strategy.definition
    for field, value in updates.items():
        setattr(strategy, field, value)
    if definition_changed:
        # every definition change creates a new immutable version (spec #55)
        new_version = strategy.current_version + 1
        db.add(
            StrategyVersion(
                strategy_id=strategy.id,
                version_number=new_version,
                definition=strategy.definition,
                changelog="Updated via API",
            )
        )
        strategy.current_version = new_version
    await db.commit()
    await db.refresh(strategy)
    return strategy


@router.delete("/strategies/{strategy_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_strategy(strategy_id: uuid.UUID, db: DbSession, current_user: CurrentUser) -> None:
    strategy = await _get_owned_strategy(db, strategy_id, current_user)
    await db.delete(strategy)
    await db.commit()


@router.post("/strategies/{strategy_id}/clone", response_model=StrategyOut, status_code=status.HTTP_201_CREATED)
async def clone_strategy(strategy_id: uuid.UUID, db: DbSession, current_user: CurrentUser) -> Strategy:
    source = await _get_owned_strategy(db, strategy_id, current_user)
    clone = Strategy(
        user_id=current_user.id,
        name=f"{source.name} (Copy)",
        description=source.description,
        exchange=source.exchange,
        underlying=source.underlying,
        instrument=source.instrument,
        strategy_type=source.strategy_type,
        tags=list(source.tags or []),
        definition=source.definition,
    )
    db.add(clone)
    await db.flush()
    db.add(
        StrategyVersion(
            strategy_id=clone.id,
            version_number=1,
            definition=source.definition,
            changelog=f"Cloned from {source.name} v{source.current_version}",
        )
    )
    await db.commit()
    await db.refresh(clone)
    return clone


@router.get("/strategies/{strategy_id}/versions", response_model=list[StrategyVersionOut])
async def list_versions(
    strategy_id: uuid.UUID, db: DbSession, current_user: CurrentUser
) -> list[StrategyVersion]:
    await _get_owned_strategy(db, strategy_id, current_user)
    result = await db.execute(
        select(StrategyVersion)
        .where(StrategyVersion.strategy_id == strategy_id)
        .order_by(StrategyVersion.version_number.desc())
    )
    return list(result.scalars().all())


@router.post("/strategies/{strategy_id}/versions", response_model=StrategyVersionOut, status_code=status.HTTP_201_CREATED)
async def create_version(
    strategy_id: uuid.UUID,
    payload: VersionCreate,
    db: DbSession,
    current_user: CurrentUser,
) -> StrategyVersion:
    strategy = await _get_owned_strategy(db, strategy_id, current_user)
    version = StrategyVersion(
        strategy_id=strategy.id,
        version_number=strategy.current_version + 1,
        definition=strategy.definition,
        changelog=payload.changelog,
    )
    db.add(version)
    strategy.current_version += 1
    await db.commit()
    await db.refresh(version)
    return version
