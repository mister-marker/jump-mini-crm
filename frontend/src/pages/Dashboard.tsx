import { useCallback, useEffect, useState } from 'react'
import { ArrowUpRight, LayoutGrid, LogOut, Plus, RefreshCw, Send, Tags, X, ChevronLeft, ChevronRight, Inbox, SlidersHorizontal } from 'lucide-react'
import { api, errorText, statusLabels, type Lead, type SourceOption, type Tag, type User } from '../api/client'
import LeadCard from '../components/LeadCard'
import LeadSheet from '../components/LeadSheet'
import TagsSheet from '../components/TagsSheet'
import { telegram } from '../utils/telegram'

export default function Dashboard({ user, onLogout }: { user: User; onLogout: () => void }) {
  const [leads, setLeads] = useState<Lead[]>([])
  const [tags, setTags] = useState<Tag[]>([])
  const [sources, setSources] = useState<SourceOption[]>([])
  const [status, setStatus] = useState('')
  const [source, setSource] = useState('')
  const [tag, setTag] = useState('')
  const [page, setPage] = useState(0)
  const [hasNext, setHasNext] = useState(false)
  const [loading, setLoading] = useState(true)
  const [refreshing, setRefreshing] = useState(false)
  const [error, setError] = useState('')
  const [updated, setUpdated] = useState<Date | null>(null)
  const [revision, setRevision] = useState(0)
  const [editing, setEditing] = useState<Lead | 'new' | null>(null)
  const [showTags, setShowTags] = useState(false)
  const refresh = useCallback(() => setRevision(n => n + 1), [])
  const closeLead = useCallback(() => setEditing(null), [])
  const closeTags = useCallback(() => setShowTags(false), [])

  useEffect(() => { window.scrollTo(0, 0) }, [])

  useEffect(() => {
    const controller = new AbortController()
    let pending = false
    setLoading(true)
    setLeads([])
    setHasNext(false)
    async function load() {
      if (pending || controller.signal.aborted) return
      pending = true; setRefreshing(true)
      try {
        const [records, labels, origins] = await Promise.all([
          api.leads({ status, source, tag, page }, controller.signal),
          api.tags(controller.signal), api.sources(controller.signal),
        ])
        if (controller.signal.aborted) return
        if (!records.length && page > 0) { setPage(n => n - 1); return }
        setLeads(records.slice(0, 12)); setHasNext(records.length > 12)
        setTags(labels); setSources(origins); setError(''); setUpdated(new Date())
      } catch (e) { if (!controller.signal.aborted) setError(errorText(e)) }
      finally {
        pending = false
        if (!controller.signal.aborted) { setLoading(false); setRefreshing(false) }
      }
    }
    const visible = () => { if (document.visibilityState === 'visible') void load() }
    void load()
    const interval = window.setInterval(visible, 30000)
    window.addEventListener('focus', visible)
    return () => { controller.abort(); window.clearInterval(interval); window.removeEventListener('focus', visible) }
  }, [status, source, tag, page, revision])

  useEffect(() => {
    const button = telegram()?.MainButton
    if (!button) return
    const open = () => setEditing('new')
    button.setText('Добавить лида')
    button.onClick(open)
    if (editing || showTags) button.hide(); else button.show()
    return () => { button.offClick(open); button.hide() }
  }, [editing, showTags])

  function changeTag(value: string) { setTag(value); setPage(0) }
  function resetFilters() { setStatus(''); setSource(''); setTag(''); setPage(0) }

  return <div className="workspace bg-[var(--tg-theme-bg-color)]">
    <aside className="sidebar">
      <a className="brand" href="/" aria-label="Jump Ads CRM"><span className="brand-symbol"><ArrowUpRight /></span>jump<span className="brand-suffix">ads</span></a>
      <div className="workspace-label">РАБОЧЕЕ ПРОСТРАНСТВО</div>
      <nav aria-label="Основная навигация"><button className="nav-item active" onClick={resetFilters}><LayoutGrid size={18} />Лиды<span className="nav-dot" /></button><button className="nav-item" onClick={() => setShowTags(true)}><Tags size={18} />Теги команды</button></nav>
      <div className="sidebar-bottom"><a className="bot-link" href="https://t.me/jump_crm_lead_bot" target="_blank" rel="noreferrer"><span className="bot-icon"><Send size={19} /></span><div><strong>Бот для заявок</strong><span>Открыть в Telegram</span></div><ArrowUpRight size={16} /></a><p>JUMP ADS <span>MINI CRM / 01</span></p></div>
    </aside>
    <div className="workspace-main">
      <header className="topbar"><div className="breadcrumb"><span className="mobile-logo"><ArrowUpRight size={21} /></span>Jump Ads <span>/</span> <strong>CRM</strong></div><div className="user-area"><span className="role-dot" /><span>{user.role === 'admin' ? 'Администратор' : 'Менеджер'}</span><button className="icon-button" onClick={onLogout} aria-label="Выйти из CRM" title="Выйти"><LogOut size={17} /></button></div></header>
      <main className="dashboard">
        <div className="page-heading"><div><p className="eyebrow">РАБОТА С ОБРАЩЕНИЯМИ</p><h1>Лиды<span className="heading-dot">.</span></h1><p className="muted">Все обращения. Следующий шаг — за вами.</p></div><button className="btn primary add-lead" onClick={() => setEditing('new')}><Plus size={19} />Добавить лида</button></div>
        <section className="filters" aria-label="Фильтры лидов">
          <div className="filter-top"><div className="status-tabs" role="group" aria-label="Статус лида">{[['', 'Все лиды'], ...Object.entries(statusLabels)].map(([value, label]) => <button key={value} className={status === value ? 'active' : ''} aria-pressed={status === value} onClick={() => { setStatus(value); setPage(0) }}>{label}</button>)}</div><button className="icon-button" onClick={refresh} disabled={refreshing} aria-label="Обновить лидов" title="Обновить"><RefreshCw size={17} className={refreshing ? 'spin' : ''} /></button></div>
          <div className="source-filter"><label htmlFor="source-filter">Источник</label><select id="source-filter" value={source} onChange={event => { setSource(event.target.value); setPage(0) }}><option value="">Все источники</option>{sources.map(item => <option key={item.id} value={item.id}>{item.name}</option>)}</select></div>
          <div className="filter-bottom"><span className="filter-caption"><SlidersHorizontal size={15} />Теги</span><div className="tag-scroll"><button className={`filter-chip ${!tag ? 'selected' : ''}`} onClick={() => changeTag('')} aria-pressed={!tag}>Все</button>{tags.map(label => <button className={`filter-chip ${tag === label.id ? 'selected' : ''}`} key={label.id} aria-pressed={tag === label.id} onClick={() => changeTag(tag === label.id ? '' : label.id)}><i style={{ backgroundColor: label.color }} />{label.name}</button>)}</div><button className="icon-button" onClick={() => setShowTags(true)} title="Управление тегами" aria-label="Теги команды"><Tags size={17} /></button></div>
        </section>
        <div className="list-meta"><span>{loading ? 'Загружаем обращения…' : `${leads.length} на странице`}{(status || source || tag) && <button className="reset-filter" onClick={resetFilters}>Сбросить фильтры <X size={12} /></button>}</span><span className="sync-label">{updated ? `Обновлено в ${updated.toLocaleTimeString('ru-RU', { hour: '2-digit', minute: '2-digit' })}` : 'Подключаемся к CRM'}</span></div>
        {error && <div className="error-box list-error" role="alert"><span>{error}</span><button className="text-button" onClick={refresh} disabled={refreshing}>Повторить</button></div>}
        {loading ? <div className="lead-grid" aria-label="Загрузка лидов" aria-busy="true">{[1, 2, 3, 4].map(id => <div className="skeleton-card" key={id}><i /><i /><i /></div>)}</div>
          : leads.length ? <div className="lead-grid">{leads.map(lead => <LeadCard key={lead.id} lead={lead} sources={sources} onOpen={() => setEditing(lead)} />)}</div>
          : !error && <div className="empty-state"><span className="empty-icon"><Inbox size={30} /></span><h2>{status || source || tag ? 'Пока нет совпадений' : 'Здесь начинается работа с клиентами'}</h2><p>{status || source || tag ? 'Попробуйте другой фильтр.' : 'Добавьте первый лид вручную или оставьте заявку через Telegram-бота.'}</p><button className="btn secondary" onClick={status || source || tag ? resetFilters : () => setEditing('new')}>{status || source || tag ? 'Сбросить фильтры' : 'Добавить первого лида'}<ArrowUpRight size={16} /></button></div>}
        {(page > 0 || hasNext) && <nav className="pagination" aria-label="Страницы лидов"><button className="btn secondary" disabled={page === 0 || loading} onClick={() => setPage(n => n - 1)}><ChevronLeft size={16} />Назад</button><span>Страница {page + 1}</span><button className="btn secondary" disabled={!hasNext || loading} onClick={() => setPage(n => n + 1)}>Далее<ChevronRight size={16} /></button></nav>}
        <footer className="dashboard-footer"><span className="live-dot" /> Новые обращения подгружаются автоматически</footer>
      </main>
    </div>
    {editing && <LeadSheet key={editing === 'new' ? 'new' : editing.id} lead={editing === 'new' ? null : editing} tags={tags} sources={sources} user={user} onSourceAdded={item => setSources(previous => [...previous, item].sort((a, b) => a.name.localeCompare(b.name)))} onClose={closeLead} onChanged={refresh} />}
    {showTags && <TagsSheet tags={tags} onClose={closeTags} onAdded={label => setTags(previous => [...previous, label].sort((a, b) => a.name.localeCompare(b.name)))} />}
  </div>
}
