import { useRef, useState, type FormEvent } from 'react'
import { Check, LoaderCircle, Trash2 } from 'lucide-react'
import { api, errorText, sourceLabels, statusLabels, type Lead, type LeadFields, type Status, type Tag, type User } from '../api/client'
import Sheet from './Sheet'

export default function LeadSheet({ lead, tags, user, onClose, onChanged }: {
  lead: Lead | null; tags: Tag[]; user: User; onClose: () => void; onChanged: () => void
}) {
  const [record, setRecord] = useState(lead)
  const persisted = useRef(lead)
  const [fields, setFields] = useState<LeadFields>({
    name: lead?.name || '', contact: lead?.contact || '', request: lead?.request || '',
    status: lead?.status || 'new', next_contact_date: lead?.next_contact_date || null,
  })
  const [selected, setSelected] = useState(() => new Set(lead?.tags.map(tag => tag.id) || []))
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [deleting, setDeleting] = useState(false)
  function update<K extends keyof LeadFields>(key: K, value: LeadFields[K]) { setFields(previous => ({ ...previous, [key]: value })) }
  function toggle(id: string) { setSelected(previous => { const next = new Set(previous); if (next.has(id)) next.delete(id); else next.add(id); return next }) }

  async function save(event: FormEvent) {
    event.preventDefault()
    if (!fields.name.trim() || !fields.contact.trim()) { setError('Укажите имя и контакт.'); return }
    setBusy(true); setError('')
    let baseSaved = false
    try {
      const body = { ...fields, name: fields.name.trim(), contact: fields.contact.trim(), request: fields.request?.trim() || null }
      let current = persisted.current ? await api.updateLead(persisted.current.id, body) : await api.createLead(body)
      // Keep the new ID even if a following tag request fails; retry must not create another lead.
      persisted.current = current; setRecord(current); baseSaved = true
      for (const tag of [...current.tags]) {
        if (!selected.has(tag.id)) {
          current = await api.removeTag(current.id, tag.id)
          persisted.current = current
        }
      }
      for (const id of selected) {
        if (!current.tags.some(tag => tag.id === id)) {
          current = await api.assignTag(current.id, id)
          persisted.current = current
        }
      }
      onChanged(); onClose()
    } catch (e) {
      if (baseSaved) onChanged()
      setError((baseSaved ? 'Лид сохранён, но теги обновлены не полностью. Повторите сохранение. ' : '') + errorText(e))
    } finally { setBusy(false) }
  }

  async function remove() {
    if (!record) return
    setBusy(true); setError('')
    try { await api.deleteLead(record.id); onChanged(); onClose() }
    catch (e) { setError(errorText(e)); setDeleting(false) }
    finally { setBusy(false) }
  }

  return <Sheet title={record ? 'Карточка лида' : 'Новый лид'} description={record ? `${sourceLabels[record.source]} · ${new Date(record.created_at).toLocaleDateString('ru-RU')}` : 'Добавьте обращение — контакт и задача будут под рукой.'} busy={busy} onClose={onClose}>
    <form onSubmit={save} className="lead-form">
      <div className="sheet-body" data-vaul-no-drag><fieldset disabled={busy}>
        <label htmlFor="lead-name">Имя <span>*</span></label>
        <input id="lead-name" value={fields.name} onChange={e => update('name', e.target.value)} maxLength={200} required placeholder="Как зовут клиента" autoComplete="off" />
        <label htmlFor="lead-contact">Контакт <span>*</span></label>
        <input id="lead-contact" value={fields.contact} onChange={e => update('contact', e.target.value)} maxLength={320} required placeholder="Телефон, email или @username" autoComplete="off" />
        <label htmlFor="lead-request">Задача клиента</label>
        <textarea id="lead-request" value={fields.request || ''} onChange={e => update('request', e.target.value)} maxLength={10000} rows={4} placeholder="Что нужно сделать? Добавьте детали обращения." />
        <div className="form-columns"><div><label htmlFor="lead-status">Статус</label><select id="lead-status" value={fields.status} onChange={e => update('status', e.target.value as Status)}>
          {Object.entries(statusLabels).map(([value, label]) => <option key={value} value={value}>{label}</option>)}
        </select></div><div><label htmlFor="lead-date">Следующий контакт</label><input id="lead-date" type="date" value={fields.next_contact_date || ''} onChange={e => update('next_contact_date', e.target.value || null)} /></div></div>
        <label>Теги <small>Можно выбрать несколько</small></label>
        <div className="tag-options">{tags.length ? tags.map(tag => <button type="button" className={`tag-option ${selected.has(tag.id) ? 'selected' : ''}`} key={tag.id} aria-pressed={selected.has(tag.id)} onClick={() => toggle(tag.id)}>
          <i style={{ backgroundColor: tag.color }} />{tag.name}{selected.has(tag.id) && <Check size={13} />}
        </button>) : <p className="muted small">Теги можно создать в разделе «Теги команды».</p>}</div>
        {error && <p className="error-box" role="alert">{error}</p>}
        {record && user.role === 'admin' && <div className="delete-area">{deleting ? <><p>Удалить лид? Восстановить его будет нельзя.</p><div className="inline-actions"><button type="button" className="btn danger" onClick={() => void remove()}>Удалить безвозвратно</button><button type="button" className="btn secondary" onClick={() => setDeleting(false)}>Отмена</button></div></> : <button type="button" className="text-button danger-text" onClick={() => setDeleting(true)}><Trash2 size={16} /> Удалить лид</button>}</div>}
      </fieldset></div>
      <footer className="sheet-footer"><button className="btn secondary" type="button" onClick={onClose} disabled={busy}>Отмена</button><button className="btn primary" type="submit" disabled={busy}>{busy ? <LoaderCircle className="spin" size={18} /> : <Check size={18} />}{busy ? 'Сохраняем…' : record ? 'Сохранить изменения' : 'Создать лида'}</button></footer>
    </form>
  </Sheet>
}
