import { useState, type FormEvent } from 'react'
import { ArrowUpRight, ArrowRight, LockKeyhole, LoaderCircle, ShieldCheck } from 'lucide-react'

interface Props {
  busy: boolean; error: string; telegramMode: boolean
  onLogin: (pin: string) => Promise<void>; onRetry: () => void
}

export default function Login({ busy, error, telegramMode, onLogin, onRetry }: Props) {
  const [pin, setPin] = useState('')
  function submit(event: FormEvent) { event.preventDefault(); void onLogin(pin) }
  return <main className="login-page bg-[var(--tg-theme-bg-color)]">
    <a className="brand" href="/" aria-label="Jump Ads CRM"><span className="brand-symbol"><ArrowUpRight /></span>jump<span className="brand-suffix">ads</span></a>
    <div className="login-layout">
      <section className="login-intro">
        <p className="eyebrow"><span className="live-dot" /> WORKSPACE / JUMP ADS</p>
        <h1>Каждое обращение.<br /><span>На своём месте.</span></h1>
        <p className="intro-copy">Заявки из Telegram, с сайта и от вашей команды — в одном рабочем пространстве.</p>
        <div className="intro-lines"><div><span>01</span> Собирайте обращения</div><div><span>02</span> Назначайте теги</div><div><span>03</span> Доводите до результата <ArrowUpRight size={19} /></div></div>
        <div className="orbit" aria-hidden="true"><div /><ArrowUpRight /></div>
      </section>
      <section className="login-panel">
        <div className="login-icon"><LockKeyhole size={23} /></div>
        <p className="eyebrow">ДОСТУП КОМАНДЫ</p>
        <h2>{telegramMode ? 'Вход через Telegram' : 'Добро пожаловать'}</h2>
        <p className="muted">{telegramMode ? 'Проверим ваш аккаунт и откроем рабочее пространство.' : 'Введите ПИН-код, чтобы открыть CRM агентства.'}</p>
        {telegramMode ? <button className="btn primary full" disabled={busy} onClick={onRetry}>
          {busy ? <LoaderCircle className="spin" size={18} /> : <ArrowRight size={18} />} {busy ? 'Проверяем доступ' : 'Повторить вход'}
        </button> : <form onSubmit={submit}>
          <label htmlFor="pin">ПИН-код</label>
          <input id="pin" className="pin-input" type="password" inputMode="numeric" pattern="[0-9]{4}" minLength={4} maxLength={4}
            value={pin} onChange={e => setPin(e.target.value.replace(/\D/g, ''))} placeholder="· · · ·" required autoComplete="off" disabled={busy} />
          <button className="btn primary full" disabled={busy || pin.length !== 4} type="submit">
            {busy ? <LoaderCircle className="spin" size={18} /> : null}{busy ? 'Подключаемся…' : 'Войти в CRM'} {!busy && <ArrowRight size={18} />}
          </button>
        </form>}
        {error && <p className="error-box" role="alert">{error}</p>}
        {busy && <p className="small muted" role="status">Первое подключение может занять около минуты.</p>}
        {!telegramMode && <div className="demo-note"><ShieldCheck size={17} /><span>Демо-доступ для проверки · ПИН <strong>2026</strong></span></div>}
        <p className="login-client">Хотите обсудить проект? <a href="https://t.me/jump_crm_lead_bot" target="_blank" rel="noreferrer">Оставьте заявку боту ↗</a></p>
      </section>
    </div>
    <footer className="login-footer"><span>JUMP ADS · MINI CRM</span><span>Меньше рутины. Больше движения.</span></footer>
  </main>
}
