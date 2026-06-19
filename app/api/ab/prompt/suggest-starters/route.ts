// BFF — génère une amorce (message d'accueil) + N exemples de prompts
// à partir du system prompt. Utilise Scaleway Generative APIs avec gpt-oss-120b.
// La réponse LLM est demandée en JSON strict pour être parseable côté client.

import { NextResponse } from 'next/server';
import { getServerSession } from 'next-auth';
import { authOptions } from '@/lib/auth';
import { scwChatCompletions, ScwLlmUnavailableError } from '@/lib/scw-llm-client';
import { rateLimit, LLM_RATE_LIMIT } from '@/lib/rate-limit';
import { inspectInput, logGuardEvent } from '@/lib/prompt-guard';

const SYSTEM_META_PROMPT = `Tu es un assistant qui aide à mettre en service un agent IA
ministériel. À partir du prompt système que l'utilisateur fournit, génère :

1. Une "amorce" : un message d'accueil court (moins de 300 caractères) qui sera affiché
   à l'utilisateur final lors du lancement de l'agent. L'amorce présente ce que fait
   l'agent et invite à poser une question. Ton formel, français administratif clair.

2. Une liste d'"exemples" : 4 exemples de prompts que l'utilisateur final pourrait
   taper. Ils servent de suggestions cliquables. Chaque exemple doit être :
   - une question ou demande concrète (pas un titre générique)
   - en français
   - de longueur 40-120 caractères
   - représentatif d'usages réalistes de l'agent

Retourne EXCLUSIVEMENT du JSON valide, sans préambule, sans balise, sans markdown,
respectant strictement ce schéma :
{
  "greeting": "string",
  "examples": ["string", "string", "string", "string"]
}`;

type StartersResponse = {
  greeting: string;
  examples: string[];
};

export async function POST(req: Request) {
  const session = await getServerSession(authOptions);
  if (!session) {
    return NextResponse.json({ error: 'unauthorized' }, { status: 401 });
  }
  if (!rateLimit(`starters:${session.user?.id ?? 'anon'}`, LLM_RATE_LIMIT)) {
    return NextResponse.json({ error: 'rate_limited' }, { status: 429 });
  }

  const body = (await req.json().catch(() => ({}))) as {
    prompt?: string;
    count?: number;
  };

  if (!body.prompt || body.prompt.trim().length < 20) {
    return NextResponse.json(
      {
        error: 'prompt_too_short',
        detail: 'Le prompt système doit faire au moins 20 caractères.',
      },
      { status: 400 },
    );
  }

  // Garde d'entrée : le prompt système soumis est fourni par l'utilisateur.
  const inGuard = inspectInput(body.prompt, 'system');
  if (inGuard.blocked) {
    logGuardEvent({
      route: 'prompt.suggest-starters',
      stage: 'input',
      userId: session.user?.id,
      role: 'system',
      signals: inGuard.signals,
    });
    return NextResponse.json({ error: 'blocked_input' }, { status: 422 });
  }

  const userMessage =
    `Voici le prompt système de l'agent :\n\n${body.prompt}\n\n` +
    `Génère l'amorce et ${body.count ?? 4} exemples de prompts.`;

  try {
    const completion = await scwChatCompletions({
      messages: [
        { role: 'system', content: SYSTEM_META_PROMPT },
        { role: 'user', content: userMessage },
      ],
      temperature: 0.8, // un peu de variété dans les exemples
      maxTokens: 2048,
    });

    const raw = completion.choices?.[0]?.message?.content?.trim() ?? '';
    const parsed = parseStartersJson(raw);
    if (!parsed) {
      console.error('suggest-starters parse_failed, raw output:', raw);
      return NextResponse.json(
        {
          error: 'parse_failed',
          detail: 'Le modèle n\'a pas renvoyé un JSON valide.',
        },
        { status: 502 },
      );
    }
    return NextResponse.json(parsed);
  } catch (err) {
    if (err instanceof ScwLlmUnavailableError) {
      return NextResponse.json(
        { error: 'llm_not_configured', detail: err.message },
        { status: 501 },
      );
    }
    console.error('suggest-starters upstream_failure', err);
    return NextResponse.json({ error: 'upstream_failure' }, { status: 502 });
  }
}

/** Parse le JSON renvoyé par le modèle, tolérant à un éventuel wrapping en
 *  bloc markdown ```json ... ``` que certains modèles ajoutent malgré la
 *  consigne de n'émettre que du JSON. */
function parseStartersJson(raw: string): StartersResponse | null {
  let text = raw.trim();
  // Retire un éventuel fencing markdown
  const fenced = text.match(/```(?:json)?\s*([\s\S]*?)\s*```/);
  if (fenced) text = fenced[1].trim();
  try {
    const obj = JSON.parse(text) as Partial<StartersResponse>;
    if (
      typeof obj.greeting === 'string' &&
      Array.isArray(obj.examples) &&
      obj.examples.every((e) => typeof e === 'string')
    ) {
      return {
        greeting: obj.greeting.trim(),
        examples: obj.examples.map((e) => e.trim()).filter((e) => e.length > 0),
      };
    }
  } catch {
    // fall through
  }
  return null;
}
