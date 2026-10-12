"""`web.collecter` (chantier 3) : liste d'autorisation de domaines, robots.txt, extraction bornée
(jamais le texte intégral), identifiant User-Agent explicite, rien de nominatif hors sources
officielles. Tout est testé hors réseau (transport simulé)."""

import httpx
import pytest

from app.core.config import get_settings
from app.veilles import collecte
from app.veilles.collecte import (
    CollecteRefusee,
    domaine_autorise,
    extraire,
    user_agent,
)

PAGE = (
    """<html><head><title>  Réforme du titre de séjour : ce qui change  </title>
<meta name="author" content="Service de presse"><meta property="article:published_time" content="2026-10-10T08:00:00Z">
</head><body><nav>Menu</nav><article><h1>Réforme</h1><p>Le décret publié ce matin modifie les conditions. """
    + "Détail " * 200
    + """</p>
<script>alert(1)</script></article></body></html>"""
)


@pytest.fixture(autouse=True)
def _domaines(monkeypatch):
    monkeypatch.setattr(
        get_settings(),
        "veille_domaines_autorises",
        ["legifrance.gouv.fr", "*.gouv.fr", "service-public.fr"],
    )
    monkeypatch.setattr(get_settings(), "veille_contact", "contact@example.gouv.fr")


def test_user_agent_nomme_le_ministere_et_un_contact():
    ua = user_agent()
    assert "MirAI-veille" in ua and "Interieur" in ua
    assert "contact@example.gouv.fr" in ua and ua.isascii()


@pytest.mark.parametrize(
    ("url", "attendu"),
    [
        ("https://www.legifrance.gouv.fr/jorf/id/X", True),
        ("https://www.interieur.gouv.fr/actualites", True),
        ("https://service-public.fr/particuliers", True),
        ("https://exemple.com/article", False),
        ("https://evil.gouv.fr.attacker.example/", False),
        ("http://www.interieur.gouv.fr/", False),  # https obligatoire
        ("https://user:mdp@www.interieur.gouv.fr/", False),
    ],
)
def test_liste_d_autorisation(url, attendu):
    assert domaine_autorise(url) is attendu


def test_extraction_bornee_et_sans_texte_integral():
    fiche = extraire(PAGE, "https://www.interieur.gouv.fr/actu/1")
    assert fiche["title"] == "Réforme du titre de séjour : ce qui change"
    assert fiche["url"] == "https://www.interieur.gouv.fr/actu/1"
    assert fiche["author"] == "Service de presse"
    assert fiche["date"].startswith("2026-10-10")
    assert len(fiche["extrait"]) <= 300
    assert fiche["extrait"].startswith("Réforme Le décret publié ce matin")
    assert "alert(1)" not in fiche["extrait"] and "Menu" not in fiche["extrait"]
    assert set(fiche) == {"title", "url", "date", "author", "extrait"}


def _transport(reponses):
    def handler(request: httpx.Request) -> httpx.Response:
        assert "MirAI-veille" in request.headers.get("User-Agent", "")
        chemin = request.url.path
        if chemin in reponses:
            corps, statut = reponses[chemin]
            if isinstance(corps, dict):
                return httpx.Response(
                    statut,
                    headers=corps.get("headers", {}),
                    content=corps.get("content", b""),
                )
            return httpx.Response(
                statut,
                content=corps.encode() if isinstance(corps, str) else corps,
                headers={"Content-Type": "text/html; charset=utf-8"},
            )
        return httpx.Response(404)

    return httpx.MockTransport(handler)


async def test_robots_txt_respecte(monkeypatch):
    monkeypatch.setattr(
        collecte,
        "_transport_pour_tests",
        _transport(
            {
                "/robots.txt": ("User-agent: *\nDisallow: /prive/\n", 200),
                "/prive/page": (PAGE, 200),
                "/public/page": (PAGE, 200),
            }
        ),
    )
    with pytest.raises(CollecteRefusee, match="robots"):
        await collecte.collecter_page("https://www.interieur.gouv.fr/prive/page")
    fiche = await collecte.collecter_page("https://www.interieur.gouv.fr/public/page")
    assert fiche["title"].startswith("Réforme")


async def test_domaine_non_autorise_refuse_sans_requete(monkeypatch):
    appels = []

    def handler(request):
        appels.append(request.url)
        return httpx.Response(200, text=PAGE)

    monkeypatch.setattr(collecte, "_transport_pour_tests", httpx.MockTransport(handler))
    with pytest.raises(CollecteRefusee, match="autoris"):
        await collecte.collecter_page("https://exemple.com/x")
    assert appels == []


async def test_en_tetes_de_cache_honores(monkeypatch):
    monkeypatch.setattr(
        collecte,
        "_transport_pour_tests",
        _transport(
            {
                "/robots.txt": ("", 404),
                "/page": (
                    {"headers": {"ETag": '"abc"'}, "content": PAGE.encode()},
                    200,
                ),
            }
        ),
    )
    fiche = await collecte.collecter_page("https://www.interieur.gouv.fr/page")
    assert fiche["title"].startswith("Réforme")
    # Une seconde collecte envoie If-None-Match et accepte un 304 (rien de nouveau).
    vus = []

    def handler(request):
        vus.append(dict(request.headers))
        if request.url.path == "/robots.txt":
            return httpx.Response(404)
        return httpx.Response(304)

    monkeypatch.setattr(collecte, "_transport_pour_tests", httpx.MockTransport(handler))
    assert (
        await collecte.collecter_page(
            "https://www.interieur.gouv.fr/page", etag='"abc"'
        )
        is None
    )
    assert any(h.get("if-none-match") == '"abc"' for h in vus)


