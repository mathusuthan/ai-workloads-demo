import type {
  ArchetypesCatalogResponse,
  Cat1BatchResponse,
  Cat1PresetsResponse,
  Cat1RunResponse,
  Cat2ModelTier,
  Cat2PresetsResponse,
  Cat2RungId,
  Cat2RunResponse,
  Cat2SectionKey,
  Cat2SectionRegenResponse,
  Cat2SubTaskType,
  Cat3ChatTurnEntry,
  Cat3ChatTurnResponse,
  Cat3PresetsResponse,
  Cat3RungId,
  Cat3RunResponse,
  Cat4AdhocQueryResponse,
  Cat4PresetsResponse,
  Cat4RungId,
  Cat4RunResponse,
  Cat5PresetsResponse,
  Cat5RungId,
  Cat5RunResponse,
  Cat6PresetsResponse,
  Cat6RungId,
  Cat6RunResponse,
  CreditShieldCredentials,
  ExecutionMode,
  RungId,
  SubTaskType,
  SystemStatusResponse,
} from './types'

const STORAGE_KEY = 'novamart_credit_shield_v1'

export function loadCredentials(): CreditShieldCredentials {
  try {
    const raw = sessionStorage.getItem(STORAGE_KEY)
    if (raw) {
      const parsed = JSON.parse(raw) as Partial<CreditShieldCredentials>
      return {
        mode: parsed.mode === 'live' ? 'live' : 'replay',
        anthropicKey: parsed.anthropicKey ?? '',
        authorPasscode: parsed.authorPasscode ?? '',
      }
    }
  } catch {
    // ignore storage restrictions
  }
  return {
    mode: 'replay',
    anthropicKey: '',
    authorPasscode: '',
  }
}

export function saveCredentials(creds: CreditShieldCredentials): void {
  try {
    sessionStorage.setItem(STORAGE_KEY, JSON.stringify(creds))
  } catch {
    // ignore storage restrictions
  }
}

function buildAuthHeaders(creds: CreditShieldCredentials): Record<string, string> {
  const headers: Record<string, string> = { 'Content-Type': 'application/json' }
  if (creds.mode === 'live') {
    if (creds.anthropicKey.trim()) headers['X-Anthropic-Api-Key'] = creds.anthropicKey.trim()
    if (creds.authorPasscode.trim()) headers['X-Author-Passcode'] = creds.authorPasscode.trim()
  }
  return headers
}

async function fetchJson<T>(url: string, init?: RequestInit): Promise<T> {
  const res = await fetch(url, init)
  if (!res.ok) {
    let msg = `Request failed (${res.status})`
    try {
      const errBody = (await res.json()) as { detail?: string }
      if (errBody.detail) msg = errBody.detail
    } catch {
      // ignore non-json error bodies
    }
    throw new Error(msg)
  }
  return (await res.json()) as T
}

export function fetchSystemStatus(): Promise<SystemStatusResponse> {
  return fetchJson<SystemStatusResponse>('/api/system/status')
}

export function fetchArchetypes(): Promise<ArchetypesCatalogResponse> {
  return fetchJson<ArchetypesCatalogResponse>('/api/archetypes')
}

export function fetchCat1Presets(): Promise<Cat1PresetsResponse> {
  return fetchJson<Cat1PresetsResponse>('/api/cat1/presets')
}

export function runCat1Arena(
  params: {
    preset_id?: string
    custom_input?: string
    sub_task: SubTaskType
    rungs: RungId[]
    mode: ExecutionMode
  },
  creds: CreditShieldCredentials
): Promise<Cat1RunResponse> {
  return fetchJson<Cat1RunResponse>('/api/cat1/run', {
    method: 'POST',
    headers: buildAuthHeaders(creds),
    body: JSON.stringify(params),
  })
}

export function runCat1Batch(
  params: {
    sub_task: 'mixed' | SubTaskType
    mode: ExecutionMode
  },
  creds: CreditShieldCredentials
): Promise<Cat1BatchResponse> {
  return fetchJson<Cat1BatchResponse>('/api/cat1/batch', {
    method: 'POST',
    headers: buildAuthHeaders(creds),
    body: JSON.stringify(params),
  })
}

export function fetchCat2Presets(): Promise<Cat2PresetsResponse> {
  return fetchJson<Cat2PresetsResponse>('/api/cat2/presets')
}

