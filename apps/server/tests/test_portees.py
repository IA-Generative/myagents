"""Table portée → opération (ADR §4.7, §10.1 point 6) et normalisation du claim `scope`."""

import pytest

from app.core.contrat import ContratError
from app.core.portees import (
    PORTEE,
    REFUSEES,
    Operation,
    exiger,
    normaliser_portees,
    portee_pour_appel,
)


def test_table_complete():
    assert PORTEE[Operation.LISTER] == "mesagents:read"
    assert PORTEE[Operation.APPELER_LECTURE] == "mesagents:read"
    assert PORTEE[Operation.APPELER_ACTION] == "mesagents:act"
    assert PORTEE[Operation.REDIGER] == "mesagents:author"
    assert PORTEE[Operation.REVOIR] == "mesagents:review"
    assert PORTEE[Operation.DELEGUER] == "mesagents:delegate"
    assert REFUSEES == frozenset({"mesagents:delegate"})


def test_normalisation_du_claim_scope():
    portees = normaliser_portees("openid profile mesagents:read  mesagents:author")
    assert portees == frozenset(
        {"openid", "profile", "mesagents:read", "mesagents:author"}
    )
    assert normaliser_portees("") == frozenset()


def test_alias_de_nommage_normalises():
    """Repli si Keycloak refuse « : » : mesagents-read et mesagents.read valent mesagents:read."""
    portees = normaliser_portees("mesagents-read mesagents.act")
    assert {"mesagents:read", "mesagents:act"} <= portees


def test_portee_pour_appel_selon_readonly():
    assert portee_pour_appel(read_only=True) == "mesagents:read"
    assert portee_pour_appel(read_only=False) == "mesagents:act"


def test_exiger_leve_scope_missing_nommant_la_portee():
    with pytest.raises(ContratError) as exc:
        exiger(frozenset({"mesagents:read"}), Operation.APPELER_ACTION)
    assert exc.value.status_code == 403
    assert exc.value.code == "scope_missing"
    assert "mesagents:act" in exc.value.message


def test_exiger_passe_quand_la_portee_est_la():
    exiger(frozenset({"mesagents:read", "mesagents:act"}), Operation.APPELER_ACTION)


def test_delegate_toujours_refusee():
    with pytest.raises(ContratError) as exc:
        exiger(frozenset({"mesagents:delegate", "mesagents:read"}), Operation.LISTER)
    assert exc.value.status_code == 403
    assert exc.value.code == "forbidden"
