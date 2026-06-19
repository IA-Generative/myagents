// Page "Mes Agents" — landing principale après login.
// Liste les agents persistés du user, avec un onboarding si la liste est vide
// et une bannière de succès si on arrive depuis une publication.

import Link from 'next/link';
import { redirect } from 'next/navigation';
import { getServerSession } from 'next-auth';
import { authOptions } from '@/lib/auth';
import { prisma } from '@/lib/db';
import { env } from '@/lib/env';
import { OnboardingChat } from './_components/onboarding-chat';

type SearchParams = { saved?: string };

export default async function AgentsPage({
  searchParams,
}: {
  searchParams: Promise<SearchParams>;
}) {
  const session = await getServerSession(authOptions);
  if (!session?.user?.id) redirect('/sign-in');

  const displayName = session.user.name || session.user.email || 'agent';

  const agents = await prisma.agent.findMany({
    where: { creatorId: session.user.id, NOT: { status: 'archived' } },
    orderBy: { updatedAt: 'desc' },
    take: 50,
  });

  const owuiPublicUrl = env().OWUI_PUBLIC_URL || null;

  const savedBanner = buildSavedBanner((await searchParams).saved);

  return (
    <div>
      <div className="fr-mb-4w">
        <h1>Bienvenue, {displayName}</h1>
        <p className="fr-text--lead">
          Mes Agents MirAI vous permet de créer et partager vos propres agents IA
          souverains en moins de 5 minutes, sans écrire une ligne de code.
        </p>
      </div>

      {savedBanner && (
        <div className="fr-alert fr-alert--success fr-mb-4w">
          <h3 className="fr-alert__title">{savedBanner.title}</h3>
          <p>{savedBanner.detail}</p>
        </div>
      )}

      <h2 className="fr-h3">Que souhaitez-vous faire&nbsp;?</h2>
      <div className="fr-grid-row fr-grid-row--gutters fr-mb-6w">
        <ActionTile
          href="/agents/new"
          icon="fr-icon-add-circle-line"
          title={agents.length === 0 ? 'Créer mon premier agent' : 'Créer un nouvel agent'}
          description="Un formulaire guidé en 4 étapes : identité, comportement, connaissances, test. L'IA vous aide à rédiger le prompt."
        />
        <ActionTile
          href="/catalog"
          icon="fr-icon-search-line"
          title="Explorer le catalogue"
          description="Parcourez les agents partagés par les autres directions. Vous pouvez les utiliser directement ou les dupliquer pour les personnaliser."
        />
        <ActionTile
          href="/agents/new?template=example"
          icon="fr-icon-lightbulb-line"
          title="Partir d'un exemple"
          description="Choisissez un modèle métier pré-configuré (préfecture, juridique, RH, communication) comme point de départ."
        />
      </div>

      <section className="fr-mb-4w">
        <h2 className="fr-h3">Mes agents ({agents.length})</h2>
        {agents.length === 0 ? (
          <div className="fr-notice fr-notice--info">
            <div className="fr-container">
              <div className="fr-notice__body">
                <p className="fr-notice__title">
                  Vous n&apos;avez pas encore créé d&apos;agent.
                </p>
                <p className="fr-notice__desc">
                  Commencez par définir ce que votre agent doit faire et à qui il
                  s&apos;adresse. L&apos;assistant de rédaction vous guidera à chaque étape.
                </p>
              </div>
            </div>
          </div>
        ) : (
          <div className="fr-grid-row fr-grid-row--gutters">
            {agents.map((a) => (
              <div key={a.id} className="fr-col-12 fr-col-md-6 fr-col-lg-4">
                <div
                  style={{
                    border: '1px solid var(--border-default-grey)',
                    borderRadius: '8px',
                    padding: '1.25rem',
                    display: 'flex',
                    flexDirection: 'column',
                    height: '100%',
                    minHeight: '320px',
                  }}
                >
                  {/* En-tete : titre (peut deborder sur 2 lignes) + badges */}
                  <h3
                    className="fr-h6 fr-mb-1w"
                    style={{ margin: 0, lineHeight: 1.3, minHeight: '2.6em' }}
                  >
                    {a.owuiModelId.replace(/^mirai-/, '').replace(/-[a-z0-9]{6,8}$/, '').replace(/-/g, ' ')}
                  </h3>
                  <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.5rem', marginBottom: '0.75rem' }}>
                    <StatusBadge status={a.status} />
                    <VisibilityBadge visibility={a.visibility} />
                    {a.category.length > 0 && a.category.map((cat) => (
                      <span key={cat} className="fr-badge fr-badge--sm fr-badge--purple-glycine">
                        {cat}
                      </span>
                    ))}
                  </div>
                  <p className="fr-text--xs fr-mb-2w" style={{ color: 'var(--text-mention-grey)' }}>
                    Version {a.version} · mis a jour le {new Date(a.updatedAt).toLocaleString('fr-FR')}
                  </p>

                  {/* Zone boutons alignee en bas */}
                  <div style={{ marginTop: 'auto', display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
                    {/* Bouton principal : MirAI Chat (experience complete avec outils) */}
                    {owuiPublicUrl && a.status !== 'draft' ? (
                      <a
                        href={`${owuiPublicUrl}/?models=${encodeURIComponent(a.owuiModelId)}`}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="fr-btn fr-btn--icon-left fr-icon-chat-3-line"
                        style={{ width: '100%', justifyContent: 'center' }}
                      >
                        Utiliser dans MirAI Chat
                      </a>
                    ) : (
                      <span
                        className="fr-btn fr-btn--icon-left fr-icon-chat-3-line"
                        style={{ width: '100%', justifyContent: 'center', opacity: 0.5, pointerEvents: 'none' }}
                        aria-disabled="true"
                      >
                        Publiez pour utiliser dans MirAI Chat
                      </span>
                    )}
                    <p className="fr-text--xs fr-mb-0" style={{ color: 'var(--text-mention-grey)', textAlign: 'center' }}>
                      Recherche web, base de connaissances, outils avances
                    </p>

                    {/* Bouton secondaire : test rapide local */}
                    <Link
                      href={`/agents/${a.id}/chat`}
                      className="fr-btn fr-btn--secondary fr-btn--sm fr-btn--icon-left fr-icon-question-answer-line"
                      style={{ width: '100%', justifyContent: 'center' }}
                    >
                      Utiliser rapidement ici
                    </Link>
                    <p className="fr-text--xs fr-mb-0" style={{ color: 'var(--text-mention-grey)', textAlign: 'center' }}>
                      Conversation simple, sans outils
                    </p>

                    {/* Lien modifier en bas a droite */}
                    <div style={{ display: 'flex', justifyContent: 'flex-end', marginTop: '0.25rem' }}>
                      <Link
                        href={`/agents/${a.id}/edit`}
                        className="fr-btn fr-btn--tertiary-no-outline fr-btn--sm fr-btn--icon-left fr-icon-edit-line"
                      >
                        Modifier
                      </Link>
                    </div>
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}
      </section>

      <OnboardingChat />
    </div>
  );
}

function buildSavedBanner(saved?: string) {
  if (saved === 'draft')
    return {
      title: 'Brouillon sauvegardé',
      detail: 'Votre agent est enregistré en brouillon. Vous pouvez l\'éditer à tout moment.',
    };
  if (saved === 'published')
    return {
      title: 'Agent publié dans votre espace',
      detail: 'Votre agent est visible dans votre liste personnelle. Vous pouvez le partager depuis sa fiche.',
    };
  if (saved === 'submitted')
    return {
      title: 'Agent soumis au catalogue',
      detail: 'Votre agent sera revu avant publication dans le catalogue ministériel.',
    };
  if (saved === 'updated')
    return {
      title: 'Agent mis à jour',
      detail: 'Les modifications ont été enregistrées. Une nouvelle version a été créée.',
    };
  return null;
}

function StatusBadge({ status }: { status: string }) {
  const map: Record<string, { label: string; cls: string }> = {
    draft: { label: 'Brouillon', cls: 'fr-badge--grey' },
    published: { label: 'Publié', cls: 'fr-badge--success' },
    submitted: { label: 'Soumis', cls: 'fr-badge--info' },
    validated: { label: 'Validé', cls: 'fr-badge--new' },
    archived: { label: 'Archivé', cls: 'fr-badge--warning' },
  };
  const entry = map[status] ?? { label: status, cls: '' };
  return <span className={`fr-badge fr-badge--sm ${entry.cls}`}>{entry.label}</span>;
}

function VisibilityBadge({ visibility }: { visibility: string }) {
  const map: Record<string, { label: string; cls: string }> = {
    private: { label: 'Prive', cls: 'fr-badge--yellow-tournesol' },
    community: { label: 'Communaute', cls: 'fr-badge--green-emeraude' },
    ministry: { label: 'Ministeriel', cls: 'fr-badge--blue-ecume' },
  };
  const entry = map[visibility] ?? { label: visibility, cls: '' };
  return <span className={`fr-badge fr-badge--sm ${entry.cls}`}>{entry.label}</span>;
}

function ActionTile({
  href,
  icon,
  title,
  description,
}: {
  href: string;
  icon: string;
  title: string;
  description: string;
}) {
  return (
    <div className="fr-col-12 fr-col-md-4">
      <div className="fr-tile fr-enlarge-link">
        <div className="fr-tile__body">
          <div className="fr-tile__content">
            <h3 className="fr-tile__title">
              <Link href={href} className="fr-tile__link">
                {title}
              </Link>
            </h3>
            <p className="fr-tile__desc">{description}</p>
          </div>
        </div>
        <div className="fr-tile__header">
          <div className="fr-tile__pictogram">
            <span className={`${icon} fr-icon--lg`} aria-hidden="true" />
          </div>
        </div>
      </div>
    </div>
  );
}
