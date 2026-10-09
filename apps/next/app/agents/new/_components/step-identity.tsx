// Étape 1 — Identité de l'agent (§3.1 du prompt).
// Lit / écrit via useWizard() depuis _context.tsx.

'use client';

import { useEffect, useMemo, useRef, useState } from 'react';
import { useWizard, type AgentVisibility } from '../_context';

type Category = {
  value: string;
  label: string;
  icon: string;
};

const CATEGORIES: Category[] = [
  { value: 'redaction', label: 'Rédaction', icon: 'fr-icon-edit-line' },
  { value: 'juridique', label: 'Juridique', icon: 'fr-icon-scales-3-line' },
  { value: 'rh', label: 'Ressources humaines', icon: 'fr-icon-team-line' },
  { value: 'securite', label: 'Sécurité', icon: 'fr-icon-shield-line' },
  { value: 'immigration', label: 'Immigration', icon: 'fr-icon-global-line' },
  { value: 'prefecture', label: 'Préfecture', icon: 'fr-icon-government-line' },
  { value: 'it', label: 'IT / Systèmes d’information', icon: 'fr-icon-computer-line' },
  { value: 'communication', label: 'Communication', icon: 'fr-icon-chat-3-line' },
  { value: 'transverse', label: 'Transverse', icon: 'fr-icon-links-line' },
];

type KcGroup = { id: string; path: string; name: string; depth: number };

