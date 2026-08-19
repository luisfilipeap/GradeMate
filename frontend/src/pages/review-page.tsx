import { ArrowLeft, Check, Copy, Pencil, ScanText, Undo2, X } from 'lucide-react'
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { toast } from 'sonner'

import { EmptyState } from '@/components/empty-state'
import { LaTeXPreview } from '@/components/latex-preview'
import { PageCanvas } from '@/components/page-canvas'
import { PageHeader } from '@/components/page-header'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { Textarea } from '@/components/ui/textarea'
import { api, type OcrLine, type Review, type Student } from '@/lib/api'
import { cn } from '@/lib/utils'

/** What the transcript shows for a line: the teacher's edit, or the OCR reading. */
function finalText(line: OcrLine): string {
  return line.corrected_text ?? line.text
}

/**
 * What the whole-transcript preview shows for a line: the LLM-normalized
 * LaTeX/Markdown when available, or the same fallback as the plain view.
 * `normalization_incomplete` always pairs with `normalized_text === null`,
 * so falling back to `finalText` here never renders a blank segment.
 */
function previewText(line: OcrLine): string {
  return line.normalized_text ?? finalText(line)
}

/**
 * Grading screen: the scanned page with the OCR boxes on the left, and on the
 * right the recognised lines to accept or rewrite, building the plain-text
 * version of the answer as the teacher goes.
 */
export function ReviewPage() {
  const { classId, assessmentId, submissionId } = useParams<{
    classId: string
    assessmentId: string
    submissionId: string
  }>()

  const [review, setReview] = useState<Review | null>(null)
  const [student, setStudent] = useState<Student | null>(null)
  const [pageIndex, setPageIndex] = useState(0)
  const [activeLineId, setActiveLineId] = useState<string | null>(null)
  const [activePanel, setActivePanel] = useState<'transcript' | 'regions'>('transcript')
  const [loading, setLoading] = useState(true)
  const [running, setRunning] = useState(false)

  useEffect(() => {
    if (!submissionId || !classId) return
    api
      .getReview(submissionId)
      .then(async (data) => {
        setReview(data)
        const students = await api.listStudents(classId)
        setStudent(students.find((item) => item.id === data.student_id) ?? null)
      })
      .catch((error: Error) => toast.error(error.message))
      .finally(() => setLoading(false))
  }, [submissionId, classId])

  const page = review?.pages[pageIndex]

  const patchLine = useCallback((updated: OcrLine) => {
    setReview((current) =>
      current
        ? {
            ...current,
            pages: current.pages.map((item) => ({
              ...item,
              lines: item.lines.map((line) => (line.id === updated.id ? updated : line)),
            })),
          }
        : current,
    )
  }, [])

  const transcript = useMemo(() => {
    if (!review) return ''
    return review.pages
      .map((item) => item.lines.filter((line) => line.accepted).map(previewText).join('\n'))
      .filter(Boolean)
      .join('\n\n')
  }, [review])

  const allLines = review?.pages.flatMap((item) => item.lines) ?? []
  const acceptedCount = allLines.filter((line) => line.accepted).length

  async function handleRunOcr() {
    if (!submissionId) return
    setRunning(true)
    try {
      const data = await api.runOcr(submissionId)
      setReview(data)
      setPageIndex(0)
      toast.success(`Recognised ${data.pages.reduce((sum, p) => sum + p.lines.length, 0)} regions.`)
    } catch (error) {
      toast.error((error as Error).message)
    } finally {
      setRunning(false)
    }
  }

  async function acceptAll() {
    const pending = allLines.filter((line) => !line.accepted)
    try {
      for (const line of pending) {
        patchLine(await api.updateLine(line.id, { accepted: true }))
      }
      toast.success(`Accepted ${pending.length} regions.`)
    } catch (error) {
      toast.error((error as Error).message)
    }
  }

  if (loading) return <p className="text-muted-foreground text-sm">Loading submission…</p>

  return (
    <>
      <Button
        variant="ghost"
        size="sm"
        className="mb-4 -ml-2"
        nativeButton={false}
        render={<Link to={`/classes/${classId}/assessments/${assessmentId}`} />}
      >
        <ArrowLeft className="size-4" />
        Back to the exam list
      </Button>

      <PageHeader
        title={student ? `Correcting ${student.full_name}` : 'Correcting exam'}
        description="Check what the OCR read on each region of the page, then accept or rewrite it."
      >
        {review && review.page_count > 0 ? (
          <>
            <Badge variant="secondary">
              {acceptedCount} of {allLines.length} regions
            </Badge>
            <Button variant="ghost" disabled={running} onClick={() => void handleRunOcr()}>
              <ScanText className="size-4" />
              {running ? 'Reading…' : 'Read again'}
            </Button>
          </>
        ) : null}
      </PageHeader>

      {!review || review.page_count === 0 ? (
        <EmptyState
          icon={ScanText}
          title="This exam has not been read yet"
          description="Running the OCR renders every page and asks the recognition service what is written on it. It takes a few seconds per page."
        >
          <Button disabled={running} onClick={() => void handleRunOcr()}>
            <ScanText className="size-4" />
            {running ? 'Reading the exam…' : 'Run OCR'}
          </Button>
        </EmptyState>
      ) : (
        <div className="grid gap-6 xl:grid-cols-[minmax(0,1fr)_460px]">
          <div className="space-y-3">
            {review.pages.length > 1 ? (
              <div className="flex flex-wrap items-center gap-1">
                {review.pages.map((item, index) => (
                  <Button
                    key={item.id}
                    size="sm"
                    variant={index === pageIndex ? 'secondary' : 'ghost'}
                    onClick={() => setPageIndex(index)}
                  >
                    Page {item.number}
                  </Button>
                ))}
              </div>
            ) : null}

            {page ? (
              <PageCanvas
                page={page}
                activeLineId={activeLineId}
                onHoverLine={setActiveLineId}
                onSelectLine={(lineId) => {
                  setActiveLineId(lineId)
                  setActivePanel('regions')
                }}
              />
            ) : null}
          </div>

          <div className="xl:sticky xl:top-6 xl:self-start">
            <Tabs
              value={activePanel}
              onValueChange={(value) => setActivePanel(value as 'transcript' | 'regions')}
            >
              <TabsList>
                <TabsTrigger value="transcript">Transcript</TabsTrigger>
                <TabsTrigger value="regions">Recognised regions</TabsTrigger>
              </TabsList>

              <TabsContent value="transcript" className="mt-4 space-y-2">
                <div className="flex items-center justify-end">
                  <Button
                    variant="ghost"
                    size="sm"
                    disabled={!transcript}
                    onClick={() => {
                      void navigator.clipboard.writeText(transcript)
                      toast.success('Transcript copied.')
                    }}
                  >
                    <Copy className="size-4" />
                    Copy
                  </Button>
                </div>
                <LaTeXPreview
                  text={transcript}
                  emptyText="Accept a line to start building the transcript."
                  className="bg-muted/50 max-h-[70vh] overflow-auto rounded-lg border p-3"
                />
              </TabsContent>

              <TabsContent value="regions" className="mt-4 space-y-2">
                <div className="flex items-center justify-end">
                  <Button variant="ghost" size="sm" onClick={() => void acceptAll()}>
                    <Check className="size-4" />
                    Accept all
                  </Button>
                </div>
                <ul className="max-h-[70vh] space-y-1 overflow-y-auto pr-1">
                  {page?.lines.map((line) => (
                    <LineRow
                      key={line.id}
                      line={line}
                      active={line.id === activeLineId}
                      onHover={setActiveLineId}
                      onPatched={patchLine}
                    />
                  ))}
                </ul>
              </TabsContent>
            </Tabs>
          </div>
        </div>
      )}
    </>
  )
}

