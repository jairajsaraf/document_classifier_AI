'use client'

import { useEffect, useState } from 'react'
import { Check } from 'lucide-react'
import { cn } from 'cn'

export type Sensitivity = 'Public' | 'Confidential' | 'Highly Sensitive'
export const SENSITIVITIES: Sensitivity[] = ['Public', 'Confidential', 'Highly Sensitive']

export type DocRow = {
  id: number
  filename: string
  status: string
  sensitivity: Sensitivity | null
  unsafe: boolean | null
  confidence: number | null
  requires_review: boolean
  created_at: string
}

export type Citation = {
  page_number: number | null
  evidence_type: string
  evidence_text: string | null
  description: string
  verified: boolean | null
}

export type Detail = {
  document: { id: number; filename: string; status: string; page_count: number | null; created_at: string }
  classification: {
    sensitivity: Sensitivity
    unsafe: boolean | null
    confidence: number | null
    summary: string | null
    reasoning: string | null
  } | null
  citations: Citation[]
}

/** Same-origin call to the FastAPI backend; throws with the server's message. */
export async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(path, init)
  const body = await res.json().catch(() => null)
  if (!res.ok) {
    const d = body?.detail
    throw new Error(typeof d === 'string' ? d : d?.error_detail ?? d?.error ?? `Request failed (${res.status})`)
  }
  return body as T
}

// the API sends naive UTC timestamps
export function fmtDate(iso: string) {
  const d = new Date(/[zZ]|[+-]\d\d:\d\d$/.test(iso) ? iso : iso + 'Z')
  return d.toLocaleString('en-GB', { day: 'numeric', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit' })
}

export const STATUS: Record<string, string> = {
  pending_review: 'Needs review',
  completed: 'Classified',
  failed: 'Failed',
  uploaded: 'Not classified',
  preprocessing: 'Classifying',
  classifying: 'Classifying',
}

export function TopBar({ children }: { children?: React.ReactNode }) {
  const [model, setModel] = useState<string | null>(null)
  useEffect(() => {
    api<{ model: string }>('/api').then((r) => setModel(r.model), () => setModel(null))
  }, [])
  return (
    <header className="flex h-14 items-center gap-4 border-b bg-card px-6 whitespace-nowrap">
      <a href="/" className="text-base font-medium">Document review</a>
      {children}
      {/* on phones the document view needs the room for its back link; the queue keeps the model */}
      <span className={cn('ml-auto text-xs text-muted-foreground', children && 'max-sm:hidden')}>
        Model <span className="font-mono text-text-2">{model ?? '…'}</span>
      </span>
    </header>
  )
}

export function SensitivityTag({ value, className }: { value: Sensitivity | null; className?: string }) {
  if (!value) return <span className={cn('text-muted-foreground', className)}>Not classified</span>
  const high = value === 'Highly Sensitive'
  return (
    <span className={cn('inline-flex items-center gap-2', high && 'text-redline', className)}>
      <span
        aria-hidden
        className={cn(
          'size-2 shrink-0 rounded-full',
          value === 'Public' && 'border border-muted-foreground',
          value === 'Confidential' && 'bg-text-2',
          high && 'bg-redline',
        )}
      />
      {value}
    </span>
  )
}

export function UnsafeTag({ value }: { value: boolean | null }) {
  if (value === null) return <span className="text-muted-foreground">–</span>
  return value ? <span className="text-redline">Unsafe</span> : <span className="text-text-2">Safe</span>
}

/** The signature: a mono page reference, ticked when the quote was found on that page. */
export function PageChip({ page, verified, selected }: { page: number | null; verified: boolean | null; selected?: boolean }) {
  return (
    <span
      className={cn(
        'inline-flex h-6 shrink-0 items-center gap-1 rounded-sm border px-1.5 font-mono text-xs tabular-nums',
        selected ? 'border-redline/40 bg-redline-tint text-redline' : 'bg-card text-text-2',
      )}
    >
      p.{page ?? '?'}
      {verified && <Check aria-label="quote found on this page" className="size-3" strokeWidth={2} />}
    </span>
  )
}
