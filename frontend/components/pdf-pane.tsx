'use client'

// Loaded with ssr: false. workerSrc must be set in the same module that renders <Document>/<Page>
// (https://github.com/wojtekmaj/react-pdf/blob/main/packages/react-pdf/README.md).
import { useCallback, useEffect, useRef, useState } from 'react'
import { Document, Page, pdfjs } from 'react-pdf'
import 'react-pdf/dist/Page/TextLayer.css'

pdfjs.GlobalWorkerOptions.workerSrc = new URL('pdfjs-dist/build/pdf.worker.min.mjs', import.meta.url).toString()

const norm = (s: string) => s.toLowerCase().replace(/[^a-z0-9]+/g, ' ').trim()
const esc = (s: string) => s.replace(/[&<>"']/g, (c) => `&#${c.charCodeAt(0)};`)

export default function PdfPane({
  url, page, quote, onPages,
}: { url: string; page: number; quote: string | null; onPages: (n: number) => void }) {
  const box = useRef<HTMLDivElement>(null)
  const [width, setWidth] = useState(0)
  useEffect(() => {
    const el = box.current!
    const ro = new ResizeObserver(([e]) => setWidth(Math.min(Math.floor(e.contentRect.width), 880)))
    ro.observe(el)
    return () => ro.disconnect()
  }, [])

  // ponytail: marks whole text items that occur inside the quote; quotes split across items mark partially.
  const q = quote ? norm(quote) : ''
  const renderer = useCallback(
    ({ str }: { str: string }) => {
      const n = norm(str)
      return q && n.length >= 4 && q.includes(n) ? `<mark>${esc(str)}</mark>` : esc(str)
    },
    [q],
  )

  return (
    <div ref={box} className="mx-auto w-full max-w-[880px]">
      {width > 0 && (
        <Document
          // v11 suspends by default and throws load errors to the nearest boundary, which
          // took down the whole view for a broken file; use the loading/error props instead
          suspense={false}
          file={url}
          onLoadSuccess={({ numPages }) => onPages(numPages)}
          loading={<p className="p-6 text-sm text-text-2">Loading PDF</p>}
          error={<p className="p-6 text-sm text-redline">Could not load this PDF</p>}
        >
          <Page
            pageNumber={page}
            width={width}
            renderAnnotationLayer={false}
            customTextRenderer={renderer}
            className="overflow-hidden rounded-md shadow-[0_1px_2px_rgba(0,0,0,0.05),0_8px_24px_rgba(0,0,0,0.06)]"
            loading={<div style={{ height: width * 1.3 }} className="bg-card" />}
          />
        </Document>
      )}
    </div>
  )
}
