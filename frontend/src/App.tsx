import { useCallback, useEffect, useState } from 'react'
import { api, ApiError, errorText, savedToken, setToken, type User } from './api/client'
import Login from './pages/Login'
import Dashboard from './pages/Dashboard'
import { initializeTelegram, telegram } from './utils/telegram'

export default function App() {
  const [user, setUser] = useState<User | null>(null)
  const [busy, setBusy] = useState(true)
  const [error, setError] = useState('')
  const [attempt, setAttempt] = useState(0)
  const isTelegram = Boolean(telegram())

  const logout = useCallback(() => {
    setToken(null)
    setUser(null)
    setError('')
  }, [])

  useEffect(() => {
    initializeTelegram()
    let active = true
    const restore = async () => {
      setBusy(true)
      setError('')
      try {
        const initData = telegram()?.initData
        if (initData) {
          const result = await api.telegram(initData)
          if (!active) return
          setToken(result.access_token)
        } else {
          const saved = savedToken()
          if (!saved) return
          setToken(saved, true)
        }
        const current = await api.me()
        if (active) setUser(current)
      } catch (e) {
        if (active) {
          setToken(null)
          setError(e instanceof ApiError && e.status === 401 && isTelegram
            ? 'Данные входа устарели. Закройте приложение и откройте его заново в Telegram.'
            : errorText(e))
        }
      } finally { if (active) setBusy(false) }
    }
    void restore()
    return () => { active = false }
  }, [attempt, isTelegram])

  useEffect(() => {
    const expire = () => {
      logout()
      setError('Сессия завершена. Войдите снова.')
    }
    window.addEventListener('crm:unauthorized', expire)
    return () => window.removeEventListener('crm:unauthorized', expire)
  }, [logout])

  async function login(pin: string) {
    setBusy(true)
    setError('')
    try {
      const result = await api.pin(pin)
      setToken(result.access_token, true)
      setUser(await api.me())
    } catch (e) {
      setToken(null)
      setError(e instanceof ApiError && e.status === 401 ? 'Неверный ПИН-код. Попробуйте ещё раз.' : errorText(e))
    } finally { setBusy(false) }
  }

  return user
    ? <Dashboard user={user} onLogout={logout} />
    : <Login busy={busy} error={error} telegramMode={isTelegram} onLogin={login} onRetry={() => setAttempt(n => n + 1)} />
}
