interface TelegramButton {
  setText(text: string): void
  show(): void
  hide(): void
  onClick(callback: () => void): void
  offClick(callback: () => void): void
}
interface TelegramWebApp {
  initData: string
  ready(): void
  expand(): void
  MainButton: TelegramButton
  BackButton: Omit<TelegramButton, 'setText'>
}
declare global {
  interface Window { Telegram?: { WebApp?: TelegramWebApp } }
}

export function telegram(): TelegramWebApp | undefined {
  const app = window.Telegram?.WebApp
  return app?.initData ? app : undefined
}

export function initializeTelegram(): void {
  const app = telegram()
  app?.ready()
  app?.expand()
}
