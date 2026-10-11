"""Le contrat documenté (docs/contrats/contrat-capacites-mirai.md) est généré depuis le code et
contrôlé : la version committée doit être égale à la génération."""

from pathlib import Path

from app.scripts.exporter_contrat import CHEMIN_DOC, generer


def test_doc_committee_egale_a_la_generation():
    chemin = Path(CHEMIN_DOC)
    assert chemin.exists(), (
        f"{chemin} manquant : python -m app.scripts.exporter_contrat"
    )
    assert chemin.read_text(encoding="utf-8") == generer()


def test_la_generation_porte_les_elements_du_contrat():
    texte = generer()
    for attendu in (
        "/api/v2/capabilities",
        "/mcp",
        "tools/list",
        "tools/call",
        "prompts/get",
        "rechercher_capacites",
        "mesagents:read",
        "mesagents:delegate",
        "guard_rejected",
        "dependency_not_allowed",
        "Cache-Control: no-store",
        "scope_used",
        "oauth-protected-resource",
    ):
        assert attendu in texte, attendu
