import { useEffect, useRef, type ReactNode } from 'react'

/** Native disclosure with a bounded floating surface; Escape returns to its trigger. */
export function Popover({ label, children, className = '', title }: { label: ReactNode; children: ReactNode; className?: string; title?: string }) {
  const ref = useRef<HTMLDetailsElement>(null)
  useEffect(() => {
    const closeOutside = (event: PointerEvent) => {
      if (ref.current?.open && event.target instanceof Node && !ref.current.contains(event.target)) ref.current.open = false
    }
    document.addEventListener('pointerdown', closeOutside)
    return () => document.removeEventListener('pointerdown', closeOutside)
  }, [])
  return <details ref={ref} className={`bench-popover ${className}`} onKeyDown={event => {
    if (event.key === 'Escape' && ref.current?.open && !event.defaultPrevented) {
      event.preventDefault(); event.stopPropagation(); if (ref.current) ref.current.open = false
      ref.current?.querySelector('summary')?.focus()
    }
  }}><summary title={title}>{label}</summary><div className="bench-popover-surface">{children}</div></details>
}
