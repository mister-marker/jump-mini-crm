import { useState, type FormEvent } from 'react'
import { Check, LoaderCircle, Plus, Tags } from 'lucide-react'
import { api, errorText, type Tag } from '../api/client'
import Sheet from './Sheet'

const colors = ['#A3E635', '#60A5FA', '#C084FC', '#FB923C', '#F472B6', '#2DD4BF', '#94A3B8']

export default function TagsSheet({ tags, onAdded, onClose }: { tags: Tag[]; onAdded: (tag: Tag) => void; onClose: () => void }) {
  const [name, setName] = useState('')
  const [color, setColor] = useState(colors[0])
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  async function submit(event: FormEvent) {
    event.preventDefault()
    if (!name.trim()) return
    setBusy(true); setError('')
    try { onAdded(await api.createTag(name.trim(), color)); setName('') }
    catch (e) { setError(errorText(e)) }
    finally { setBusy(false) }
  }
  return <Sheet title="Теги команды" description="Создавайте теги, чтобы группировать обращения и быстро находить нужные." busy={busy} onClose={onClose}>
    <div className="sheet-body">
      <div className="tag-directory">{tags.length ? tags.map(tag => <span className="tag-label" key={tag.id}><i style={{ backgroundColor: tag.color }} />{tag.name}</span>) : <p className="muted"><Tags size={18} /> Пока нет тегов. Добавьте первый.</p>}</div>
      <form onSubmit={submit} className="tag-form">
        <label htmlFor="tag-name">Новый тег</label>
        <input id="tag-name" value={name} onChange={e => setName(e.target.value)} maxLength={64} required placeholder="Например, Приоритетный" disabled={busy} />
        <label>Цвет тега</label>
        <div className="color-picker">{colors.map(value => <button type="button" key={value} className="color-option" style={{ backgroundColor: value }}
          aria-label={`Цвет ${value}`} aria-pressed={value === color} onClick={() => setColor(value)} disabled={busy}>{value === color && <Check size={18} />}</button>)}</div>
        {error && <p className="error-box" role="alert">{error}</p>}
        <button className="btn primary full" disabled={busy || !name.trim()}>{busy ? <LoaderCircle size={18} className="spin" /> : <Plus size={18} />} Создать тег</button>
      </form>
    </div>
  </Sheet>
}
