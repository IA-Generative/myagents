// Endpoint de santé — utilisé par la readinessProbe K8s et par le curl
// post-déploiement documenté dans le README.

import { NextResponse } from 'next/server';

export async function GET() {
  return NextResponse.json({ status: 'ok', service: 'miraiku-agents' });
}
