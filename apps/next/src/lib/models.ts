// Catalogue curated des modèles LLM souverains disponibles sur l'instance
// Scaleway Generative APIs du ministère (celle qu'utilise owuicore-main).
// Liste figée à la main à partir de GET ${SCW_LLM_BASE_URL}/models, filtrée
// aux modèles pertinents pour la rédaction / raisonnement administratif
// (on masque les modèles audio, embedding et les pures specialized code).
//
// Chaque modèle expose :
//   - id        : nom technique à envoyer dans le champ "model" de l'API
//   - label     : nom affiché dans l'UI (plus lisible)
//   - family    : éditeur / famille
//   - tier      : léger / équilibré / raisonnement / puissant / spécialisé
//   - strengths : ce pour quoi il est bon
//   - tradeoffs : limites / ce à quoi il n'est pas adapté
//   - cost      : indication relative de coût tokens (1=bas, 5=élevé)
//   - latency   : indication relative de vitesse (1=lent, 5=rapide)

export type ModelTier = 'light' | 'balanced' | 'reasoning' | 'power' | 'multimodal';

export type ModelProfile = {
  id: string;
  label: string;
  family: string;
  tier: ModelTier;
  shortPitch: string;
  strengths: string[];
  tradeoffs: string[];
  cost: 1 | 2 | 3 | 4 | 5;
  latency: 1 | 2 | 3 | 4 | 5;
  recommendedFor: string[];
};

