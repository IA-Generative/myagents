// Client OpenWebUI — appelé UNIQUEMENT depuis le serveur (BFF / Server Actions).
// Règle n°3 du prompt : jamais d'appel direct OpenWebUI depuis le client.

import { env } from './env';

export class OwuiClient {
  constructor(
    private readonly baseUrl: string = env().OWUI_BASE_URL,
    private readonly accessToken?: string,
  ) {}

  private async request<T>(path: string, init: RequestInit = {}): Promise<T> {
    const headers = new Headers(init.headers);
    headers.set('Content-Type', 'application/json');
    if (this.accessToken) {
      headers.set('Authorization', `Bearer ${this.accessToken}`);
    }
    const res = await fetch(`${this.baseUrl}${path}`, { ...init, headers });
    if (!res.ok) {
      const body = await res.text().catch(() => '');
      throw new Error(
        `OpenWebUI ${init.method ?? 'GET'} ${path} → ${res.status}: ${body}`,
      );
    }
    return (await res.json()) as T;
  }

  // --- Models / Agents ---
  listModels() {
    return this.request<unknown[]>('/api/models');
  }

  createModel(payload: Record<string, unknown>) {
    return this.request<unknown>('/api/models/create', {
      method: 'POST',
      body: JSON.stringify(payload),
    });
  }

  // --- Files / Knowledge ---
  uploadFile(file: Blob, filename: string): Promise<unknown> {
    // Upload multipart — ne passe pas par request() (Content-Type différent)
    const form = new FormData();
    form.append('file', file, filename);
    const headers: HeadersInit = this.accessToken
      ? { Authorization: `Bearer ${this.accessToken}` }
      : {};
    return fetch(`${this.baseUrl}/api/v1/files/`, {
      method: 'POST',
      headers,
      body: form,
    }).then(async (res) => {
      if (!res.ok) throw new Error(`upload failed: ${res.status}`);
      return res.json();
    });
  }

  listKnowledge() {
    return this.request<unknown[]>('/api/v1/knowledge');
  }

  // --- Chat completions (test agent / prompt assist) ---
  chatCompletions(payload: {
    model: string;
    messages: Array<{ role: string; content: string }>;
    stream?: boolean;
  }) {
    return this.request<unknown>('/api/chat/completions', {
      method: 'POST',
      body: JSON.stringify(payload),
    });
  }

  // --- Tools ---
  listTools() {
    return this.request<unknown[]>('/api/v1/tools');
  }
}