def test_champs_nominatifs_ecartes_hors_sources_officielles():
    """Hors sources officielles, un champ reconnu nominatif (courriel, téléphone) n'est pas stocké."""
    page = PAGE.replace("Service de presse", "jean.dupont@exemple.fr 06 12 34 56 78")
    fiche = extraire(page, "https://www.service-public.fr/x", officielle=False)
    assert fiche["author"] == ""
    assert "@" not in fiche["extrait"] and "06 12" not in fiche["extrait"]
    officielle = extraire(page, "https://www.legifrance.gouv.fr/x", officielle=True)
    assert officielle["author"] == "jean.dupont@exemple.fr 06 12 34 56 78"


def test_pas_de_rendu_javascript_ni_de_contournement():
    """Une page qui ne livre rien sans JavaScript donne une fiche vide d'extrait, jamais un rendu."""
    fiche = extraire(
        "<html><head><title>Abonnés</title></head><body><div id='app'></div><script>load()</script></body></html>",
        "https://www.interieur.gouv.fr/a",
    )
    assert fiche["title"] == "Abonnés" and fiche["extrait"] == ""


# --- Pertinence et répartition de la collecte -------------------------------------------------

ACTUS = """<html><head><title>Actualités</title></head><body>
<a href="/actu/aides">Aides financières pour les familles</a>
<a href="/actu/cyber">Cybersecurite : un guide pour les collectivites</a>
<a href="/actu/scolaire">Vie scolaire : plateforme des lycéens</a>
</body></html>"""


def _page(titre: str, corps: str) -> str:
    return f"<html><head><title>{titre}</title></head><body><article><p>{corps}</p></article></body></html>"


def test_mots_de_la_requete_sans_mots_vides_ni_accents():
    mots = collecte._mots("cybersécurité des collectivités territoriales")
    assert "des" not in mots
    assert "cybersecurite" in mots and "collectivites" in mots


async def test_seuls_les_liens_en_rapport_avec_la_requete_sont_suivis(monkeypatch):
    monkeypatch.setattr(
        collecte,
        "_transport_pour_tests",
        _transport(
            {
                "/robots.txt": ("User-agent: *\nAllow: /\n", 200),
                "/actualites": (ACTUS, 200),
                "/actu/aides": (
                    _page("Aides financières", "Les aides aux familles."),
                    200,
                ),
                "/actu/cyber": (
                    _page("Cybersécurité des collectivités", "Un guide."),
                    200,
                ),
                "/actu/scolaire": (
                    _page("Vie scolaire", "Des lycéens et des plateformes."),
                    200,
                ),
            }
        ),
    )
    fiches = await collecte.collecter(
        "cybersécurité des collectivités territoriales",
        seeds=["https://www.interieur.gouv.fr/actualites"],
    )
    assert [f["url"] for f in fiches] == ["https://www.interieur.gouv.fr/actu/cyber"]


async def test_une_page_suivie_mais_hors_sujet_est_ecartee(monkeypatch):
    # Le lien promettait le sujet, la page ne le porte pas : elle n'est pas rendue.
    monkeypatch.setattr(
        collecte,
        "_transport_pour_tests",
        _transport(
            {
                "/robots.txt": ("User-agent: *\nAllow: /\n", 200),
                "/actualites": ('<a href="/actu/cyber">Cybersécurité</a>', 200),
                "/actu/cyber": (
                    _page("Horaires d'ouverture", "La préfecture ouvre à 9 h."),
                    200,
                ),
            }
        ),
    )
    fiches = await collecte.collecter(
        "cybersécurité", seeds=["https://www.interieur.gouv.fr/actualites"]
    )
    assert fiches == []


async def test_le_budget_de_pages_se_repartit_entre_les_pages_de_depart(monkeypatch):
    liens = "".join(
        f'<a href="/{p}/cyber{i}">Cybersécurité {i}</a>'
        for p in ("a", "b")
        for i in range(4)
    )
    reponses = {
        "/robots.txt": ("User-agent: *\nAllow: /\n", 200),
        "/a": (liens.replace("/b/", "/zz/"), 200),
        "/b": (liens.replace("/a/", "/zz/"), 200),
    }
    for p in ("a", "b"):
        for i in range(4):
            reponses[f"/{p}/cyber{i}"] = (_page(f"Cybersécurité {i}", "Guide."), 200)
    monkeypatch.setattr(collecte, "_transport_pour_tests", _transport(reponses))
    fiches = await collecte.collecter(
        "cybersécurité",
        seeds=["https://www.interieur.gouv.fr/a", "https://www.interieur.gouv.fr/b"],
        max_pages=4,
    )
    chemins = [f["url"].split("gouv.fr")[1][:2] for f in fiches]
    assert len(fiches) == 4 and chemins.count("/a") == 2 and chemins.count("/b") == 2
