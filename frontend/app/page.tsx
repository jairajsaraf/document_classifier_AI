'use client'

import { useCallback, useEffect, useState } from 'react'
import {
  columnFilteringFeature,
  createFilteredRowModel,
  createSortedRowModel,
  filterFn_equals,
  filterFn_includesString,
  rowSortingFeature,
  sortFn_basic,
  sortFn_text,
  tableFeatures,
  useTable,
  type ColumnDef,
} from '@tanstack/react-table'
import { ArrowDown, ArrowUp, ChevronsUpDown } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { NativeSelect, NativeSelectOption } from '@/components/ui/native-select'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { api, fmtDate, SENSITIVITIES, SensitivityTag, STATUS, TopBar, UnsafeTag, type DocRow } from '@/components/bits'

// Source: eval/runs_phase3/combo/metrics.md (shipped prompt, claude-haiku-5-5, 3 runs) and docs/FEATURES.md.
const EVAL = [
  { label: 'Test cases labelled correctly', value: '12/12', note: 'TC1–TC4, 3 runs each · vs 3/12 with the previous prompt' },
  { label: 'Sensitive documents labelled Public', value: '0%', note: 'TC1–TC4 · vs 67% with the previous prompt' },
  { label: 'Synthetic set labelled correctly', value: '63/72', note: '24 documents, 3 runs each' },
  { label: 'Quotes found on the cited page', value: '31%', note: '28 of 91 citations on TC1–TC4' },
]

const features = tableFeatures({
  rowSortingFeature,
  columnFilteringFeature,
  sortedRowModel: createSortedRowModel(),
  filteredRowModel: createFilteredRowModel(),
  sortFns: { basic: sortFn_basic, text: sortFn_text },
  filterFns: { includesString: filterFn_includesString, equals: filterFn_equals },
})

const RANK = { Public: 0, Confidential: 1, 'Highly Sensitive': 2 }

const columns: ColumnDef<typeof features, DocRow>[] = [
  {
    accessorKey: 'filename',
    header: 'Document',
    sortFn: 'text',
    filterFn: 'includesString',
    cell: ({ row }) => (
      <a href={`/document/?id=${row.original.id}`} className="font-medium underline-offset-4 hover:underline">
        {row.original.filename}
      </a>
    ),
  },
  {
    id: 'sensitivity',
    accessorFn: (r) => r.sensitivity ?? '',
    header: 'Label',
    filterFn: 'equals',
    sortFn: (a, b) => (RANK[a.original.sensitivity!] ?? -1) - (RANK[b.original.sensitivity!] ?? -1),
    cell: ({ row }) => <SensitivityTag value={row.original.sensitivity} />,
  },
  {
    id: 'unsafe',
    accessorFn: (r) => (r.unsafe === null ? -1 : Number(r.unsafe)),
    header: 'Safety',
    sortFn: 'basic',
    cell: ({ row }) => <UnsafeTag value={row.original.unsafe} />,
  },
  {
    id: 'status',
    accessorFn: (r) => STATUS[r.status] ?? r.status,
    header: 'Status',
    sortFn: 'text',
    cell: ({ getValue }) => <span className="text-text-2">{getValue() as string}</span>,
  },
  {
    accessorKey: 'confidence',
    header: 'Confidence',
    sortFn: 'basic',
    cell: ({ row }) => (
      <span className="font-mono tabular-nums text-text-2">{row.original.confidence?.toFixed(2) ?? '–'}</span>
    ),
  },
  {
    accessorKey: 'created_at',
    header: 'Added',
    sortFn: 'text',
    cell: ({ row }) => <span className="font-mono text-xs tabular-nums text-muted-foreground">{fmtDate(row.original.created_at)}</span>,
  },
]

