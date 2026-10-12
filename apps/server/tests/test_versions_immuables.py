"""Règle 2 : une version publiée est immuable — aucune mise à jour possible par l'ORM."""

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.models.capability import Capability, CapabilityVersion, ImmutableVersionError


async def _capacite(db):
    cap = Capability(
        name="imm",
        kind="prompt",
        title="Immuable",
        description="d",
        input_schema={"type": "object"},
        definition={"prompt": "p"},
        dependencies=[],
        grounding="input",
        annotations={"readOnlyHint": True},
        examples=[],
        visibility="private",
        owner_sub="alice",
    )
    db.add(cap)
    await db.flush()
    version = CapabilityVersion(
        capability_id=cap.id,
        version=1,
        maturity="alpha",
        hash="a" * 64,
        title="Immuable",
        description="d",
        definition={"prompt": "p"},
        input_schema={"type": "object"},
        dependencies=[],
        annotations={"readOnlyHint": True},
        grounding="input",
        examples=[],
        published_by="alice",
        published_from="dev",
        guard_verdict="favorable",
        guard_ruleset_version="abc",
        guard_details=[],
    )
    db.add(version)
    await db.commit()
    return cap, version


async def test_update_orm_refuse(db_session):
    _, version = await _capacite(db_session)
    version.definition = {"prompt": "modifié"}
    with pytest.raises(ImmutableVersionError):
        await db_session.commit()
    await db_session.rollback()
    relue = (await db_session.execute(select(CapabilityVersion))).scalar_one()
    assert relue.definition == {"prompt": "p"}


async def test_unicite_capacite_version(db_session):
    cap, _ = await _capacite(db_session)
    db_session.add(
        CapabilityVersion(
            capability_id=cap.id,
            version=1,
            maturity="alpha",
            hash="b" * 64,
            title="t",
            description="d",
            definition={},
            input_schema={},
            dependencies=[],
            annotations={},
            grounding="input",
            examples=[],
            published_by="x",
            published_from="y",
            guard_verdict="favorable",
            guard_ruleset_version="abc",
            guard_details=[],
        )
    )
    with pytest.raises(IntegrityError):
        await db_session.commit()
    await db_session.rollback()
