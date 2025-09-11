// Prefer build-time env (Next.js exposes NEXT_PUBLIC_* at build), then runtime window override, then fallback
export const API_BASE =
  (process.env.NEXT_PUBLIC_API_BASE as string | undefined) ||
  (typeof window !== 'undefined' && (window as any).NEXT_PUBLIC_API_BASE) ||
  'http://localhost:8000';

function authHeaders(): Record<string, string> {
  if (typeof window === 'undefined') return {};
  const token = localStorage.getItem('jwt');
  return token ? { Authorization: `Bearer ${token}` } : {};
}

export async function apiGet<T>(path: string): Promise<T> {
  const res = await fetch(`${API_BASE}/${path.replace(/^\//,'')}`, { headers: { ...authHeaders() } });
  if (res.status === 401 && typeof window !== 'undefined') {
    localStorage.removeItem('jwt');
    // Soft redirect to login
    window.location.href = '/login';
    throw new Error('Unauthorized');
  }
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function apiPost<T>(path: string, body: any, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}/${path.replace(/^\//,'')}`,
    { method: 'POST', headers: { 'Content-Type': 'application/json', ...authHeaders() }, body: JSON.stringify(body), ...(init||{}) });
  if (res.status === 401 && typeof window !== 'undefined') {
    localStorage.removeItem('jwt');
    window.location.href = '/login';
    throw new Error('Unauthorized');
  }
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function apiDelete<T = any>(path: string): Promise<T> {
  const res = await fetch(`${API_BASE}/${path.replace(/^\//,'')}`, { method: 'DELETE', headers: { ...authHeaders() } });
  if (res.status === 401 && typeof window !== 'undefined') {
    localStorage.removeItem('jwt');
    window.location.href = '/login';
    throw new Error('Unauthorized');
  }
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}