export const AVAILABLE_MODELS: ModelProfile[] = [
  {
    id: 'mistral-small-3.2-24b-instruct-2506',
    label: 'Mistral Small 3.2 (24B)',
    family: 'Mistral AI',
    tier: 'light',
    shortPitch: 'Rapide et économique, idéal pour la rédaction administrative courante.',
    strengths: [
      'Excellente vitesse de réponse',
      'Maîtrise du français administratif',
      'Faible consommation de tokens → bon marché',
      'Parfait pour des tâches de reformulation, résumé, correction',
    ],
    tradeoffs: [
      'Moins pertinent sur du raisonnement multi-étapes complexe',
      'Peut hallucinar sur des textes juridiques pointus',
    ],
    cost: 2,
    latency: 5,
    recommendedFor: [
      'Notes de service, courriers formels, reformulations',
      'Résumés de documents courts',
      'Agents FAQ, assistants de guichet',
    ],
  },
  {
    id: 'gemma-4-26b-a4b-it',
    label: 'Gemma 4 (26B, MoE 4B actif)',
    family: 'Google',
    tier: 'balanced',
    shortPitch: 'Généraliste Google récent, architecture MoE efficace (rapide pour sa taille).',
    strengths: [
      'Bon rapport qualité / vitesse',
      'MoE : 26B paramètres, ~4B activés par token → économe',
      'Capacités générales récentes, multilingue correct',
      'Bon défaut quand Mistral Small est un peu juste',
    ],
    tradeoffs: [
      'Moins fort que les très grands modèles sur le raisonnement complexe',
      'Français parfois moins idiomatique que Mistral',
    ],
    cost: 2,
    latency: 4,
    recommendedFor: [
      'Tâches généralistes quotidiennes',
      'Reformulation, résumé, questions-réponses',
      'Agents polyvalents légers',
    ],
  },
  {
    id: 'llama-3.3-70b-instruct',
    label: 'Llama 3.3 (70B)',
    family: 'Meta',
    tier: 'balanced',
    shortPitch: 'Généraliste robuste, bon compromis qualité / vitesse.',
    strengths: [
      'Très bonne qualité générale sur tout type de texte',
      'Français correct sans biais marqué',
      'Suivi d\'instructions fiable',
      'Réponses structurées et cohérentes',
    ],
    tradeoffs: [
      'Plus lent qu\'un modèle 24B',
      'Consommation de tokens modérée',
    ],
    cost: 3,
    latency: 3,
    recommendedFor: [
      'Rédaction de rapports, synthèses de dossiers',
      'Analyse de texte à longueur moyenne',
      'Agents polyvalents qui mélangent plusieurs tâches',
    ],
  },
  {
    id: 'qwen3.6-35b-a3b',
    label: 'Qwen3.6 (35B, MoE 3B actif)',
    family: 'Alibaba',
    tier: 'balanced',
    shortPitch: 'Généraliste Qwen récent, MoE économe, suivi d\'instructions fiable.',
    strengths: [
      'Architecture MoE efficiente (35B paramètres, ~3B activés)',
      'Bonnes performances générales et multilingues',
      'Suivi d\'instructions fiable',
      'Gère les contextes longs',
    ],
    tradeoffs: [
      'Français administratif un peu moins naturel que Mistral',
      'Peut être verbeux',
    ],
    cost: 3,
    latency: 3,
    recommendedFor: [
      'Agents polyvalents, alternative récente à Llama 3.3',
      'Analyse et synthèse de documents',
      'Tâches mêlant plusieurs langues',
    ],
  },
  {
    id: 'gpt-oss-120b',
    label: 'GPT-OSS 120B (raisonnement)',
    family: 'OpenAI (open-source)',
    tier: 'reasoning',
    shortPitch: 'Modèle de raisonnement avancé, génère un plan interne avant de répondre.',
    strengths: [
      'Raisonnement multi-étapes explicite',
      'Excellent pour les analyses juridiques, les études de cas',
      'Plans d\'action structurés et justifiés',
      'Meilleure précision factuelle que les modèles non-raisonnement',
    ],
    tradeoffs: [
      'Consomme davantage de tokens (reasoning overhead)',
      'Latence plus élevée — prévoir quelques secondes d\'attente',
      'Sur-dimensionné pour des tâches simples de reformulation',
    ],
    cost: 4,
    latency: 2,
    recommendedFor: [
      'Analyses juridiques (CESEDA, Code pénal, circulaires)',
      'Arbres de décision, diagnostics administratifs',
      'Agents qui doivent justifier leurs recommandations',
    ],
  },
  {
    id: 'mistral-medium-3.5-128b',
    label: 'Mistral Medium 3.5 (128B)',
    family: 'Mistral AI',
    tier: 'power',
    shortPitch: 'Modèle haut de gamme de Mistral — excellent en français soutenu et en style contraint.',
    strengths: [
      'Très bonne qualité rédactionnelle en français',
      'Suivi d\'instructions fin et nuancé (ton, format, style)',
      'Bon compromis qualité / latence pour un grand modèle',
      'Adapté aux tâches exigeantes (synthèse soignée, créativité)',
    ],
    tradeoffs: [
      'Consommation de tokens élevée',
      'Plus lent que les modèles légers',
    ],
    cost: 4,
    latency: 2,
    recommendedFor: [
      'Rédaction soignée, contraintes de style ou de format',
      'Notes à forte visibilité, synthèses de qualité',
      'Agents généralistes premium',
    ],
  },
  {
    id: 'qwen3-235b-a22b-instruct-2507',
    label: 'Qwen3 235B (MoE 22B actif)',
    family: 'Alibaba',
    tier: 'power',
    shortPitch: 'Très puissant, architecture MoE — grande capacité à coût maîtrisé.',
    strengths: [
      'Architecture Mixture-of-Experts : 235B paramètres mais seulement 22B activés par token',
      'Excellente connaissance générale et multilingue',
      'Maîtrise des contextes longs',
      'Qualité proche des modèles frontier',
    ],
    tradeoffs: [
      'Latence sensible sur prompts longs',
      'Consommation tokens élevée',
    ],
    cost: 4,
    latency: 2,
    recommendedFor: [
      'Synthèses de dossiers complexes multi-documents',
      'Agents d\'aide à la décision stratégique',
      'Traductions techniques ou administratives précises',
    ],
  },
  {
    id: 'qwen3.5-397b-a17b',
    label: 'Qwen3.5 397B (le plus puissant)',
    family: 'Alibaba',
    tier: 'power',
    shortPitch: 'Le modèle le plus puissant disponible — pour les cas vraiment exigeants.',
    strengths: [
      'Architecture MoE massive (397B paramètres, 17B actifs)',
      'Qualité frontier — rivalise avec les meilleurs modèles propriétaires',
      'Très bonne compréhension fine du français juridique',
      'Peut gérer des contextes extrêmement longs',
    ],
    tradeoffs: [
      'Coût tokens le plus élevé de la liste',
      'Latence la plus haute',
      'Overkill pour la majorité des cas d\'usage quotidiens',
    ],
    cost: 5,
    latency: 1,
    recommendedFor: [
      'Analyses doctrinales, synthèses de jurisprudence',
      'Agents experts pour juristes / cadres dirigeants',
      'Rapports stratégiques à forte valeur',
    ],
  },
  {
    id: 'pixtral-12b-2409',
    label: 'Pixtral 12B (multimodal image)',
    family: 'Mistral AI',
    tier: 'multimodal',
    shortPitch: 'Accepte du texte ET des images — lecture de documents scannés, plans, formulaires.',
    strengths: [
      'Lit les images (PDF scannés, formulaires remplis, photos)',
      'Extraction structurée depuis des documents visuels',
      'Taille modeste (12B) → rapide',
    ],
    tradeoffs: [
      'Moins performant en pure rédaction que Mistral Small',
      'Qualité OCR variable sur manuscrits difficiles',
    ],
    cost: 2,
    latency: 4,
    recommendedFor: [
      'Agents qui ingèrent des formulaires scannés',
      'Lecture de plans, schémas, tableaux',
      'Assistants d\'accueil traitant des pièces justificatives',
    ],
  },
];