export default function Queue() {
  const [docs, setDocs] = useState<DocRow[] | null>(null)
  const [loadError, setLoadError] = useState<string | null>(null)
  const [status, setStatus] = useState<{ text: string; error?: boolean } | null>(null)
  const [busy, setBusy] = useState(false)

  const load = useCallback(() => {
    api<{ documents: DocRow[] }>('/api/documents').then(
      (r) => { setDocs(r.documents); setLoadError(null) },
      (e: Error) => setLoadError(e.message),
    )
  }, [])
  useEffect(load, [load])

  const table = useTable({
    features,
    columns,
    data: docs ?? [],
    initialState: { sorting: [{ id: 'created_at', desc: true }] },
  })

  async function upload(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault()
    const form = e.currentTarget
    if (!(new FormData(form).get('file') as File | null)?.size) return setStatus({ text: 'Choose a PDF first', error: true })
    setBusy(true)
    try {
      setStatus({ text: 'Uploading' })
      const up = await api<{ document_id: number }>('/api/documents/upload', { method: 'POST', body: new FormData(form) })
      load()
      setStatus({ text: 'Classifying, usually 15 to 30 seconds' })
      await api(`/api/documents/${up.document_id}/classify`, { method: 'POST' })
      setStatus({ text: 'Classified and added to the queue' })
      form.reset()
    } catch (err) {
      setStatus({ text: (err as Error).message, error: true })
    } finally {
      setBusy(false)
      load()
    }
  }

  const rows = table.getRowModel().rows
  const nameFilter = (table.getColumn('filename')?.getFilterValue() as string) ?? ''
  const labelFilter = (table.getColumn('sensitivity')?.getFilterValue() as string) ?? ''

  return (
    <>
      <TopBar />
      <main className="mx-auto max-w-[1440px] px-6 py-8">
        <section aria-labelledby="eval-title">
          <h2 id="eval-title" className="text-sm text-text-2">Evaluation of the running prompt</h2>
          <dl className="mt-3 grid grid-cols-1 rounded-xl border bg-card sm:grid-cols-2 lg:grid-cols-4">
            {EVAL.map((m, i) => (
              <div key={m.label} className={`flex flex-col gap-1 p-5 ${i ? 'border-t sm:border-t-0 sm:border-l' : ''}`}>
                <dt className="text-sm text-text-2">{m.label}</dt>
                <dd className="font-mono text-3xl font-medium tabular-nums">{m.value}</dd>
                <dd className="text-xs text-muted-foreground">{m.note}</dd>
              </div>
            ))}
          </dl>
        </section>

        <section aria-labelledby="queue-title" className="mt-12">
          <div className="flex flex-wrap items-end justify-between gap-6">
            <div>
              <h1 id="queue-title" className="text-2xl font-medium">Review queue</h1>
              <p className="mt-1 text-sm text-text-2">
                {docs ? `${docs.length} documents · open one to see the evidence, then approve or override the label` : ' '}
              </p>
            </div>
            <form onSubmit={upload} className="flex w-full max-w-md flex-col gap-2">
              <div className="flex gap-2">
                <Input type="file" name="file" accept="application/pdf,.pdf" aria-label="PDF to classify" disabled={busy} className="bg-card" />
                <Button type="submit" disabled={busy}>Upload and classify</Button>
              </div>
              <p className="text-xs text-text-2">
                Do not upload real personal data. The text is sent to the Anthropic API for classification.
              </p>
            </form>
          </div>
          <p role="status" className={`mt-3 min-h-5 text-sm ${status?.error ? 'text-redline' : 'text-text-2'}`}>
            {status?.text}
          </p>

          <div className="mt-3 flex flex-wrap items-center gap-2">
            <Input
              placeholder="Filter by name"
              aria-label="Filter by document name"
              value={nameFilter}
              onChange={(e) => table.getColumn('filename')?.setFilterValue(e.target.value)}
              className="w-64 bg-card"
            />
            <NativeSelect
              aria-label="Filter by label"
              value={labelFilter}
              onChange={(e) => table.getColumn('sensitivity')?.setFilterValue(e.target.value || undefined)}
              className="bg-card"
            >
              <NativeSelectOption value="">All labels</NativeSelectOption>
              {SENSITIVITIES.map((s) => <NativeSelectOption key={s} value={s}>{s}</NativeSelectOption>)}
            </NativeSelect>
          </div>

          <div className="mt-3 overflow-hidden rounded-xl border bg-card">
            <Table>
              <TableHeader>
                {table.getHeaderGroups().map((hg) => (
                  <TableRow key={hg.id} className="hover:bg-transparent">
                    {hg.headers.map((h) => {
                      const dir = h.column.getIsSorted()
                      const Icon = dir === 'asc' ? ArrowUp : dir === 'desc' ? ArrowDown : ChevronsUpDown
                      return (
                        <TableHead
                          key={h.id}
                          aria-sort={dir === 'asc' ? 'ascending' : dir === 'desc' ? 'descending' : 'none'}
                          className="h-10 px-4 font-normal text-text-2"
                        >
                          <button
                            type="button"
                            onClick={h.column.getToggleSortingHandler()}
                            className="-mx-1 inline-flex items-center gap-1 rounded-sm px-1 transition-colors hover:text-foreground focus-visible:ring-3 focus-visible:ring-ring/50 focus-visible:outline-none"
                          >
                            <table.FlexRender header={h} />
                            <Icon aria-hidden className={`size-4 ${dir ? 'text-foreground' : 'text-muted-foreground'}`} strokeWidth={1.5} />
                          </button>
                        </TableHead>
                      )
                    })}
                  </TableRow>
                ))}
              </TableHeader>
              <TableBody>
                {rows.map((row) => (
                  <TableRow key={row.id} className="h-11">
                    {row.getAllCells().map((cell) => (
                      <TableCell key={cell.id} className="px-4">
                        <table.FlexRender cell={cell} />
                      </TableCell>
                    ))}
                  </TableRow>
                ))}
                {!rows.length && (
                  <TableRow className="hover:bg-transparent">
                    <TableCell colSpan={columns.length} className="h-24 px-4 text-text-2">
                      {loadError ? `Could not load the queue: ${loadError}` : !docs ? 'Loading' : docs.length ? 'No documents match these filters' : 'No documents yet. Upload a PDF to start'}
                    </TableCell>
                  </TableRow>
                )}
              </TableBody>
            </Table>
          </div>
        </section>
      </main>
    </>
  )
}
