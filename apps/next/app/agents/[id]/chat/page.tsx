// Chat avec un agent — historique persisté, copier/telecharger, lien MirAI Chat.

'use client';

import { useEffect, useRef, useState } from 'react';
import { useParams } from 'next/navigation';
import Link from 'next/link';

type Message = { role: 'user' | 'assistant'; content: string };
type ConvSummary = { id: string; title: string; updatedAt: string };

type AgentConfig = {
  name: string;
  systemPrompt: string;
  greeting: string;
  examples: string[];
  modelId: string;
  temperature: number;
};

export default function AgentChatPage() {
  const { id } = useParams<{ id: string }>();
  const [config, setConfig] = useState<AgentConfig | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [conversationId, setConversationId] = useState<string | null>(null);
  const [conversations, setConversations] = useState<ConvSummary[]>([]);
  const [input, setInput] = useState('');
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [owuiUrl, setOwuiUrl] = useState<string | null>(null);
  const [showHistory, setShowHistory] = useState(false);
  const [copied, setCopied] = useState<number | null>(null);
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, busy]);

  // Charger config agent + historique conversations
  useEffect(() => {
    Promise.all([
      fetch(`/api/ab/agents/${id}`).then((r) => r.json()),
      fetch(`/api/ab/agents/${id}/conversations`).then((r) => r.json()),
    ])
      .then(([agentData, convData]) => {
        const cfg = agentData.config ?? {};
        setConfig({
          name: cfg.name ?? 'Agent',
          systemPrompt: cfg.systemPrompt ?? '',
          greeting: cfg.greeting ?? '',
          examples: Array.isArray(cfg.examples) ? cfg.examples : [],
          modelId: cfg.modelId ?? 'gpt-oss-120b',
          temperature: cfg.temperature ?? 0.7,
        });
        setConversations(convData.conversations ?? []);
      })
      .catch((err) => setError(String(err)))
      .finally(() => setLoading(false));
  }, [id]);

  async function loadConversation(convId: string) {
    const res = await fetch(`/api/ab/conversations/${convId}`);
    if (!res.ok) return;
    const data = await res.json();
    setMessages(data.messages ?? []);
    setConversationId(convId);
    setShowHistory(false);
  }

  async function deleteConversation(convId: string) {
    await fetch(`/api/ab/conversations/${convId}`, { method: 'DELETE' });
    setConversations((prev) => prev.filter((c) => c.id !== convId));
    if (conversationId === convId) {
      setMessages([]);
      setConversationId(null);
    }
  }

  function newConversation() {
    setMessages([]);
    setConversationId(null);
    setShowHistory(false);
  }

  async function send(text?: string) {
    const msg = text ?? input.trim();
    if (!msg || busy || !config) return;
    setInput('');
    const userMsg: Message = { role: 'user', content: msg };
    const updated = [...messages, userMsg];
    setMessages(updated);
    setBusy(true);
    setError(null);

    try {
      const res = await fetch(`/api/ab/agents/${id}/chat`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ messages: updated, conversationId }),
      });
      if (!res.ok) {
        const d = await res.json().catch(() => ({}));
        setError(d.message ?? `Erreur ${res.status} : ${d.error ?? 'inconnue'}`);
        setBusy(false);
        return;
      }
      const data = await res.json();
      setMessages([...updated, { role: 'assistant', content: data.content }]);
      if (data.conversationId) setConversationId(data.conversationId);
      if (data.owuiPublicUrl) setOwuiUrl(data.owuiPublicUrl);
    } catch (err) {
      setError(String(err));
    } finally {
      setBusy(false);
    }
  }

  function copyRichText(content: string, index: number) {
    // Copie en rich text (HTML) + texte brut en fallback
    const html = markdownToHtml(content);
    const richBlob = new Blob([html], { type: 'text/html' });
    const plainBlob = new Blob([content], { type: 'text/plain' });
    navigator.clipboard.write([
      new ClipboardItem({
        'text/html': richBlob,
        'text/plain': plainBlob,
      }),
    ]).then(() => {
      setCopied(index);
      setTimeout(() => setCopied(null), 2000);
    }).catch(() => {
      // Fallback navigateurs sans ClipboardItem
      navigator.clipboard.writeText(content).then(() => {
        setCopied(index);
        setTimeout(() => setCopied(null), 2000);
      });
    });
  }

  function downloadTxt(content: string, index: number) {
    const blob = new Blob([content], { type: 'text/plain;charset=utf-8' });
    triggerDownload(blob, `reponse-${index + 1}.txt`);
  }

  function downloadDocx(content: string, index: number) {
    // Genere un .docx minimal (format Office Open XML)
    const escaped = content
      .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
      .split('\n').map((line) => `<w:p><w:r><w:t xml:space="preserve">${line}</w:t></w:r></w:p>`).join('');
    const docxml = `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
<w:body>${escaped}</w:body></w:document>`;
    const rels = `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>
</Relationships>`;
    const contentTypes = `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
<Default Extension="xml" ContentType="application/xml"/>
<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
</Types>`;
    // Creer le ZIP via l'API native Blob (pas de lib externe)
    // Approche simplifiee : on genere un fichier .doc en HTML que Word ouvre
    const htmlDoc = `<html xmlns:o="urn:schemas-microsoft-com:office:office" xmlns:w="urn:schemas-microsoft-com:office:word" xmlns="http://www.w3.org/TR/REC-html40">
<head><meta charset="utf-8"><title>Reponse</title>
<!--[if gte mso 9]><xml><w:WordDocument><w:View>Print</w:View></w:WordDocument></xml><![endif]-->
</head><body>${markdownToHtml(content)}</body></html>`;
    const blob = new Blob([htmlDoc], { type: 'application/msword;charset=utf-8' });
    triggerDownload(blob, `reponse-${index + 1}.doc`);
  }

  function downloadOdt(content: string, index: number) {
    // Genere un .fodt (Flat ODT) avec styles ODF natifs :
    // - Heading 1/2/3 pour les titres markdown # ## ###
    // - Text Body pour les paragraphes
    // - Bold / Italic pour **gras** et *italique*
    // - List Bullet / List Number pour les listes - et 1.
    // - Preformatted Text pour les blocs de code ```

    // --- Styles ODF ---
    const styles = `
<office:automatic-styles>
  <style:style style:name="Bold" style:family="text">
    <style:text-properties fo:font-weight="bold"/>
  </style:style>
  <style:style style:name="Italic" style:family="text">
    <style:text-properties fo:font-style="italic"/>
  </style:style>
  <style:style style:name="Code" style:family="text">
    <style:text-properties style:font-name="Liberation Mono" fo:font-size="9pt" fo:background-color="#f0f0f0"/>
  </style:style>
  <style:style style:name="CodeBlock" style:family="paragraph">
    <style:paragraph-properties fo:background-color="#f5f5f5" fo:padding="0.3cm" fo:border="0.5pt solid #cccccc"/>
    <style:text-properties style:font-name="Liberation Mono" fo:font-size="9pt"/>
  </style:style>
  <style:style style:name="H1" style:family="paragraph" style:parent-style-name="Heading_20_1">
    <style:text-properties fo:font-size="18pt" fo:font-weight="bold" fo:color="#000091"/>
  </style:style>
  <style:style style:name="H2" style:family="paragraph" style:parent-style-name="Heading_20_2">
    <style:text-properties fo:font-size="15pt" fo:font-weight="bold" fo:color="#000091"/>
  </style:style>
  <style:style style:name="H3" style:family="paragraph" style:parent-style-name="Heading_20_3">
    <style:text-properties fo:font-size="12pt" fo:font-weight="bold" fo:color="#161616"/>
  </style:style>
</office:automatic-styles>`;

    // --- Conversion markdown → ODF ---
    let inCodeBlock = false;
    const odLines: string[] = [];
    const lines = content.split('\n');

    for (const line of lines) {
      // Blocs de code
      if (line.startsWith('```')) {
        inCodeBlock = !inCodeBlock;
        continue;
      }
      if (inCodeBlock) {
        const esc = escOdf(line);
        odLines.push(`<text:p text:style-name="CodeBlock">${esc}</text:p>`);
        continue;
      }

      const esc = escOdf(line);

      // Titres
      if (line.startsWith('### ')) {
        odLines.push(`<text:h text:style-name="H3" text:outline-level="3">${applyInline(line.slice(4))}</text:h>`);
      } else if (line.startsWith('## ')) {
        odLines.push(`<text:h text:style-name="H2" text:outline-level="2">${applyInline(line.slice(3))}</text:h>`);
      } else if (line.startsWith('# ')) {
        odLines.push(`<text:h text:style-name="H1" text:outline-level="1">${applyInline(line.slice(2))}</text:h>`);
      }
      // Listes a puces
      else if (line.startsWith('- ')) {
        odLines.push(`<text:list text:style-name="List_20_1"><text:list-item><text:p text:style-name="List_20_Bullet">${applyInline(line.slice(2))}</text:p></text:list-item></text:list>`);
      }
      // Listes numerotees
      else if (/^\d+\. /.test(line)) {
        odLines.push(`<text:list text:style-name="List_20_1"><text:list-item><text:p text:style-name="List_20_Number">${applyInline(line.replace(/^\d+\. /, ''))}</text:p></text:list-item></text:list>`);
      }
      // Ligne vide
      else if (line.trim() === '') {
        odLines.push('<text:p text:style-name="Text_20_body"/>');
      }
      // Paragraphe normal
      else {
        odLines.push(`<text:p text:style-name="Text_20_body">${applyInline(line)}</text:p>`);
      }
    }

    function escOdf(s: string): string {
      return s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
    }

    function applyInline(s: string): string {
      let out = escOdf(s);
      // Code inline `...`
      out = out.replace(/`([^`]+)`/g, '<text:span text:style-name="Code">$1</text:span>');
      // Gras **...**
      out = out.replace(/\*\*(.+?)\*\*/g, '<text:span text:style-name="Bold">$1</text:span>');
      // Italique *...*
      out = out.replace(/\*(.+?)\*/g, '<text:span text:style-name="Italic">$1</text:span>');
      return out;
    }

    const fodt = `<?xml version="1.0" encoding="UTF-8"?>
<office:document xmlns:office="urn:oasis:names:tc:opendocument:xmlns:office:1.0"
  xmlns:text="urn:oasis:names:tc:opendocument:xmlns:text:1.0"
  xmlns:style="urn:oasis:names:tc:opendocument:xmlns:style:1.0"
  xmlns:fo="urn:oasis:names:tc:opendocument:xmlns:xsl-fo-compatible:1.0"
  office:version="1.2" office:mimetype="application/vnd.oasis.opendocument.text">
${styles}
<office:body><office:text>
${odLines.join('\n')}
</office:text></office:body>
</office:document>`;

    const blob = new Blob([fodt], { type: 'application/vnd.oasis.opendocument.text;charset=utf-8' });
    triggerDownload(blob, `reponse-${index + 1}.fodt`);
  }

  function triggerDownload(blob: Blob, filename: string) {
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = filename;
    a.click();
    URL.revokeObjectURL(url);
  }

  /** Conversion markdown → HTML (titres, gras, italique, code, listes, paragraphes) */
  function markdownToHtml(md: string): string {
    let html = md
      .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');

    // Blocs de code ```
    html = html.replace(/```(\w*)\n([\s\S]*?)```/g,
      (_m, _lang, code) => `<pre style="background:#f5f5f5;padding:0.75rem;border-radius:6px;overflow-x:auto;font-size:0.85rem"><code>${code.trim()}</code></pre>`);

    // Code inline `...`
    html = html.replace(/`([^`]+)`/g,
      '<code style="background:#f0f0f0;padding:0.1rem 0.3rem;border-radius:3px;font-size:0.85em">$1</code>');

    // Titres
    html = html.replace(/^### (.+)$/gm, '<h4 style="margin:0.75rem 0 0.25rem;font-size:1rem">$1</h4>');
    html = html.replace(/^## (.+)$/gm, '<h3 style="margin:0.75rem 0 0.25rem;font-size:1.1rem">$1</h3>');
    html = html.replace(/^# (.+)$/gm, '<h2 style="margin:0.75rem 0 0.25rem;font-size:1.2rem">$1</h2>');

    // Gras / italique
    html = html.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
    html = html.replace(/\*(.+?)\*/g, '<em>$1</em>');

    // Listes non ordonnees (- item)
    html = html.replace(/^- (.+)$/gm, '<li>$1</li>');
    // Listes ordonnees (1. item)
    html = html.replace(/^\d+\. (.+)$/gm, '<li>$1</li>');

    // Grouper les <li> consecutifs en <ul>
    html = html.replace(/((?:<li>.*<\/li>\n?)+)/g, (block) => `<ul style="margin:0.5rem 0;padding-left:1.5rem">${block}</ul>`);

    // Paragraphes : double saut = nouveau <p>
    html = html.replace(/\n{2,}/g, '</p><p style="margin:0.5rem 0">');

    // Sauts de ligne simples → <br>
    html = html.replace(/\n/g, '<br>');

    // Envelopper dans un <p> si pas deja un bloc
    if (!html.startsWith('<')) {
      html = `<p style="margin:0.5rem 0">${html}</p>`;
    }

    // Nettoyage
    html = html.replace(/<p[^>]*><\/p>/g, '');
    html = html.replace(/<br>\s*(<\/?(h[2-4]|ul|pre|li))/g, '$1');
    html = html.replace(/(<\/(h[2-4]|ul|pre)>)\s*<br>/g, '$1');

    return html;
  }

  if (loading) return <div className="fr-container fr-py-4w">Chargement...</div>;
  if (!config) return <div className="fr-alert fr-alert--error"><p>Agent introuvable</p></div>;

  return (
    <div style={{ maxWidth: '900px', margin: '0 auto' }}>
      {/* Header */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '0.5rem' }}>
        <h1 className="fr-h3 fr-mb-0">{config.name}</h1>
        <div className="fr-btns-group fr-btns-group--inline fr-btns-group--sm">
          <button
            className="fr-btn fr-btn--tertiary fr-btn--sm"
            onClick={() => setShowHistory(!showHistory)}
          >
            Historique ({conversations.length})
          </button>
          <button className="fr-btn fr-btn--tertiary fr-btn--sm" onClick={newConversation}>
            Nouvelle conversation
          </button>
          {owuiUrl && (
            <a
              href={owuiUrl}
              target="_blank"
              rel="noopener noreferrer"
              className="fr-btn fr-btn--secondary fr-btn--sm fr-btn--icon-right fr-icon-external-link-line"
            >
              Poursuivre dans MirAI Chat
            </a>
          )}
          <Link href={`/agents/${id}/edit`} className="fr-btn fr-btn--tertiary fr-btn--sm">
            Modifier
          </Link>
          <Link href="/agents" className="fr-btn fr-btn--tertiary fr-btn--sm">
            Retour
          </Link>
        </div>
      </div>

      <p className="fr-text--xs fr-mb-2w" style={{ color: 'var(--text-mention-grey)' }}>
        {config.modelId} &middot; temp {config.temperature}
      </p>

      {/* Panneau historique */}
      {showHistory && (
        <div
          style={{
            border: '1px solid var(--border-default-grey)',
            borderRadius: '8px',
            padding: '1rem',
            marginBottom: '1rem',
            maxHeight: '200px',
            overflowY: 'auto',
            background: 'var(--background-contrast-grey)',
          }}
        >
          <h4 className="fr-h6 fr-mb-1w">Conversations precedentes</h4>
          {conversations.length === 0 && (
            <p className="fr-text--sm" style={{ color: 'var(--text-mention-grey)' }}>Aucune conversation.</p>
          )}
          {conversations.map((c) => (
            <div
              key={c.id}
              style={{
                display: 'flex',
                justifyContent: 'space-between',
                alignItems: 'center',
                padding: '0.5rem 0',
                borderBottom: '1px solid var(--border-default-grey)',
              }}
            >
              <button
                onClick={() => loadConversation(c.id)}
                style={{
                  background: 'none',
                  border: 'none',
                  cursor: 'pointer',
                  textAlign: 'left',
                  flex: 1,
                  fontFamily: 'inherit',
                  fontSize: '0.875rem',
                  fontWeight: conversationId === c.id ? 700 : 400,
                }}
              >
                {c.title}
              </button>
              <button
                onClick={() => deleteConversation(c.id)}
                className="fr-btn fr-btn--tertiary-no-outline fr-btn--sm fr-icon-delete-line"
                title="Supprimer"
                style={{ color: 'var(--text-default-error)' }}
              />
            </div>
          ))}
        </div>
      )}

      {/* Zone de chat */}
      <div
        style={{
          border: '1px solid var(--border-default-grey)',
          borderRadius: '8px',
          height: '500px',
          display: 'flex',
          flexDirection: 'column',
          overflow: 'hidden',
          background: 'var(--background-default-grey)',
        }}
      >
        <div style={{ flex: 1, overflowY: 'auto', padding: '1rem' }}>
          {/* Greeting + exemples si pas de messages */}
          {messages.length === 0 && (
            <>
              {config.greeting && (
                <div style={{ padding: '1rem', borderRadius: '12px', background: 'var(--background-contrast-grey)', marginBottom: '1rem', fontSize: '0.95rem', lineHeight: 1.6 }}>
                  {config.greeting}
                </div>
              )}
              {config.examples.length > 0 && (
                <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.5rem', marginBottom: '1rem' }}>
                  {config.examples.map((ex, i) => (
                    <button key={i} className="fr-tag" onClick={() => send(ex)} disabled={busy} style={{ cursor: 'pointer' }}>
                      {ex}
                    </button>
                  ))}
                </div>
              )}
            </>
          )}

          {/* Messages */}
          {messages.map((m, i) => (
            <div key={i} style={{ display: 'flex', justifyContent: m.role === 'user' ? 'flex-end' : 'flex-start', marginBottom: '0.75rem' }}>
              <div style={{ maxWidth: '80%', position: 'relative' }}>
                <div
                  style={{
                    padding: '0.75rem 1rem',
                    borderRadius: m.role === 'user' ? '16px 16px 4px 16px' : '16px 16px 16px 4px',
                    background: m.role === 'user' ? 'var(--background-action-high-blue-france)' : 'var(--background-contrast-grey)',
                    color: m.role === 'user' ? 'white' : 'inherit',
                    fontSize: '0.9rem',
                    lineHeight: 1.6,
                  }}
                >
                  {m.role === 'assistant' ? (
                    <div
                      className="chat-md"
                      dangerouslySetInnerHTML={{ __html: markdownToHtml(m.content) }}
                    />
                  ) : (
                    <span style={{ whiteSpace: 'pre-wrap' }}>{m.content}</span>
                  )}
                </div>
                {/* Actions sur les reponses assistant */}
                {m.role === 'assistant' && (
                  <div style={{ display: 'flex', gap: '0.5rem', marginTop: '0.35rem', flexWrap: 'wrap' }}>
                    <ActionBtn
                      icon="📋"
                      label={copied === i ? 'Copie !' : 'Copier'}
                      onClick={() => copyRichText(m.content, i)}
                      title="Copier en texte riche (colle dans Word, mail...)"
                    />
                    <ActionBtn
                      icon="📄"
                      label=".txt"
                      onClick={() => downloadTxt(m.content, i)}
                      title="Telecharger en texte brut"
                    />
                    <ActionBtn
                      icon="📝"
                      label=".doc"
                      onClick={() => downloadDocx(m.content, i)}
                      title="Telecharger au format Word"
                    />
                    <ActionBtn
                      icon="📃"
                      label=".odt"
                      onClick={() => downloadOdt(m.content, i)}
                      title="Telecharger au format LibreOffice Writer"
                    />
                  </div>
                )}
              </div>
            </div>
          ))}

          {busy && (
            <div style={{ marginBottom: '0.75rem' }}>
              <div style={{ display: 'inline-block', padding: '0.75rem 1rem', borderRadius: '16px 16px 16px 4px', background: 'var(--background-contrast-grey)', opacity: 0.6 }}>
                ...
              </div>
            </div>
          )}
          {error && <div className="fr-alert fr-alert--error fr-alert--sm fr-mb-2w"><p>{error}</p></div>}
          <div ref={bottomRef} />
        </div>

        {/* Bouton MirAI Chat en bas du chat */}
        {owuiUrl && (
          <div style={{ padding: '0.5rem 0.75rem', borderTop: '1px solid var(--border-default-grey)', background: 'var(--background-alt-blue-france)', textAlign: 'center' }}>
            <a
              href={owuiUrl}
              target="_blank"
              rel="noopener noreferrer"
              className="fr-text--sm"
              style={{ color: 'var(--text-inverted-blue-france)' }}
            >
              Poursuivre dans MirAI Chat pour utiliser les outils avances (RAG, recherche web, generation d&apos;image...)
            </a>
          </div>
        )}

        {/* Input */}
        <div style={{ padding: '0.75rem', borderTop: '1px solid var(--border-default-grey)', display: 'flex', gap: '0.5rem' }}>
          <input
            className="fr-input"
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send(); } }}
            placeholder="Posez votre question..."
            disabled={busy}
            style={{ flex: 1 }}
          />
          <button className="fr-btn" disabled={busy || !input.trim()} onClick={() => send()}>
            Envoyer
          </button>
        </div>
      </div>
    </div>
  );
}

function ActionBtn({
  icon,
  label,
  onClick,
  title,
}: {
  icon: string;
  label: string;
  onClick: () => void;
  title: string;
}) {
  return (
    <button
      onClick={onClick}
      title={title}
      style={{
        background: 'var(--background-contrast-grey)',
        border: '1px solid var(--border-default-grey)',
        borderRadius: '4px',
        cursor: 'pointer',
        fontSize: '0.75rem',
        color: 'var(--text-mention-grey)',
        padding: '3px 8px',
        display: 'flex',
        alignItems: 'center',
        gap: '0.25rem',
        fontFamily: 'inherit',
      }}
    >
      <span style={{ fontSize: '0.85rem' }}>{icon}</span>
      {label}
    </button>
  );
}
