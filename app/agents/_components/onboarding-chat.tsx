// Widget de chat flottant — assistant d'onboarding qui guide la creation
// d'un agent par questions successives. Quand l'assistant a recueilli
// toutes les infos, il renvoie un JSON parse en `agentConfig` et le
// bouton "Creer cet agent" pre-remplit le wizard.

'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import { useRouter } from 'next/navigation';

type Message = {
  role: 'user' | 'assistant';
  content: string;
};

type AgentConfig = {
  ready: boolean;
  name: string;
  description: string;
  category: string;
  systemPrompt: string;
  greeting: string;
  examples: string[];
};

export function OnboardingChat() {
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState('');
  const [busy, setBusy] = useState(false);
  const [agentConfig, setAgentConfig] = useState<AgentConfig | null>(null);
  const [error, setError] = useState<string | null>(null);
  const bottomRef = useRef<HTMLDivElement>(null);

  // Auto-scroll
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, busy]);

  // Premier message de l'assistant au lancement
  const startChat = useCallback(async () => {
    setOpen(true);
    if (messages.length > 0) return; // deja demarre
    setBusy(true);
    setError(null);
    try {
      const res = await fetch('/api/ab/onboarding/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          messages: [{ role: 'user', content: 'Bonjour, je souhaite creer un agent.' }],
        }),
      });
      if (!res.ok) {
        const d = await res.json().catch(() => ({}));
        throw new Error(d.message ?? `Erreur ${res.status}`);
      }
      const data = await res.json();
      setMessages([
        { role: 'user', content: 'Bonjour, je souhaite creer un agent.' },
        { role: 'assistant', content: data.message },
      ]);
    } catch (err) {
      setError(String(err));
    } finally {
      setBusy(false);
    }
  }, [messages.length]);

  async function send() {
    if (!input.trim() || busy) return;
    const userMsg: Message = { role: 'user', content: input.trim() };
    const updatedMessages = [...messages, userMsg];
    setMessages(updatedMessages);
    setInput('');
    setBusy(true);
    setError(null);

    try {
      const res = await fetch('/api/ab/onboarding/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ messages: updatedMessages }),
      });
      if (!res.ok) {
        const d = await res.json().catch(() => ({}));
        throw new Error(d.message ?? `Erreur ${res.status}`);
      }
      const data = await res.json();
      setMessages([...updatedMessages, { role: 'assistant', content: data.message }]);
      if (data.agentConfig) {
        setAgentConfig(data.agentConfig);
      }
    } catch (err) {
      setError(String(err));
    } finally {
      setBusy(false);
    }
  }

  function createAgent() {
    if (!agentConfig) return;
    // Encode la config dans le hash pour que le wizard la lise
    const encoded = encodeURIComponent(JSON.stringify(agentConfig));
    router.push(`/agents/new?onboarding=${encoded}`);
  }

  // Bouton flottant
  if (!open) {
    return (
      <button
        onClick={startChat}
        className="fr-btn fr-btn--lg"
        style={{
          position: 'fixed',
          bottom: '2rem',
          right: '2rem',
          zIndex: 1000,
          borderRadius: '50px',
          boxShadow: '0 4px 12px rgba(0,0,0,0.25)',
          display: 'flex',
          alignItems: 'center',
          gap: '0.5rem',
          padding: '0.75rem 1.5rem',
        }}
      >
        <span className="fr-icon-chat-3-line" aria-hidden="true" />
        Aide-moi a creer mon agent
      </button>
    );
  }

  // Panel de chat
  return (
    <div
      style={{
        position: 'fixed',
        bottom: '1rem',
        right: '1rem',
        width: '420px',
        maxWidth: 'calc(100vw - 2rem)',
        height: '600px',
        maxHeight: 'calc(100vh - 4rem)',
        zIndex: 1000,
        display: 'flex',
        flexDirection: 'column',
        borderRadius: '12px',
        overflow: 'hidden',
        boxShadow: '0 8px 32px rgba(0,0,0,0.2)',
        border: '1px solid var(--border-default-grey)',
        background: 'var(--background-default-grey)',
      }}
    >
      {/* Header */}
      <div
        style={{
          padding: '0.75rem 1rem',
          background: 'var(--background-action-high-blue-france)',
          color: 'white',
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
        }}
      >
        <strong>Assistant de creation</strong>
        <button
          onClick={() => setOpen(false)}
          style={{
            background: 'none',
            border: 'none',
            color: 'white',
            cursor: 'pointer',
            fontSize: '1.25rem',
          }}
          title="Reduire"
        >
          &times;
        </button>
      </div>

      {/* Messages */}
      <div
        style={{
          flex: 1,
          overflowY: 'auto',
          padding: '1rem',
          display: 'flex',
          flexDirection: 'column',
          gap: '0.75rem',
        }}
      >
        {messages
          .filter((m) => m.role !== 'user' || m.content !== 'Bonjour, je souhaite creer un agent.')
          .map((m, i) => (
            <div
              key={i}
              style={{
                alignSelf: m.role === 'user' ? 'flex-end' : 'flex-start',
                maxWidth: '85%',
                padding: '0.75rem 1rem',
                borderRadius: m.role === 'user' ? '16px 16px 4px 16px' : '16px 16px 16px 4px',
                background:
                  m.role === 'user'
                    ? 'var(--background-action-high-blue-france)'
                    : 'var(--background-contrast-grey)',
                color: m.role === 'user' ? 'white' : 'inherit',
                fontSize: '0.9rem',
                lineHeight: 1.5,
                whiteSpace: 'pre-wrap',
              }}
            >
              {m.content.replace(/```json[\s\S]*?```/g, '').trim() || m.content}
            </div>
          ))}
        {busy && (
          <div
            style={{
              alignSelf: 'flex-start',
              padding: '0.75rem 1rem',
              borderRadius: '16px 16px 16px 4px',
              background: 'var(--background-contrast-grey)',
              fontSize: '0.9rem',
              opacity: 0.6,
            }}
          >
            ...
          </div>
        )}
        {error && (
          <div className="fr-alert fr-alert--error fr-alert--sm">
            <p>{error}</p>
          </div>
        )}
        <div ref={bottomRef} />
      </div>

      {/* Agent config ready */}
      {agentConfig && (
        <div
          style={{
            padding: '0.75rem 1rem',
            background: 'var(--background-contrast-info)',
            borderTop: '1px solid var(--border-default-grey)',
          }}
        >
          <p className="fr-text--sm fr-mb-1w">
            <strong>{agentConfig.name}</strong> est pret a etre cree !
          </p>
          <button className="fr-btn fr-btn--sm" onClick={createAgent}>
            Creer cet agent
          </button>
        </div>
      )}

      {/* Input */}
      <div
        style={{
          padding: '0.75rem',
          borderTop: '1px solid var(--border-default-grey)',
          display: 'flex',
          gap: '0.5rem',
        }}
      >
        <input
          type="text"
          className="fr-input"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
              e.preventDefault();
              send();
            }
          }}
          placeholder="Votre reponse..."
          disabled={busy}
          style={{ flex: 1, fontSize: '0.9rem' }}
        />
        <button
          className="fr-btn fr-btn--sm"
          disabled={busy || !input.trim()}
          onClick={send}
        >
          Envoyer
        </button>
      </div>
    </div>
  );
}
