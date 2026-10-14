// Limiteur de debit en memoire (fenetre fixe), sans dependance externe.
// Objectif : freiner l'abus de cout / DoS sur les endpoints LLM (clé Scaleway
// partagee). Cle = identifiant utilisateur.
//
// LIMITES CONNUES : l'etat est par-process. Avec plusieurs replicas K8s, la
// limite effective est multipliee par le nombre de pods. Pour une limite
// globale stricte, brancher un store partage (Redis). Suffisant ici comme
// premiere barriere contre le hammering depuis un seul compte.

type Bucket = { count: number; resetAt: number };

const buckets = new Map<string, Bucket>();

export function rateLimit(
  key: string,
  opts: { max: number; windowMs: number },
): boolean {
  const now = Date.now();

  // Nettoyage opportuniste pour borner la memoire.
  if (buckets.size > 10_000) {
    for (const [k, b] of buckets) {
      if (now >= b.resetAt) buckets.delete(k);
    }
  }

  const b = buckets.get(key);
  if (!b || now >= b.resetAt) {
    buckets.set(key, { count: 1, resetAt: now + opts.windowMs });
    return true;
  }
  if (b.count >= opts.max) return false;
  b.count += 1;
  return true;
}

// Defaut applique aux endpoints LLM : 20 requetes / minute / utilisateur.
export const LLM_RATE_LIMIT = { max: 20, windowMs: 60_000 };
