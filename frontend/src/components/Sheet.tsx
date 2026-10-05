import { Drawer } from 'vaul'
import { X } from 'lucide-react'
import { useEffect, type ReactNode } from 'react'
import { telegram } from '../utils/telegram'

export default function Sheet({ title, description, busy = false, onClose, children }: {
  title: string; description: string; busy?: boolean; onClose: () => void; children: ReactNode
}) {
  useEffect(() => {
    const button = telegram()?.BackButton
    const close = () => { if (!busy) onClose() }
    button?.show()
    button?.onClick(close)
    return () => { button?.offClick(close); button?.hide() }
  }, [busy, onClose])
  return <Drawer.Root open onOpenChange={open => { if (!open && !busy) onClose() }} dismissible={!busy}>
    <Drawer.Portal>
      <Drawer.Overlay className="sheet-overlay" />
      <Drawer.Content className="sheet" aria-describedby="sheet-description">
        <div className="sheet-handle" aria-hidden="true" />
        <header className="sheet-header"><div><Drawer.Title>{title}</Drawer.Title>
          <Drawer.Description id="sheet-description">{description}</Drawer.Description></div>
          <button className="icon-button" aria-label="Закрыть" onClick={onClose} disabled={busy}><X size={20} /></button>
        </header>
        {children}
      </Drawer.Content>
    </Drawer.Portal>
  </Drawer.Root>
}
