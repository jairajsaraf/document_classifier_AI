'use client'

import dynamic from 'next/dynamic'
import { useEffect, useState } from 'react'
import { ArrowLeft, ChevronLeft, ChevronRight } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { NativeSelect, NativeSelectOption } from '@/components/ui/native-select'
import { api, fmtDate, PageChip, SENSITIVITIES, SensitivityTag, TopBar, UnsafeTag, type Detail } from '@/components/bits'
import { cn } from 'cn'

const PdfPane = dynamic(() => import('@/components/pdf-pane'), {
  ssr: false,
  loading: () => <p className="p-6 text-sm text-text-2">Loading PDF viewer</p>,
})

// The demo has no accounts; feedback rows carry this fixed name.
const REVIEWER = 'demo reviewer'

export default function DocumentView() {
  const [id, setId] = useState<string | null>(null)
  const [doc, setDoc] = useState<Detail | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [page, setPage] = useState(1)
  const [pages, setPages] = useState(0)
  const [selected, setSelected] = useState<number | null>(null)
  const [overriding, setOverriding] = useState(false)
  const [status, setStatus] = useState<{ text: string; error?: boolean } | null>(null)

  const load = (docId: string) =>
    api<Detail>(`/api/documents/${docId}`).then(setDoc, (e: Error) => setError(e.message))

  useEffect(() => {
    // static export: the id is read in the browser, not from a dynamic route
    const docId = new URLSearchParams(window.location.search).get('id')
    if (!docId || !/^\d+$/.test(docId)) return setError('No document id in the address')
    setId(docId)
    load(docId)
  }, [])

  async function feedback(params: Record<string, string>) {
    setStatus({ text: 'Saving' })
    try {
      const q = new URLSearchParams({ document_id: id!, reviewer_name: REVIEWER, ...params })
      const r = await api<{ feedback_id: number }>(`/api/feedback?${q}`, { method: 'POST' })
      return r.feedback_id
    } catch (e) {
      setStatus({ text: (e as Error).message, error: true })
      return null
    }
  }

  async function approve() {
    const fid = await feedback({ feedback_type: 'confirmation' })
    if (fid) setStatus({ text: `Label approved. Saved as feedback #${fid}` })
  }

  async function override(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault()
    const f = new FormData(e.currentTarget)
    const fid = await feedback({
      feedback_type: 'correction',
      corrected_category: f.get('sensitivity') as string,
      corrected_unsafe: f.get('unsafe') as string,
      ...(f.get('note') ? { comments: f.get('note') as string } : {}),
    })
    if (fid) {
      setStatus({ text: `Override saved as feedback #${fid}` })
      setOverriding(false)
      load(id!)
    }
  }

  function cite(i: number) {
    const p = doc!.citations[i].page_number
    setSelected(i)
    if (p) setPage(p)
  }

  const c = doc?.classification
  const name = doc?.document.filename ?? ''
  const isPdf = /\.pdf$/i.test(name)
  const isImage = /\.(png|jpe?g)$/i.test(name)
  const sel = selected !== null ? doc?.citations[selected] : null
  const quote = sel && sel.page_number === page ? sel.evidence_text : null

  return (
    <div className="flex h-dvh flex-col">
      <TopBar>
        <a href="/" className="inline-flex items-center gap-2 text-sm text-text-2 transition-colors hover:text-foreground">
          <ArrowLeft aria-hidden className="size-4" strokeWidth={1.5} />
          Review queue
        </a>
      </TopBar>

      {error ? (
        <main className="p-6 text-sm text-redline">Could not open this document: {error}</main>
      ) : !doc ? (
        <main className="p-6 text-sm text-text-2">Loading</main>
      ) : (
        <main className="grid min-h-0 flex-1 grid-cols-1 lg:grid-cols-[minmax(0,1fr)_440px]">
          <section aria-label="Document pages" className="flex h-[75dvh] min-h-0 flex-col bg-muted lg:h-auto">
            {isPdf && (
              <div className="flex h-12 shrink-0 items-center justify-center gap-2 border-b bg-card">
                <Button variant="ghost" size="icon" aria-label="Previous page" disabled={page <= 1} onClick={() => setPage(page - 1)}>
                  <ChevronLeft aria-hidden strokeWidth={1.5} />
                </Button>
                <span className="min-w-28 text-center font-mono text-xs tabular-nums text-text-2" aria-live="polite">
                  Page {page} of {pages || '…'}
                </span>
                <Button variant="ghost" size="icon" aria-label="Next page" disabled={!pages || page >= pages} onClick={() => setPage(page + 1)}>
                  <ChevronRight aria-hidden strokeWidth={1.5} />
                </Button>
              </div>
            )}
            {/* focusable so keyboard users can scroll the page image (axe scrollable-region-focusable) */}
            <div tabIndex={0} className="min-h-0 flex-1 overflow-auto p-6 focus-visible:ring-3 focus-visible:ring-ring/50 focus-visible:outline-none focus-visible:ring-inset">
              {isPdf ? (
                <PdfPane url={`/api/documents/${id}/file`} page={page} quote={quote} onPages={setPages} />
              ) : isImage ? (
                // eslint-disable-next-line @next/next/no-img-element -- static export, no image optimisation
                <img src={`/api/documents/${id}/file`} alt={`Uploaded image ${name}`} className="mx-auto max-w-full rounded-md" />
              ) : (
                <p className="text-sm text-text-2">No preview for this file type</p>
              )}
            </div>
          </section>

          <aside className="min-h-0 overflow-auto border-l bg-card">
            <div className="flex flex-col gap-8 p-6">
              <header>
                <h1 className="text-xl font-medium break-words">{name}</h1>
                <p className="mt-1 font-mono text-xs tabular-nums text-muted-foreground">
                  {doc.document.page_count ?? '?'} pages · added {fmtDate(doc.document.created_at)}
                </p>
              </header>

              {!c ? (
                <p className={cn('text-sm', doc.document.status === 'failed' ? 'text-redline' : 'text-text-2')}>
                  {doc.document.status === 'failed' ? 'Classification failed for this file' : 'Not classified yet'}
                </p>
              ) : (
                <>
                  <dl className="grid grid-cols-3 gap-4 border-y py-4">
                    <div>
                      <dt className="text-xs text-text-2">Sensitivity</dt>
                      <dd className="mt-1 text-base font-medium"><SensitivityTag value={c.sensitivity} /></dd>
                    </div>
                    <div>
                      <dt className="text-xs text-text-2">Safety</dt>
                      <dd className="mt-1 text-base font-medium"><UnsafeTag value={c.unsafe} /></dd>
                    </div>
                    <div>
                      <dt className="text-xs text-text-2">Confidence</dt>
                      <dd className="mt-1 font-mono text-base tabular-nums">{c.confidence?.toFixed(2) ?? '–'}</dd>
                    </div>
                  </dl>

                  <section aria-labelledby="reasons-title">
                    <h2 id="reasons-title" className="text-sm font-medium">Reasons</h2>
                    {c.summary && <p className="mt-2 text-sm text-text-2">{c.summary}</p>}
                    {c.reasoning && <p className="mt-2 text-sm leading-6">{c.reasoning}</p>}
                  </section>

                  <section aria-labelledby="cites-title">
                    <h2 id="cites-title" className="text-sm font-medium">
                      Citations <span className="font-mono text-xs text-muted-foreground">{doc.citations.length}</span>
                    </h2>
                    <ul className="mt-2 flex flex-col gap-2">
                      {doc.citations.map((ct, i) => (
                        <li key={i}>
                          <button
                            type="button"
                            aria-pressed={selected === i}
                            onClick={() => cite(i)}
                            className={cn(
                              'flex w-full gap-3 rounded-lg border p-3 text-left transition-colors focus-visible:ring-3 focus-visible:ring-ring/50 focus-visible:outline-none',
                              selected === i ? 'border-redline/40 bg-redline-tint' : 'hover:bg-muted',
                            )}
                          >
                            <PageChip page={ct.page_number} verified={ct.verified} selected={selected === i} />
                            <span className="flex min-w-0 flex-col gap-1">
                              {ct.evidence_text && <q className="text-sm break-words">{ct.evidence_text}</q>}
                              {ct.description && <span className="text-xs text-text-2">{ct.description}</span>}
                              {ct.verified === false && (
                                <span className="text-xs text-muted-foreground">Quote not found in this page&apos;s extracted text</span>
                              )}
                            </span>
                          </button>
                        </li>
                      ))}
                    </ul>
                  </section>

                  <section aria-labelledby="review-title" className="border-t pt-6">
                    <h2 id="review-title" className="text-sm font-medium">Your review</h2>
                    <div className="mt-3 flex gap-2">
                      <Button onClick={approve}>Approve label</Button>
                      <Button variant="outline" aria-expanded={overriding} aria-controls="override-form" onClick={() => setOverriding(!overriding)}>
                        Override
                      </Button>
                    </div>
                    {overriding && (
                      <form id="override-form" onSubmit={override} className="mt-4 flex flex-col gap-3">
                        <div className="grid grid-cols-2 gap-3">
                          <label className="flex flex-col gap-1 text-xs text-text-2">
                            Sensitivity
                            <NativeSelect name="sensitivity" defaultValue={c.sensitivity} className="w-full">
                              {SENSITIVITIES.map((s) => <NativeSelectOption key={s} value={s}>{s}</NativeSelectOption>)}
                            </NativeSelect>
                          </label>
                          <label className="flex flex-col gap-1 text-xs text-text-2">
                            Safety
                            <NativeSelect name="unsafe" defaultValue={String(!!c.unsafe)} className="w-full">
                              <NativeSelectOption value="false">Safe</NativeSelectOption>
                              <NativeSelectOption value="true">Unsafe</NativeSelectOption>
                            </NativeSelect>
                          </label>
                        </div>
                        <label className="flex flex-col gap-1 text-xs text-text-2">
                          Why (optional)
                          <Input name="note" maxLength={500} />
                        </label>
                        <Button type="submit" className="self-start">Save override</Button>
                      </form>
                    )}
                    <p role="status" className={cn('mt-3 min-h-5 text-sm', status?.error ? 'text-redline' : 'text-text-2')}>
                      {status?.text}
                    </p>
                  </section>
                </>
              )}
            </div>
          </aside>
        </main>
      )}
    </div>
  )
}
