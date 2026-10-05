export type Status = 'new' | 'in_progress' | 'done' | 'rejected'
export type Source = string
export interface SourceOption { id: Source; name: string }
export interface Tag { id: string; name: string; color: string }
export interface User { id: string; telegram_id: number | null; role: 'admin' | 'manager' }
export interface Lead {
  id: string; name: string; contact: string; request: string | null
  source: Source; status: Status; next_contact_date: string | null
  created_at: string; updated_at: string; tags: Tag[]
}
export type LeadFields = Pick<Lead, 'name' | 'contact' | 'request' | 'status' | 'next_contact_date'>
export type NewLeadFields = LeadFields & Pick<Lead, 'source'>
interface Token { access_token: string; token_type: string; expires_in: number }

const base = (import.meta.env.VITE_API_URL || 'http://localhost:8000').replace(/\/$/, '')
const storageKey = 'jump-crm-session'
let token: string | null = null

export class ApiError extends Error {
  constructor(public status: number, message: string) { super(message) }
}

export function savedToken(): string | null {
  try { return sessionStorage.getItem(storageKey) } catch { return null }
}

export function setToken(value: string | null, persist = false): void {
  token = value
  try {
    if (value && persist) sessionStorage.setItem(storageKey, value)
    else sessionStorage.removeItem(storageKey)
  } catch { /* Restricted WebViews can still use the in-memory session. */ }
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers)
  if (init.body) headers.set('Content-Type', 'application/json')
  if (token) headers.set('Authorization', `Bearer ${token}`)
  let response: Response
  const controller = new AbortController()
  const abort = () => controller.abort()
  if (init.signal?.aborted) abort()
  init.signal?.addEventListener('abort', abort, { once: true })
  const timeout = window.setTimeout(abort, 90000)
  try {
    // Render's free instance can take around a minute to wake up.
    response = await fetch(`${base}${path}`, {
      ...init, headers, signal: controller.signal, cache: 'no-store',
    })
  } catch (error) {
    if (init.signal?.aborted) throw error
    throw new ApiError(0, 'Не удалось связаться с CRM. Проверьте соединение и попробуйте ещё раз.')
  } finally {
    window.clearTimeout(timeout)
    init.signal?.removeEventListener('abort', abort)
  }
  if (!response.ok) {
    const messages: Record<number, string> = {
      401: 'Сессия завершена. Войдите снова.',
      403: 'У этого аккаунта нет доступа к CRM. Обратитесь к администратору.',
      404: 'Запись не найдена. Обновите список.',
      409: 'Такая запись уже существует. Проверьте название.',
      422: 'Проверьте заполнение полей.',
      429: 'Слишком много попыток. Подождите минуту и повторите.',
      503: 'Сервис временно недоступен. Попробуйте ещё раз чуть позже.',
    }
    if (response.status === 401 && !path.startsWith('/auth/')) {
      window.dispatchEvent(new Event('crm:unauthorized'))
    }
    throw new ApiError(response.status, messages[response.status] || 'Не удалось выполнить действие. Попробуйте ещё раз.')
  }
  return response.status === 204 ? undefined as T : response.json() as Promise<T>
}

export const api = {
  pin: (pin: string) => request<Token>('/auth/pin', { method: 'POST', body: JSON.stringify({ pin }) }),
  telegram: (initData: string) => request<Token>('/auth/telegram', { method: 'POST', body: JSON.stringify({ initData }) }),
  me: () => request<User>('/auth/me'),
  leads: (filters: { status: string; source: string; tag: string; page: number }, signal?: AbortSignal) => {
    const query = new URLSearchParams({ limit: '13', offset: String(filters.page * 12) })
    if (filters.status) query.set('status', filters.status)
    if (filters.source) query.set('source', filters.source)
    if (filters.tag) query.set('tag_id', filters.tag)
    return request<Lead[]>(`/leads?${query}`, { signal })
  },
  tags: async (signal?: AbortSignal): Promise<Tag[]> => {
    const all: Tag[] = []
    for (let offset = 0; ; offset += 100) {
      const page = await request<Tag[]>(`/tags?limit=100&offset=${offset}`, { signal })
      all.push(...page)
      if (page.length < 100) return all
    }
  },
  sources: (signal?: AbortSignal) => request<SourceOption[]>('/sources', { signal }),
  createSource: (name: string) => request<SourceOption>('/sources', {
    method: 'POST', body: JSON.stringify({ name }),
  }),
  createLead: (fields: NewLeadFields) => request<Lead>('/leads', {
    method: 'POST', body: JSON.stringify(fields),
  }),
  updateLead: (id: string, fields: LeadFields) => request<Lead>(`/leads/${id}`, {
    method: 'PATCH', body: JSON.stringify(fields),
  }),
  deleteLead: (id: string) => request<void>(`/leads/${id}`, { method: 'DELETE' }),
  assignTag: (id: string, tag: string) => request<Lead>(`/leads/${id}/tags/${tag}`, { method: 'POST' }),
  removeTag: (id: string, tag: string) => request<Lead>(`/leads/${id}/tags/${tag}`, { method: 'DELETE' }),
  createTag: (name: string, color: string) => request<Tag>('/tags', {
    method: 'POST', body: JSON.stringify({ name, color }),
  }),
}

export const statusLabels: Record<Status, string> = {
  new: 'Новый', in_progress: 'В работе', done: 'Завершён', rejected: 'Отказ',
}
export const sourceName = (source: Source, options: SourceOption[]) =>
  options.find(option => option.id === source)?.name || source
export const errorText = (error: unknown) => error instanceof Error ? error.message : 'Что-то пошло не так. Повторите попытку.'
