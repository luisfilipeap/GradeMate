import 'katex/dist/katex.min.css'

import renderMathInElement from 'katex/contrib/auto-render'
import { useEffect, useRef } from 'react'

import { cn } from '@/lib/utils'

const KATEX_DELIMITERS = [
  { left: '$$', right: '$$', display: true },
  { left: '\\[', right: '\\]', display: true },
  { left: '$', right: '$', display: false },
  { left: '\\(', right: '\\)', display: false },
]

/**
 * Renders arbitrary text as a block, running KaTeX's auto-render over it so
 * `$…$`/`$$…$$` segments become formulas while plain text stays as-is. Runs
 * again on every `text` change, so edits show up immediately.
 */
export function LaTeXPreview({
  text,
  emptyText,
  className,
}: {
  text: string
  /** Shown instead of the text itself when `text` is empty. */
  emptyText?: string
  className?: string
}) {
  const containerRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const container = containerRef.current
    if (!container) return
    renderMathInElement(container, {
      delimiters: KATEX_DELIMITERS,
      throwOnError: false,
    })
  }, [text])

  return (
    <div ref={containerRef} className={cn('text-sm whitespace-pre-wrap', className)}>
      {text || emptyText}
    </div>
  )
}
