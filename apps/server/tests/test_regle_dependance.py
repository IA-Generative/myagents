"""Règle 3 de l'ADR : une capacité ne dépend que de capacités publiées, visibles, de maturité ≥,
dans une version épinglée. Fonction pure `verifier` + profondeur d'exécution."""

from types import SimpleNamespace

from app.services.dependances import ORDRE_MATURITE, verifier


def _cap(
    status="published",
    visibility="ministry",
    owner="autre",
    community_path=None,
    current_version=1,
):
    return SimpleNamespace(
        status=status,
        visibility=visibility,
        owner_sub=owner,
        community_path=community_path,
        current_version=current_version,
        name="dep",
    )


def _version(maturity="beta"):
    return SimpleNamespace(maturity=maturity, version=1)


class _User(SimpleNamespace):
    pass


ALICE = _User(user_id="alice", groups=["/g/G1"], is_admin=False)


def test_ordre_des_maturites():
    assert ORDRE_MATURITE["alpha"] < ORDRE_MATURITE["beta"] < ORDRE_MATURITE["general"]


def test_beta_ne_depend_pas_d_alpha():
    """C-A4."""
    raison = verifier(_cap(), _version("alpha"), maturite_dependante="beta", user=ALICE)
    assert raison and "maturité" in raison


def test_general_depend_de_general_seulement():
    assert verifier(_cap(), _version("beta"), maturite_dependante="general", user=ALICE)
    assert (
        verifier(_cap(), _version("general"), maturite_dependante="general", user=ALICE)
        is None
    )


def test_alpha_peut_dependre_de_tout():
    assert (
        verifier(_cap(), _version("alpha"), maturite_dependante="alpha", user=ALICE)
        is None
    )


def test_non_publiee_refusee():
    assert "publiée" in verifier(
        _cap(status="draft", current_version=None, owner="alice"),
        _version(),
        "alpha",
        ALICE,
    )


def test_version_epinglee_inexistante_refusee():
    assert "version" in verifier(_cap(), None, "alpha", ALICE)


def test_capacite_introuvable_ou_invisible():
    assert "introuvable" in verifier(None, None, "alpha", ALICE)
    privee = _cap(visibility="private", owner="bob")
    assert "introuvable" in verifier(privee, _version(), "alpha", ALICE)


def test_communaute_visible_selon_le_groupe():
    g1 = _cap(visibility="community", community_path="/g/G1")
    assert verifier(g1, _version("beta"), "alpha", ALICE) is None
    g2 = _cap(visibility="community", community_path="/g/G2")
    assert "introuvable" in verifier(g2, _version("beta"), "alpha", ALICE)