export function StepIdentity() {
  const { draft, update } = useWizard();
  const [groups, setGroups] = useState<KcGroup[]>([]);
  const [groupsState, setGroupsState] = useState<'idle' | 'loading' | 'error' | 'ok'>('idle');
  const [groupQuery, setGroupQuery] = useState('');
  const [groupOpen, setGroupOpen] = useState(false);
  const comboboxRef = useRef<HTMLDivElement | null>(null);

  const selectedCategory = CATEGORIES.find((c) => c.value === draft.category);

  useEffect(() => {
    if (draft.visibility !== 'community' || groupsState !== 'idle') return;
    setGroupsState('loading');
    fetch('/api/ab/keycloak/groups')
      .then((r) => r.json())
      .then((data) => {
        if (Array.isArray(data.groups)) {
          setGroups(data.groups);
          setGroupsState('ok');
        } else {
          setGroupsState('error');
        }
      })
      .catch(() => setGroupsState('error'));
  }, [draft.visibility, groupsState]);

  useEffect(() => {
    function handler(e: MouseEvent) {
      if (comboboxRef.current && !comboboxRef.current.contains(e.target as Node)) {
        setGroupOpen(false);
      }
    }
    document.addEventListener('click', handler);
    return () => document.removeEventListener('click', handler);
  }, []);

  const filteredGroups = useMemo(() => {
    const q = groupQuery.trim().toLowerCase();
    if (!q) return groups;
    return groups.filter(
      (g) => g.path.toLowerCase().includes(q) || g.name.toLowerCase().includes(q),
    );
  }, [groups, groupQuery]);

  function setVisibility(v: AgentVisibility) {
    update({ visibility: v });
    if (v !== 'community') update({ communityPath: null });
  }

  return (
    <div className="fr-grid-row fr-grid-row--gutters">
      <div className="fr-col-12">
        <div className="fr-input-group">
          <label className="fr-label" htmlFor="agent-name">
            Nom de l&apos;agent
            <span className="fr-hint-text">
              Un nom court et explicite. Ex : « Rédacteur de notes CESEDA »,
              « Assistant accueil préfecture ».
            </span>
          </label>
          <input
            className="fr-input"
            id="agent-name"
            type="text"
            maxLength={60}
            placeholder="Ex : Rédacteur de notes CESEDA"
            value={draft.name}
            onChange={(e) => update({ name: e.target.value })}
          />
        </div>
      </div>
      <div className="fr-col-12">
        <div className="fr-input-group">
          <label className="fr-label" htmlFor="agent-description">
            Description courte
            <span className="fr-hint-text">
              Visible dans le catalogue. À qui sert l&apos;agent et pour quoi ? 280 caractères max.
            </span>
          </label>
          <textarea
            className="fr-input"
            id="agent-description"
            rows={3}
            maxLength={280}
            placeholder="Ex : Aide à la rédaction de notes juridiques sur le Code de l'entrée et du séjour des étrangers. Destiné aux agents de la DLPAJ. Cite systématiquement les articles du CESEDA."
            value={draft.description}
            onChange={(e) => update({ description: e.target.value })}
          />
        </div>
      </div>

      {/* Catégorie métier avec icônes */}
      <div className="fr-col-12 fr-col-md-6">
        <div className="fr-select-group">
          <label className="fr-label" htmlFor="agent-category">
            Catégorie métier
            <span className="fr-hint-text">
              Chaque catégorie propose une icône qui sera affichée sur l&apos;agent.
            </span>
          </label>
          <select
            className="fr-select"
            id="agent-category"
            value={draft.category}
            onChange={(e) => update({ category: e.target.value })}
          >
            <option value="">Sélectionner une catégorie</option>
            {CATEGORIES.map((c) => (
              <option key={c.value} value={c.value}>
                {c.label}
              </option>
            ))}
          </select>
        </div>
        {selectedCategory && (
          <div
            className="fr-mt-2w"
            style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}
          >
            <span
              className={`${selectedCategory.icon} fr-icon--lg`}
              aria-hidden="true"
              style={{ color: 'var(--text-active-blue-france)' }}
            />
            <span className="fr-text--sm">
              Icône associée à la catégorie <strong>{selectedCategory.label}</strong>
            </span>
          </div>
        )}
      </div>

      {/* Visibilité */}
      <div className="fr-col-12 fr-col-md-6">
        <fieldset className="fr-fieldset">
          <legend className="fr-fieldset__legend">Visibilité</legend>
          <div className="fr-fieldset__content">
            <div className="fr-radio-group">
              <input
                type="radio"
                id="vis-private"
                name="visibility"
                checked={draft.visibility === 'private'}
                onChange={() => setVisibility('private')}
              />
              <label className="fr-label" htmlFor="vis-private">
                Privé
                <span className="fr-hint-text">Visible par vous seul</span>
              </label>
            </div>
            <div className="fr-radio-group">
              <input
                type="radio"
                id="vis-community"
                name="visibility"
                checked={draft.visibility === 'community'}
                onChange={() => setVisibility('community')}
              />
              <label className="fr-label" htmlFor="vis-community">
                Ma communauté
                <span className="fr-hint-text">Partagé avec un groupe d&apos;utilisateurs</span>
              </label>
            </div>
            <div className="fr-radio-group">
              <input
                type="radio"
                id="vis-ministry"
                name="visibility"
                checked={draft.visibility === 'ministry'}
                onChange={() => setVisibility('ministry')}
              />
              <label className="fr-label" htmlFor="vis-ministry">
                Tout le ministère
                <span className="fr-hint-text">Publication ouverte après validation</span>
              </label>
            </div>
          </div>
        </fieldset>
      </div>

      {/* Combobox searchable pour le groupe */}
      {draft.visibility === 'community' && (
        <div className="fr-col-12">
          <div className="fr-input-group" ref={comboboxRef}>
            <label className="fr-label" htmlFor="agent-community">
              Communauté
              <span className="fr-hint-text">
                Sélectionnez le groupe Keycloak avec lequel partager l&apos;agent.
                Tapez pour filtrer.
              </span>
            </label>
            <input
              id="agent-community"
              className="fr-input"
              type="text"
              role="combobox"
              aria-expanded={groupOpen}
              aria-autocomplete="list"
              placeholder={
                groupsState === 'loading'
                  ? 'Chargement des groupes…'
                  : groupsState === 'error'
                    ? 'Erreur — impossible de charger les groupes'
                    : draft.communityPath || 'Rechercher un groupe…'
              }
              value={groupOpen ? groupQuery : draft.communityPath || groupQuery}
              onFocus={() => setGroupOpen(true)}
              onChange={(e) => {
                setGroupQuery(e.target.value);
                setGroupOpen(true);
                if (draft.communityPath && e.target.value !== draft.communityPath) {
                  update({ communityPath: null });
                }
              }}
              disabled={groupsState === 'loading' || groupsState === 'error'}
            />
            {groupOpen && groupsState === 'ok' && (
              <div
                role="listbox"
                style={{
                  border: '1px solid var(--border-default-grey)',
                  background: 'var(--background-default-grey)',
                  maxHeight: '240px',
                  overflowY: 'auto',
                  marginTop: '2px',
                  borderRadius: '4px',
                }}
              >
                {filteredGroups.length === 0 && (
                  <div className="fr-p-2w fr-text--sm" style={{ color: 'var(--text-mention-grey)' }}>
                    Aucun groupe ne correspond à « {groupQuery} »
                  </div>
                )}
                {filteredGroups.map((g) => (
                  <button
                    type="button"
                    key={g.id}
                    role="option"
                    aria-selected={draft.communityPath === g.path}
                    onClick={() => {
                      update({ communityPath: g.path });
                      setGroupQuery('');
                      setGroupOpen(false);
                    }}
                    style={{
                      display: 'block',
                      width: '100%',
                      textAlign: 'left',
                      padding: '0.5rem 0.75rem',
                      paddingLeft: `${0.75 + g.depth * 1}rem`,
                      background:
                        draft.communityPath === g.path
                          ? 'var(--background-alt-blue-france)'
                          : 'transparent',
                      border: 'none',
                      cursor: 'pointer',
                      fontFamily: 'inherit',
                      fontSize: '0.875rem',
                    }}
                  >
                    <span
                      className="fr-icon-group-line"
                      aria-hidden="true"
                      style={{ marginRight: '0.5rem' }}
                    />
                    <strong>{g.name}</strong>
                    <span
                      style={{
                        marginLeft: '0.5rem',
                        color: 'var(--text-mention-grey)',
                        fontSize: '0.75rem',
                      }}
                    >
                      {g.path}
                    </span>
                  </button>
                ))}
              </div>
            )}
            {groupsState === 'error' && (
              <p className="fr-error-text">
                Impossible de charger la liste des groupes. L&apos;admin Keycloak est
                peut-être hors ligne ou les credentials ne sont pas configurés.
              </p>
            )}
            {draft.communityPath && (
              <p className="fr-text--sm fr-mt-1w">
                Communauté sélectionnée : <strong>{draft.communityPath}</strong>{' '}
                <button
                  type="button"
                  className="fr-btn fr-btn--tertiary-no-outline fr-btn--sm"
                  onClick={() => update({ communityPath: null })}
                >
                  Changer
                </button>
              </p>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
