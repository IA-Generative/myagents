// BFF — Assistant conversationnel d'onboarding.
// Guide l'utilisateur par des questions pour construire les parametres
// de son agent (role, public, ton, contraintes, nom, categorie).
// Utilise mistral-small (rapide, adapte au dialogue court).
// A la fin du dialogue, renvoie un JSON structure avec les champs du wizard.

import { NextResponse } from 'next/server';
import { getServerSession } from 'next-auth';
import { authOptions } from '@/lib/auth';
import { scwChatCompletions } from '@/lib/scw-llm-client';
import { rateLimit, LLM_RATE_LIMIT } from '@/lib/rate-limit';
import {
  inspectInput,
  inspectOutput,
  judgeOutput,
  DEFAULT_GUARD_CONFIG,
  DEFAULT_OUTPUT_POLICY_GOAL,
  BLOCK_MESSAGE_USER_INPUT,
  BLOCK_MESSAGE_OUTPUT,
} from '@/lib/prompt-guard';
import { recordGuardEvent } from '@/lib/guard-audit';

const SYSTEM_PROMPT = `Tu es l'assistant de creation d'agents IA du Ministere de l'Interieur.
Tu guides un agent du ministere (utilisateur non technique) pour creer son propre agent IA.

TON ROLE : poser des questions une par une, de maniere simple et bienveillante, pour
recueillir les informations necessaires a la creation de l'agent.

DEROULEMENT (pose UNE SEULE question a la fois, attends la reponse avant de continuer) :
1. "Quel est le role principal de votre agent ?" (ex: rediger des notes, resumer des reunions, aider a l'accueil)
2. "A qui s'adresse-t-il ?" (ex: agents de prefecture, cadres, tout le monde)
3. "Quel ton doit-il adopter ?" (formel / neutre / accessible)
4. "Y a-t-il des contraintes specifiques ?" (ex: citer les textes, limiter a 500 mots, ne pas inventer)
5. "Donnez un exemple de question type qu'on poserait a votre agent"
6. "Comment souhaitez-vous appeler votre agent ?" (un nom court et parlant)

Quand tu as recueilli TOUTES les reponses (apres la question 6), genere un JSON
UNIQUEMENT (sans texte avant ni apres) avec ce format exact :
\`\`\`json
{
  "ready": true,
  "name": "Nom de l'agent",
  "description": "Description courte (max 280 chars)",
  "category": "redaction|juridique|rh|securite|immigration|prefecture|it|communication|transverse",
  "systemPrompt": "Le prompt systeme complet, structure, avec role/public/ton/contraintes",
  "greeting": "Message d'accueil de l'agent (max 300 chars)",
  "examples": ["exemple 1", "exemple 2", "exemple 3", "exemple 4"]
}
\`\`\`

REGLES :
- Reponds TOUJOURS en francais
- Sois concis (2-3 phrases max par message)
- Si l'utilisateur repond de maniere vague, reformule pour preciser
- Ne saute PAS d'etape — pose chaque question dans l'ordre
- Le JSON final ne doit etre emis QU'APRES avoir pose les 6 questions
- Commence par te presenter brievement et poser la question 1`;

export async function POST(req: Request) {
  const session = await getServerSession(authOptions);
  if (!session) {
    return NextResponse.json({ error: 'unauthorized' }, { status: 401 });
  }
  if (!rateLimit(`onboarding:${session.user?.id ?? 'anon'}`, LLM_RATE_LIMIT)) {
    return NextResponse.json({ error: 'rate_limited' }, { status: 429 });
  }

  const body = (await req.json().catch(() => ({}))) as {
    messages?: Array<{ role: string; content: string }>;
  };

  if (!Array.isArray(body.messages) || body.messages.length === 0) {
    return NextResponse.json({ error: 'messages_required' }, { status: 400 });
  }

  // Whitelist des roles : seuls user/assistant venant du client sont admis.
  // Empeche l'injection d'un message role:"system" qui detournerait le
  // deroulement de l'onboarding. Borne aussi le nombre de tours.
  const clientMessages = body.messages
    .filter(
      (m): m is { role: 'user' | 'assistant'; content: string } =>
        (m?.role === 'user' || m?.role === 'assistant') &&
        typeof m?.content === 'string',
    )
    .slice(-40);

  if (clientMessages.length === 0) {
    return NextResponse.json({ error: 'messages_required' }, { status: 400 });
  }

  // Garde d'entrée : le dialogue d'onboarding produit le systemPrompt qui sera
  // ensuite publié. On inspecte le dernier message utilisateur pour bloquer une
  // injection avant qu'elle ne contamine la config générée.
  const lastUser = clientMessages[clientMessages.length - 1];
  // Anomalie en posture « audit » (journalise sans bloquer) + heuristiques bloquantes.
  const inGuard = inspectInput(lastUser.content, 'user', { anomaly: DEFAULT_GUARD_CONFIG.anomaly });
  if (inGuard.signals.some((s) => s.complied)) {
    await recordGuardEvent({
      route: 'onboarding.chat',
      stage: 'input',
      userId: session.user?.id,
      role: 'user',
      signals: inGuard.signals,
    });
  }
  if (inGuard.blocked) {
    return NextResponse.json(
      { error: 'blocked_input', message: BLOCK_MESSAGE_USER_INPUT },
      { status: 422 },
    );
  }

  try {
    const completion = await scwChatCompletions({
      messages: [
        { role: 'system', content: SYSTEM_PROMPT },
        ...clientMessages,
      ],
      // mistral-small : rapide et bon pour le dialogue guide
      model: 'mistral-small-3.2-24b-instruct-2506',
      temperature: 0.6,
      maxTokens: 1024,
    });

    const content = completion.choices?.[0]?.message?.content?.trim() ?? '';

    // Garde de sortie : la réponse (et la config d'agent qu'elle peut contenir)
    // est inspectée avant d'être renvoyée — un modèle détourné ne doit pas
    // glisser un keylogger ou de la manipulation dans le system prompt généré.
    const outHeuristics = inspectOutput(content);
    const judge = await judgeOutput({ goal: DEFAULT_OUTPUT_POLICY_GOAL, response: content });
    const outSignals = [
      ...outHeuristics.signals,
      { source: 'judge' as const, complied: judge.complied, reason: judge.reason, severity: 'medium' as const },
    ];
    if (outSignals.some((s) => s.complied)) {
      await recordGuardEvent({
        route: 'onboarding.chat',
        stage: 'output',
        userId: session.user?.id,
        role: 'user',
        signals: outSignals,
      });
      return NextResponse.json(
        { error: 'blocked_output', message: BLOCK_MESSAGE_OUTPUT },
        { status: 422 },
      );
    }

    // Detecte si la reponse contient le JSON final
    let agentConfig = null;
    const jsonMatch = content.match(/```json\s*([\s\S]*?)\s*```/);
    if (jsonMatch) {
      try {
        const parsed = JSON.parse(jsonMatch[1]);
        if (parsed.ready === true && parsed.name && parsed.systemPrompt) {
          agentConfig = parsed;
        }
      } catch {
        // pas un JSON valide, on continue le dialogue
      }
    }

    return NextResponse.json({
      message: content,
      agentConfig,
    });
  } catch (err) {
    console.error('onboarding upstream_failure', err);
    return NextResponse.json({ error: 'upstream_failure' }, { status: 502 });
  }
}
