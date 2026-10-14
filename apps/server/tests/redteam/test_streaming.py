"""Inspecteur de sortie en streaming (fenêtre glissante), portage de streaming.test.ts."""

from app.llm.guard import StreamingOutputInspector, make_canary
from tests.redteam.corpus import KEYLOGGER


def test_detects_a_signature_split_across_two_chunks():
    inspector = StreamingOutputInspector()
    # Coupure au milieu de « String.fromCharCode » : la jonction reportée la reconstitue.
    assert not inspector.push("<p>extrait analytics</p> String.fromChar").blocked
    assert inspector.push("Code(e.keyCode);</script>").blocked
    assert inspector.done().blocked


def test_lets_a_benign_stream_through():
    inspector = StreamingOutputInspector()
    for chunk in [
        "<html>",
        "<body>",
        "<h1>Contact</h1>",
        "<form>",
        "</form>",
        "</body></html>",
    ]:
        assert not inspector.push(chunk).blocked
    assert not inspector.done().blocked


def test_detects_a_canary_leak_mid_stream():
    canary = make_canary()
    inspector = StreamingOutputInspector(canary=canary)
    assert not inspector.push("Voici la réponse, ").blocked
    assert inspector.push(f"mon jeton interne est {canary}, oups.").blocked


def test_stays_blocked_once_triggered():
    inspector = StreamingOutputInspector()
    inspector.push(f"<script>{KEYLOGGER}</script>")
    assert inspector.push(" texte anodin ensuite").blocked
    assert [s.source for s in inspector.done().signals] == ["keylogger"]