function LineRow({
  line,
  active,
  onHover,
  onPatched,
}: {
  line: OcrLine
  active: boolean
  onHover: (lineId: string | null) => void
  onPatched: (line: OcrLine) => void
}) {
  const [editing, setEditing] = useState(false)
  const [draft, setDraft] = useState(finalText(line))
  const inputRef = useRef<HTMLTextAreaElement>(null)

  useEffect(() => {
    if (editing) inputRef.current?.focus()
  }, [editing])

  async function patch(input: { corrected_text?: string | null; accepted?: boolean }) {
    try {
      onPatched(await api.updateLine(line.id, input))
    } catch (error) {
      toast.error((error as Error).message)
    }
  }

  async function save() {
    const value = draft.trim()
    await patch({ corrected_text: value === line.text ? null : value, accepted: true })
    setEditing(false)
  }

  return (
    <li
      onMouseEnter={() => onHover(line.id)}
      onMouseLeave={() => onHover(null)}
      className={cn(
        'rounded-md border px-2 py-1.5 transition-colors',
        active ? 'border-sky-500 bg-sky-500/5' : 'border-transparent hover:bg-muted/60',
      )}
    >
      {editing ? (
        <div className="flex items-start gap-1">
          <Textarea
            ref={inputRef}
            value={draft}
            rows={Math.min(draft.split('\n').length + 1, 10)}
            className="font-mono text-xs"
            onChange={(event) => setDraft(event.target.value)}
            onKeyDown={(event) => {
              // Blocks are multi-line, so Enter inserts a newline and the save
              // shortcut needs a modifier.
              if (event.key === 'Enter' && (event.metaKey || event.ctrlKey)) void save()
              if (event.key === 'Escape') setEditing(false)
            }}
          />
          <Button size="icon-sm" variant="ghost" aria-label="Save" onClick={() => void save()}>
            <Check className="size-4" />
          </Button>
          <Button
            size="icon-sm"
            variant="ghost"
            aria-label="Cancel"
            onClick={() => {
              setDraft(finalText(line))
              setEditing(false)
            }}
          >
            <X className="size-4" />
          </Button>
        </div>
      ) : (
        <div className="flex items-start gap-2">
          <div className="min-w-0 flex-1">
            {line.label && line.label !== 'text' ? (
              <span className="text-muted-foreground mb-0.5 block text-[10px] uppercase">
                {line.label.replace(/_/g, ' ')}
              </span>
            ) : null}
            <span
              className={cn(
                'block font-mono text-xs break-words whitespace-pre-wrap',
                line.accepted ? 'text-foreground' : 'text-muted-foreground',
              )}
            >
              {finalText(line)}
            </span>
          </div>
          <div className="flex shrink-0 items-center">
            <Button
              size="icon-sm"
              variant="ghost"
              aria-label={line.accepted ? 'Undo acceptance' : 'Accept line'}
              onClick={() => void patch({ accepted: !line.accepted })}
            >
              {line.accepted ? <Undo2 className="size-3.5" /> : <Check className="size-4" />}
            </Button>
            <Button
              size="icon-sm"
              variant="ghost"
              aria-label="Correct line"
              onClick={() => {
                setDraft(finalText(line))
                setEditing(true)
              }}
            >
              <Pencil className="size-3.5" />
            </Button>
          </div>
        </div>
      )}
      {line.corrected_text !== null ? (
        <p className="text-muted-foreground mt-1 font-mono text-[10px] line-through">{line.text}</p>
      ) : null}
    </li>
  )
}
