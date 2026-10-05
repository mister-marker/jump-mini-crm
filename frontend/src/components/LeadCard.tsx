import { ArrowUpRight, CalendarDays, MessageSquare, Globe2, PenLine, Send } from 'lucide-react'
import { sourceLabels, statusLabels, type Lead } from '../api/client'

export default function LeadCard({ lead, onOpen }: { lead: Lead; onOpen: () => void }) {
  const SourceIcon = lead.source === 'manual' ? PenLine : lead.source === 'webhook' ? Globe2 : Send
  return <button className="lead-card bg-[#1e293b] rounded-2xl border-slate-700" onClick={onOpen}>
    <div className="card-top"><span className={`status status-${lead.status}`}><i />{statusLabels[lead.status]}</span><ArrowUpRight size={18} className="card-arrow" /></div>
    <div className="card-identity"><span className="avatar">{lead.name.slice(0, 1).toLocaleUpperCase('ru')}</span><div><h3>{lead.name}</h3><p>{lead.contact}</p></div></div>
    <p className="card-request">{lead.request || 'Описание задачи пока не добавлено.'}</p>
    <div className="card-tags">{lead.tags.length ? lead.tags.map(tag => <span className="tag-label" key={tag.id}><i style={{ backgroundColor: tag.color }} />{tag.name}</span>) : <span className="no-tags">Без тегов</span>}</div>
    {lead.next_contact_date && <div className="contact-date"><CalendarDays size={13} /> Следующий контакт: {new Date(`${lead.next_contact_date}T12:00:00`).toLocaleDateString('ru-RU', { day: 'numeric', month: 'short' })}</div>}
    <div className="card-footer"><span><SourceIcon size={13} />{sourceLabels[lead.source]}</span><span>{new Date(lead.created_at).toLocaleDateString('ru-RU', { day: 'numeric', month: 'short' })}<MessageSquare size={13} /></span></div>
  </button>
}
