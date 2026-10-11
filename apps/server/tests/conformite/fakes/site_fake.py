"""Faux site institutionnel pour la conformité des veilles : une page d'actualités et des articles.
Autorisé par VEILLE_DOMAINES_AUTORISES=["site-fake"] (http admis en compose seulement)."""

from fastapi import FastAPI
from fastapi.responses import HTMLResponse, PlainTextResponse

app = FastAPI(title="site-fake")

ARTICLES = {
    1: ("Réforme du séjour : ce qui change au 1er janvier", "2026-10-10"),
    2: ("Titres de séjour : nouvelle procédure de renouvellement", "2026-10-11"),
    3: ("Sécurité intérieure : bilan de l'année", "2026-10-09"),
}


@app.get("/robots.txt", response_class=PlainTextResponse)
async def robots():
    return "User-agent: *\nDisallow: /prive/\n"


@app.get("/actualites", response_class=HTMLResponse)
async def actualites():
    liens = "".join(
        f'<li><a href="/actu/{n}">{t}</a></li>' for n, (t, _) in ARTICLES.items()
    )
    return f"<html><head><title>Actualités</title></head><body><nav>Menu</nav><ul>{liens}</ul><a href='/prive/x'>Privé</a></body></html>"


@app.get("/actu/{n}", response_class=HTMLResponse)
async def article(n: int):
    titre, date = ARTICLES.get(n, ("Introuvable", ""))
    corps = " ".join(
        f"Paragraphe {i} de l'article {n} sur le séjour et les titres."
        for i in range(40)
    )
    return f'<html><head><title>{titre}</title><meta property="article:published_time" content="{date}T08:00:00Z"><meta name="author" content="Service de presse"></head><body><article><h1>{titre}</h1><p>{corps}</p></article></body></html>'


@app.get("/prive/{reste}", response_class=HTMLResponse)
async def prive(reste: str):
    return "<html><head><title>Privé</title></head><body>secret</body></html>"


@app.get("/health")
async def health():
    return {"status": "ok"}
