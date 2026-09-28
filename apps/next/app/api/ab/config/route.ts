// GET /api/ab/config — expose les config publiques (non-sensibles) au client.
// Utilisé par le composant MiraiChatLink pour construire le lien.

import { NextResponse } from 'next/server';
import { env } from '@/lib/env';

export async function GET() {
  const e = env();
  return NextResponse.json({
    owuiPublicUrl: e.OWUI_PUBLIC_URL || null,
  });
}