export function getModelById(id: string): ModelProfile | undefined {
  return AVAILABLE_MODELS.find((m) => m.id === id);
}

// Modèles non conversationnels à exclure du choix d'agent (embeddings, audio,
// rerank…) : ils apparaissent dans GET /models mais ne savent pas dialoguer.
const NON_CHAT_RE = /embedding|bge|rerank|whisper|voxtral|moderation|\btts\b|\bstt\b/i;

export function isSelectableModel(id: string): boolean {
  return !NON_CHAT_RE.test(id);
}

const FAMILY_BY_OWNER: Record<string, string> = {
  mistral: 'Mistral AI',
  meta: 'Meta',
  google: 'Google',
  qwen: 'Alibaba',
  alibaba: 'Alibaba',
  openai: 'OpenAI (open-source)',
  deepseek: 'DeepSeek',
  hcompany: 'H Company',
  baai: 'BAAI',
};

function prettyFamily(owner?: string): string {
  if (!owner) return 'Inconnu';
  return FAMILY_BY_OWNER[owner.toLowerCase()] ?? owner;
}

// Profil minimal pour un modèle live qui n'a pas (encore) de fiche curated.
function inferProfile(id: string, ownedBy?: string): ModelProfile {
  return {
    id,
    label: id,
    family: prettyFamily(ownedBy),
    tier: 'balanced',
    shortPitch:
      "Modèle disponible sur l'instance souveraine. Fiche détaillée non encore renseignée.",
    strengths: [],
    tradeoffs: [],
    cost: 3,
    latency: 3,
    recommendedFor: [],
  };
}

// Fusionne la liste live (ce que Scaleway sert réellement) avec les fiches
// curated. Les modèles curated encore disponibles gardent leur ordre et leur
// description ; les nouveaux modèles live sont ajoutés à la suite avec un
// profil minimal ; les modèles curated disparus de l'API ne sont PAS renvoyés
// (évite de proposer un modèle qui renverrait une erreur upstream).
export function mergeLiveModels(
  live: Array<{ id: string; owned_by?: string }>,
): ModelProfile[] {
  const usable = live.filter((m) => isSelectableModel(m.id));
  const liveIds = new Set(usable.map((m) => m.id));
  const curated = AVAILABLE_MODELS.filter((m) => liveIds.has(m.id));
  const curatedIds = new Set(curated.map((m) => m.id));
  const extras = usable
    .filter((m) => !curatedIds.has(m.id))
    .map((m) => inferProfile(m.id, m.owned_by));
  return [...curated, ...extras];
}

export const DEFAULT_MODEL_ID = 'mistral-small-3.2-24b-instruct-2506';

export const TIER_LABELS: Record<ModelTier, string> = {
  light: 'Léger',
  balanced: 'Équilibré',
  reasoning: 'Raisonnement',
  power: 'Puissant',
  multimodal: 'Multimodal',
};

export const TIER_COLORS: Record<ModelTier, string> = {
  // Couleurs DSFR (fr-badge--*)
  light: 'fr-badge--green-emeraude',
  balanced: 'fr-badge--blue-ecume',
  reasoning: 'fr-badge--purple-glycine',
  power: 'fr-badge--pink-tuile',
  multimodal: 'fr-badge--orange-terre-battue',
};
