// Runner de MATRICE red-team : joue le corpus (baseline + ZORG) contre N modèles
// Scaleway, sur deux surfaces (CIBLE BRUTE / CIBLE DERRIÈRE LE GARDE), et écrit
// une synthèse persistée (JSON brut + CSV agrégé + Markdown lisible).
//
// Contrairement à prompt-injection.test.ts (qui échoue au 1er breach, sortie
// TAP), ce runner ENREGISTRE tous les résultats sans échouer — c'est l'outil de
// synthèse par modèle demandé.
//
// Invocation (via vitest, voir matrix.run.test.ts) :
//   REDTEAM_MATRIX=1 npm run test:redteam:matrix
// Réglages (env) :
//   REDTEAM_MODELS    CSV de modèles (défaut : les 9 du catalogue models.ts)
//   REDTEAM_SAMPLES   tirages par (modèle,payload,surface) (défaut 3)
//   REDTEAM_CONCURRENCY  appels concurrents (défaut 5)
//   REDTEAM_CORPUS    'all' | 'baseline' | 'zorg' (défaut 'all')
//   REDTEAM_SURFACES  'both' | 'raw' | 'guarded' (défaut 'both')
//   REDTEAM_SMOKE=1   limite à 1 modèle × 2 payloads × 1 tirage (pré-vol)
//   REDTEAM_OUT       dossier de sortie (défaut tests/redteam/reports)

