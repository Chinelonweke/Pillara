// src/lib/api.ts
// Central API client for all Pillara backend calls.
// All components import from here — never fetch directly.

const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://127.0.0.1:8000'

// ── Token management ─────────────────────────────────────────────────────────
// Tokens live in localStorage for simplicity in dev.
// Production: consider httpOnly cookies for better XSS protection.

export const getToken = (): string | null => {
  if (typeof window === 'undefined') return null
  return localStorage.getItem('pillara_access_token')
}

export const setTokens = (accessToken: string, refreshToken: string) => {
  localStorage.setItem('pillara_access_token', accessToken)
  localStorage.setItem('pillara_refresh_token', refreshToken)
}

export const clearTokens = () => {
  localStorage.removeItem('pillara_access_token')
  localStorage.removeItem('pillara_refresh_token')
}

// ── Core fetch wrapper ────────────────────────────────────────────────────────

interface FetchOptions {
  method?: string
  body?: unknown
  auth?: boolean  // default true — most endpoints require auth
}

export class APIError extends Error {
  constructor(
    public status: number,
    public error: string,
    message: string
  ) {
    super(message)
  }
}

async function apiFetch<T>(path: string, options: FetchOptions = {}): Promise<T> {
  const { method = 'GET', body, auth = true } = options

  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
  }

  if (auth) {
    const token = getToken()
    if (token) {
      headers['Authorization'] = `Bearer ${token}`
    }
  }

  const response = await fetch(`${API_BASE}${path}`, {
    method,
    headers,
    body: body ? JSON.stringify(body) : undefined,
  })

  const data = await response.json()

  if (!response.ok) {
    throw new APIError(
      response.status,
      data.error || 'unknown_error',
      data.message || 'An unexpected error occurred'
    )
  }

  return data as T
}

// ── Auth ──────────────────────────────────────────────────────────────────────

export interface TokenResponse {
  access_token: string
  refresh_token: string
  token_type: string
  expires_in: number
}

export interface UserInfo {
  id: string
  is_verified: boolean
  subscription_tier: string
  onboarding_completed: boolean
  created_at: string
}

export const auth = {
  register: (email: string, password: string) =>
    apiFetch<TokenResponse>('/api/v1/auth/register', {
      method: 'POST',
      body: { email, password },
      auth: false,
    }),

  login: (email: string, password: string) =>
    apiFetch<TokenResponse>('/api/v1/auth/login', {
      method: 'POST',
      body: { email, password },
      auth: false,
    }),

  me: () => apiFetch<UserInfo>('/api/v1/auth/me'),

  verifyEmail: (token: string) =>
    apiFetch('/api/v1/auth/verify-email', {
      method: 'POST',
      body: { token },
      auth: false,
    }),

  logout: () =>
    apiFetch('/api/v1/auth/logout', { method: 'POST' }),
}

// ── Profiles ──────────────────────────────────────────────────────────────────

export interface Profile {
  id: string
  name: string
  relationship_to_user: string
  date_of_birth: string | null
  gender: string | null
  weight_kg: number | null
  known_allergies: string | null
  medical_conditions: string | null
  is_primary: boolean
  created_at: string
}

export const profiles = {
  list: () => apiFetch<Profile[]>('/api/v1/profiles/'),

  create: (data: Partial<Profile>) =>
    apiFetch<Profile>('/api/v1/profiles/', {
      method: 'POST',
      body: data,
    }),

  update: (profileId: string, data: Partial<Profile>) =>
    apiFetch<Profile>(`/api/v1/profiles/${profileId}`, {
      method: 'PATCH',
      body: data,
    }),
}

// ── Medications ───────────────────────────────────────────────────────────────

export interface Medication {
  id: string
  profile_id: string
  name: string
  generic_name: string
  dosage: string
  frequency: string
  route: string
  start_date: string | null
  end_date: string | null
  purpose: string | null
  notes: string | null
  is_active: boolean
  created_at: string
}

export const medications = {
  list: (profileId: string) =>
    apiFetch<Medication[]>(`/api/v1/medications/?profile_id=${profileId}`),

  add: (profileId: string, data: Partial<Medication>) =>
    apiFetch<Medication>(`/api/v1/medications/?profile_id=${profileId}`, {
      method: 'POST',
      body: data,
    }),

  delete: (medicationId: string) =>
    apiFetch(`/api/v1/medications/${medicationId}`, { method: 'DELETE' }),
}

// ── Interactions ──────────────────────────────────────────────────────────────

export interface AllergyWarning {
  drug_name: string
  allergen: string
  severity: string
  description: string
  action_required: string
}

export interface InteractionResult {
  drug_a: string
  drug_b: string
  severity: string
  description: string
  action_required: string
}

export interface InteractionCheckResponse {
  drugs_checked: string[]
  interactions_found: InteractionResult[]
  allergy_warnings: AllergyWarning[]
  overall_risk: string
  summary: string
  disclaimer: string
  confidence_gate_passed: boolean
  provider_used: string
  latency_ms: number
}

export const interactions = {
  check: (drugNames: string[], profileId?: string) =>
    apiFetch<InteractionCheckResponse>('/api/v1/interactions/check', {
      method: 'POST',
      body: { drug_names: drugNames, profile_id: profileId },
    }),
}

// ── AI Chat ───────────────────────────────────────────────────────────────────

export interface AIQueryResponse {
  response_text: string
  disclaimer: string
  confidence_gate_passed: boolean
  provider_used: string
  latency_ms: number
  conversation_id: string
}

export const ai = {
  query: (query: string, profileId?: string, conversationId?: string) =>
    apiFetch<AIQueryResponse>('/api/v1/ai/query', {
      method: 'POST',
      body: { query, profile_id: profileId, conversation_id: conversationId },
    }),
}