export function runCat2Arena(
  params: {
    preset_id?: string
    custom_input?: string
    sub_task: Cat2SubTaskType
    rungs: Cat2RungId[]
    mode: ExecutionMode
  },
  creds: CreditShieldCredentials
): Promise<Cat2RunResponse> {
  return fetchJson<Cat2RunResponse>('/api/cat2/run', {
    method: 'POST',
    headers: buildAuthHeaders(creds),
    body: JSON.stringify(params),
  })
}

export function regenerateCat2Section(
  params: {
    preset_id?: string
    custom_input?: string
    sub_task: Cat2SubTaskType
    section_key: Cat2SectionKey
    current_section: unknown
    reviewer_instruction: string
    model_tier: Cat2ModelTier
    mode: ExecutionMode
  },
  creds: CreditShieldCredentials
): Promise<Cat2SectionRegenResponse> {
  return fetchJson<Cat2SectionRegenResponse>('/api/cat2/regenerate-section', {
    method: 'POST',
    headers: buildAuthHeaders(creds),
    body: JSON.stringify(params),
  })
}

export function fetchCat3Presets(): Promise<Cat3PresetsResponse> {
  return fetchJson<Cat3PresetsResponse>('/api/cat3/presets')
}

export function runCat3Arena(
  params: {
    preset_id: string
    use_case?: 'it_hr_service_desk'
    rungs?: Cat3RungId[]
    mode: ExecutionMode
  },
  creds: CreditShieldCredentials
): Promise<Cat3RunResponse> {
  return fetchJson<Cat3RunResponse>('/api/cat3/run', {
    method: 'POST',
    headers: buildAuthHeaders(creds),
    body: JSON.stringify(params),
  })
}

export function sendCat3ChatTurn(
  params: {
    preset_id: string
    rung_id: Cat3RungId
    user_message: string
    prior_turns: Cat3ChatTurnEntry[]
    memory_summary: Record<string, unknown> | null
    mode: ExecutionMode
  },
  creds: CreditShieldCredentials
): Promise<Cat3ChatTurnResponse> {
  return fetchJson<Cat3ChatTurnResponse>('/api/cat3/chat-turn', {
    method: 'POST',
    headers: buildAuthHeaders(creds),
    body: JSON.stringify(params),
  })
}

export function fetchCat4Presets(): Promise<Cat4PresetsResponse> {
  return fetchJson<Cat4PresetsResponse>('/api/cat4/presets')
}

export function runCat4Arena(
  params: {
    preset_id: string
    use_case?: 'supplier_msa_due_diligence'
    rungs?: Cat4RungId[]
    mode: ExecutionMode
  },
  creds: CreditShieldCredentials
): Promise<Cat4RunResponse> {
  return fetchJson<Cat4RunResponse>('/api/cat4/run', {
    method: 'POST',
    headers: buildAuthHeaders(creds),
    body: JSON.stringify(params),
  })
}

export function runCat4CustomQuery(
  params: {
    preset_id: string
    question: string
    rungs?: Cat4RungId[]
    mode: ExecutionMode
  },
  creds: CreditShieldCredentials
): Promise<Cat4AdhocQueryResponse> {
  return fetchJson<Cat4AdhocQueryResponse>('/api/cat4/query', {
    method: 'POST',
    headers: buildAuthHeaders(creds),
    body: JSON.stringify(params),
  })
}

export function fetchCat5Presets(): Promise<Cat5PresetsResponse> {
  return fetchJson<Cat5PresetsResponse>('/api/cat5/presets')
}

export function runCat5Arena(
  params: {
    preset_id: string
    use_case?: 'invoice_3way_reconciliation'
    rungs?: Cat5RungId[]
    mode: ExecutionMode
  },
  creds: CreditShieldCredentials
): Promise<Cat5RunResponse> {
  return fetchJson<Cat5RunResponse>('/api/cat5/run', {
    method: 'POST',
    headers: buildAuthHeaders(creds),
    body: JSON.stringify(params),
  })
}

export function fetchCat6Presets(): Promise<Cat6PresetsResponse> {
  return fetchJson<Cat6PresetsResponse>('/api/cat6/presets')
}

export function runCat6Arena(
  params: {
    preset_id: string
    use_case?: 'checkout_ci_self_healing_swarm'
    rungs?: Cat6RungId[]
    mode: ExecutionMode
  },
  creds: CreditShieldCredentials
): Promise<Cat6RunResponse> {
  return fetchJson<Cat6RunResponse>('/api/cat6/run', {
    method: 'POST',
    headers: buildAuthHeaders(creds),
    body: JSON.stringify(params),
  })
}