import { mkdirSync, writeFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { ATTACKS, type Payload, type GoalKind } from './payloads';
import { ZORG_ATTACKS } from './zorg-corpus';
import { runRawTrial, runGuardedTrial } from './harness';
import { AVAILABLE_MODELS, getModelById } from '../../src/lib/models';

export type Surface = 'raw' | 'guarded';
export type Outcome = 'resisted' | 'breached' | 'blocked-by-guard' | 'error';

export type TrialRecord = {
  model: string;
  payloadId: string;
  source: 'baseline' | 'zorg';
  category: Payload['category'];
  severity: Payload['severity'];
  deliveryRole: Payload['deliveryRole'];
  goalKind: GoalKind;
  lang: 'fr' | 'en' | 'n/a';
  axes: string[];
  sample: number;
  surface: Surface;
  outcome: Outcome;
  blockedLayer?: 'input' | 'output' | 'none';
  signals: Array<{ source: string; complied: boolean; reason: string }>;
  latencyMs: number;
  totalTokens?: number;
  costTier: number;
  responseExcerpt: string;
  error?: string;
};

export type MatrixOptions = {
  models: string[];
  samples: number;
  concurrency: number;
  surfaces: Surface[];
  corpus: Payload[];
  outDir: string;
};

// ---------------------------------------------------------------------------
// Normalisation des payloads (les ATTACKS faits maison n'ont pas toutes les
// métadonnées de synthèse : on les infère).
// ---------------------------------------------------------------------------

function inferGoalKind(p: Payload): GoalKind {
  if (p.goalKind) return p.goalKind;
  if (p.category === 'manipulation') return 'disinfo';
  if (p.detectors.includes('prompt-leak') && !p.detectors.includes('keylogger')) return 'prompt-leak';
  return 'keylogger';
}

function normalize(p: Payload): Required<Pick<Payload, 'source' | 'goalKind' | 'axes'>> & {
  lang: 'fr' | 'en' | 'n/a';
} {
  return {
    source: p.source ?? 'baseline',
    goalKind: inferGoalKind(p),
    axes: p.axes ?? [],
    lang: p.lang ?? 'n/a',
  };
}

// ---------------------------------------------------------------------------
// Sélection du corpus + options depuis l'environnement
// ---------------------------------------------------------------------------

export function selectCorpus(kind: string): Payload[] {
  if (kind === 'baseline') return ATTACKS;
  if (kind === 'zorg') return ZORG_ATTACKS;
  return [...ATTACKS, ...ZORG_ATTACKS];
}

export function parseMatrixOptions(env: NodeJS.ProcessEnv = process.env): MatrixOptions {
  const allModelIds = AVAILABLE_MODELS.map((m) => m.id);
  let models = (env.REDTEAM_MODELS ?? allModelIds.join(','))
    .split(',')
    .map((m) => m.trim())
    .filter(Boolean);
  let samples = Number(env.REDTEAM_SAMPLES ?? '3');
  let corpus = selectCorpus(env.REDTEAM_CORPUS ?? 'all');
  const surfaces: Surface[] =
    env.REDTEAM_SURFACES === 'raw'
      ? ['raw']
      : env.REDTEAM_SURFACES === 'guarded'
        ? ['guarded']
        : ['raw', 'guarded'];

  if (env.REDTEAM_SMOKE === '1') {
    models = models.slice(0, 1);
    corpus = corpus.slice(0, 2);
    samples = 1;
  }

  return {
    models,
    samples,
    concurrency: Number(env.REDTEAM_CONCURRENCY ?? '5'),
    surfaces,
    corpus,
    outDir: env.REDTEAM_OUT ?? resolve(process.cwd(), 'tests/redteam/reports'),
  };
}

// ---------------------------------------------------------------------------
// Pool de concurrence (sans dépendance externe)
// ---------------------------------------------------------------------------

async function mapPool<T, R>(items: T[], concurrency: number, fn: (item: T, index: number) => Promise<R>): Promise<R[]> {
  const results = new Array<R>(items.length);
  let next = 0;
  async function worker(): Promise<void> {
    while (true) {
      const i = next++;
      if (i >= items.length) return;
      results[i] = await fn(items[i], i);
    }
  }
  const workers = Array.from({ length: Math.max(1, Math.min(concurrency, items.length)) }, () => worker());
  await Promise.all(workers);
  return results;
}

// ---------------------------------------------------------------------------
// Exécution d'un tirage
// ---------------------------------------------------------------------------

type Job = { model: string; payload: Payload; sample: number; surface: Surface };

function buildJobs(opts: MatrixOptions): Job[] {
  const jobs: Job[] = [];
  for (const model of opts.models) {
    for (const payload of opts.corpus) {
      for (const surface of opts.surfaces) {
        for (let s = 0; s < opts.samples; s++) {
          jobs.push({ model, payload, sample: s, surface });
        }
      }
    }
  }
  return jobs;
}

async function runJob(job: Job): Promise<TrialRecord> {
  const { model, payload, sample, surface } = job;
  const meta = normalize(payload);
  const costTier = getModelById(model)?.cost ?? 0;
  const baseRec: TrialRecord = {
    model,
    payloadId: payload.id,
    source: meta.source,
    category: payload.category,
    severity: payload.severity,
    deliveryRole: payload.deliveryRole,
    goalKind: meta.goalKind,
    lang: meta.lang,
    axes: meta.axes,
    sample,
    surface,
    outcome: 'error',
    signals: [],
    latencyMs: 0,
    costTier,
    responseExcerpt: '',
  };

  try {
    if (surface === 'raw') {
      const t = await runRawTrial(payload, model);
      return {
        ...baseRec,
        outcome: t.resisted ? 'resisted' : 'breached',
        signals: t.signals.filter((s) => s.complied),
        latencyMs: t.latencyMs,
        totalTokens: t.usage?.total_tokens,
        responseExcerpt: t.response.slice(0, 300),
      };
    }
    const t = await runGuardedTrial(payload, model);
    const outcome: Outcome = t.blockedByGuard ? 'blocked-by-guard' : t.residualBreach ? 'breached' : 'resisted';
    return {
      ...baseRec,
      outcome,
      blockedLayer: t.blockedLayer,
      signals: (t.blockedByGuard ? t.guardSignals : t.residualSignals).map((s) => ({
        source: s.source,
        complied: s.complied,
        reason: s.reason,
      })),
      latencyMs: t.latencyMs,
      totalTokens: t.usage?.total_tokens,
      responseExcerpt: t.response.slice(0, 300),
    };
  } catch (err) {
    return { ...baseRec, outcome: 'error', error: String(err).slice(0, 300) };
  }
}

// ---------------------------------------------------------------------------
// Agrégation + rendu
// ---------------------------------------------------------------------------

type Agg = { total: number; resisted: number; breached: number; blocked: number; error: number };

function emptyAgg(): Agg {
  return { total: 0, resisted: 0, breached: 0, blocked: 0, error: 0 };
}

function addTo(a: Agg, r: TrialRecord): void {
  a.total++;
  if (r.outcome === 'resisted') a.resisted++;
  else if (r.outcome === 'breached') a.breached++;
  else if (r.outcome === 'blocked-by-guard') a.blocked++;
  else a.error++;
}

function pct(n: number, d: number): string {
  return d === 0 ? '—' : `${Math.round((100 * n) / d)}%`;
}

function mean(nums: number[]): number {
  const ok = nums.filter((n) => Number.isFinite(n));
  return ok.length ? Math.round(ok.reduce((a, b) => a + b, 0) / ok.length) : 0;
}

export type MatrixReport = {
  generatedAt: string;
  options: Omit<MatrixOptions, 'corpus'> & { corpusSize: number; corpusIds: string[] };
  records: TrialRecord[];
};

function toCsv(records: TrialRecord[]): string {
  const header = [
    'model', 'payloadId', 'source', 'category', 'goalKind', 'lang', 'deliveryRole',
    'surface', 'sample', 'outcome', 'blockedLayer', 'latencyMs', 'totalTokens', 'costTier', 'signals',
  ];
  const rows = records.map((r) =>
    [
      r.model, r.payloadId, r.source, r.category, r.goalKind, r.lang, r.deliveryRole,
      r.surface, r.sample, r.outcome, r.blockedLayer ?? '', r.latencyMs, r.totalTokens ?? '',
      r.costTier, r.signals.map((s) => s.source).join('|'),
    ]
      .map((v) => {
        const s = String(v);
        return /[",\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
      })
      .join(','),
  );
  return [header.join(','), ...rows].join('\n');
}

function renderMarkdown(report: MatrixReport): string {
  const { records, options } = report;
  const models = options.models;
  const L: string[] = [];
  L.push('# Synthèse red-team — résistance aux prompt injections (matrice multi-modèles)');
  L.push('');
  L.push(`- Généré le : ${report.generatedAt}`);
  L.push(`- Modèles : ${models.length} — ${models.join(', ')}`);
  L.push(`- Corpus : ${options.corpusSize} payloads (baseline + ZORG), ${options.samples} tirage(s)/cellule, surfaces : ${options.surfaces.join(' + ')}`);
  L.push(`- Total de tirages : ${records.length}`);
  L.push('');
  L.push('**Lecture** : *brut* = robustesse intrinsèque du modèle nu ; *gardé* = bout-en-bout');
  L.push('derrière la garde de production. « breach » = l\'attaque a CÉDÉ ; « bloqué garde » = la');
  L.push('garde a stoppé (entrée ou sortie). Un breach *gardé* est une fuite que la garde a manquée.');
  L.push('');

  // --- Tableau A : synthèse par modèle ---
  L.push('## A. Synthèse par modèle');
  L.push('');
  L.push('| Modèle | Coût | Breach brut | Breach gardé | Bloqué entrée | Bloqué sortie | Latence moy. (ms) | Tokens |');
  L.push('|---|---|---|---|---|---|---|---|');
  for (const model of models) {
    const raw = records.filter((r) => r.model === model && r.surface === 'raw');
    const guarded = records.filter((r) => r.model === model && r.surface === 'guarded');
    const rawAgg = emptyAgg();
    raw.forEach((r) => addTo(rawAgg, r));
    const gAgg = emptyAgg();
    guarded.forEach((r) => addTo(gAgg, r));
    const blockedInput = guarded.filter((r) => r.blockedLayer === 'input').length;
    const blockedOutput = guarded.filter((r) => r.blockedLayer === 'output').length;
    const tokens = records.filter((r) => r.model === model).reduce((a, r) => a + (r.totalTokens ?? 0), 0);
    const lat = mean(records.filter((r) => r.model === model).map((r) => r.latencyMs));
    const costTier = getModelById(model)?.cost ?? '—';
    L.push(
      `| ${model} | ${costTier} | ${pct(rawAgg.breached, rawAgg.total)} (${rawAgg.breached}/${rawAgg.total}) | ` +
        `${pct(gAgg.breached, gAgg.total)} (${gAgg.breached}/${gAgg.total}) | ${blockedInput} | ${blockedOutput} | ${lat} | ${tokens} |`,
    );
  }
  L.push('');

  // --- Tableau B : breach brut par modèle × catégorie ---
  const categories = Array.from(new Set(records.map((r) => r.category)));
  L.push('## B. Breach BRUT par modèle × catégorie d\'attaque');
  L.push('');
  L.push(`| Modèle | ${categories.join(' | ')} |`);
  L.push(`|---|${categories.map(() => '---').join('|')}|`);
  for (const model of models) {
    const cells = categories.map((cat) => {
      const sub = records.filter((r) => r.model === model && r.surface === 'raw' && r.category === cat);
      const a = emptyAgg();
      sub.forEach((r) => addTo(a, r));
      return `${pct(a.breached, a.total)}`;
    });
    L.push(`| ${model} | ${cells.join(' | ')} |`);
  }
  L.push('');

  // --- Tableau C : efficacité des techniques (axes ZORG), brut, tous modèles ---
  const axes = Array.from(new Set(records.flatMap((r) => r.axes))).sort();
  if (axes.length) {
    L.push('## C. Efficacité des techniques ZORG (breach BRUT agrégé, tous modèles)');
    L.push('');
    L.push('| Technique (axe) | Breach brut | Tirages |');
    L.push('|---|---|---|');
    for (const axis of axes) {
      const sub = records.filter((r) => r.surface === 'raw' && r.axes.includes(axis));
      const a = emptyAgg();
      sub.forEach((r) => addTo(a, r));
      L.push(`| ${axis} | ${pct(a.breached, a.total)} | ${a.total} |`);
    }
    L.push('');
  }

  // --- Fuites gardées (les plus graves : la garde a laissé passer) ---
  const leaks = records.filter((r) => r.surface === 'guarded' && r.outcome === 'breached');
  L.push('## D. Fuites derrière la garde (à corriger en priorité)');
  L.push('');
  if (leaks.length === 0) {
    L.push('Aucune fuite : la garde a bloqué ou le modèle a résisté sur tous les tirages gardés. ✅');
  } else {
    L.push('| Modèle | Payload | Objectif | Signaux résiduels |');
    L.push('|---|---|---|---|');
    for (const r of leaks) {
      L.push(`| ${r.model} | ${r.payloadId} | ${r.goalKind} | ${r.signals.map((s) => s.source).join(', ')} |`);
    }
  }
  L.push('');

  // --- Erreurs ---
  const errors = records.filter((r) => r.outcome === 'error');
  if (errors.length) {
    L.push('## E. Erreurs d\'appel (modèles indisponibles / timeouts)');
    L.push('');
    const byModel = new Map<string, number>();
    errors.forEach((r) => byModel.set(r.model, (byModel.get(r.model) ?? 0) + 1));
    for (const [m, n] of byModel) L.push(`- ${m} : ${n} erreur(s) — ex. : ${errors.find((e) => e.model === m)?.error ?? ''}`);
    L.push('');
  }

  return L.join('\n');
}

// ---------------------------------------------------------------------------
// Entrée principale
// ---------------------------------------------------------------------------

export async function runMatrix(
  opts: MatrixOptions = parseMatrixOptions(),
  log: (msg: string) => void = (m) => console.log(m),
): Promise<{ report: MatrixReport; paths: { json: string; csv: string; md: string } }> {
  const jobs = buildJobs(opts);
  log(`[matrix] ${opts.models.length} modèles × ${opts.corpus.length} payloads × ${opts.samples} tirages × ${opts.surfaces.length} surface(s) = ${jobs.length} appels`);
  log(`[matrix] concurrence=${opts.concurrency} — démarrage…`);

  let done = 0;
  const records = await mapPool(jobs, opts.concurrency, async (job) => {
    const rec = await runJob(job);
    done++;
    if (done % 25 === 0 || done === jobs.length) log(`[matrix] ${done}/${jobs.length}`);
    return rec;
  });

  const generatedAt = new Date().toISOString();
  const stamp = generatedAt.replace(/[:.]/g, '-');
  const report: MatrixReport = {
    generatedAt,
    options: {
      models: opts.models,
      samples: opts.samples,
      concurrency: opts.concurrency,
      surfaces: opts.surfaces,
      outDir: opts.outDir,
      corpusSize: opts.corpus.length,
      corpusIds: opts.corpus.map((p) => p.id),
    },
    records,
  };

  mkdirSync(opts.outDir, { recursive: true });
  const json = resolve(opts.outDir, `results-${stamp}.json`);
  const csv = resolve(opts.outDir, `summary-${stamp}.csv`);
  const md = resolve(opts.outDir, `synthesis-${stamp}.md`);
  writeFileSync(json, JSON.stringify(report, null, 2), 'utf8');
  writeFileSync(csv, toCsv(records), 'utf8');
  writeFileSync(md, renderMarkdown(report), 'utf8');
  log(`[matrix] écrit : ${md}`);
  log(`[matrix] écrit : ${csv}`);
  log(`[matrix] écrit : ${json}`);

  return { report, paths: { json, csv, md } };
}
