import { Check, Pencil, Plus, ScanText, Trash2, Upload, X } from 'lucide-react'
import { useCallback, useEffect, useRef, useState } from 'react'
import { toast } from 'sonner'

import { LaTeXPreview } from '@/components/latex-preview'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Textarea } from '@/components/ui/textarea'
import {
  ApiError,
  api,
  type Assessment,
  type Question,
  type QuestionDraft,
  type QuestionInput,
} from '@/lib/api'

/** A candidate produced by `extractQuestions`, tagged with a client-only id for list bookkeeping. */
type DraftItem = QuestionDraft & { id: string }

function makeDraftId(): string {
  return typeof crypto !== 'undefined' && 'randomUUID' in crypto
    ? crypto.randomUUID()
    : Math.random().toString(36).slice(2)
}

/** Message shown for a `409` from `createQuestion`/`updateQuestion` on a duplicate number. */
function duplicateNumberMessage(number: string): string {
  return `Question ${number} already exists in this assessment. Change the number and try again.`
}

/**
 * "Question paper" section of the assessment page: upload/replace the paper,
 * extract candidate questions from it, and manage the assessment's
 * `Question` records (manual add, inline edit, delete).
 */
export function QuestionPaperSection({
  assessment,
  onAssessmentChange,
}: {
  assessment: Assessment
  onAssessmentChange: (assessment: Assessment) => void
}) {
  const [questions, setQuestions] = useState<Question[]>([])
  const [drafts, setDrafts] = useState<DraftItem[]>([])
  const [loading, setLoading] = useState(true)
  const [uploading, setUploading] = useState(false)
  const [extracting, setExtracting] = useState(false)
  const fileInputRef = useRef<HTMLInputElement>(null)

  const refreshQuestions = useCallback(async () => {
    setQuestions(await api.listQuestions(assessment.id))
  }, [assessment.id])

  useEffect(() => {
    refreshQuestions()
      .catch((error: Error) => toast.error(error.message))
      .finally(() => setLoading(false))
  }, [refreshQuestions])

  async function handleFile(event: React.ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0]
    // Let the same file be picked again after a failed upload.
    event.target.value = ''
    if (!file) return
    setUploading(true)
    try {
      await api.uploadQuestionPaper(assessment.id, file)
      // The upload endpoint returns no body; re-reading the assessment is what
      // lets the filename/link show up without a page reload.
      onAssessmentChange(await api.getAssessment(assessment.id))
      toast.success('Question paper uploaded.')
    } catch (error) {
      toast.error((error as Error).message)
    } finally {
      setUploading(false)
    }
  }

  async function handleExtract() {
    setExtracting(true)
    try {
      const result = await api.extractQuestions(assessment.id)
      setDrafts(result.questions.map((question) => ({ ...question, id: makeDraftId() })))
      if (result.questions.length === 0) {
        toast.error('No candidate questions were found in the question paper.')
      } else {
        toast.success(`Found ${result.questions.length} candidate question(s) to review.`)
      }
    } catch (error) {
      toast.error((error as Error).message)
    } finally {
      setExtracting(false)
    }
  }

  function updateDraft(id: string, patch: Partial<QuestionInput>) {
    setDrafts((current) => current.map((draft) => (draft.id === id ? { ...draft, ...patch } : draft)))
  }

  function discardDraft(id: string) {
    setDrafts((current) => current.filter((draft) => draft.id !== id))
  }

  async function approveDraft(draft: DraftItem) {
    try {
      const question = await api.createQuestion(assessment.id, {
        number: draft.number,
        statement: draft.statement,
      })
      setQuestions((current) => [...current, question].sort((a, b) => a.position - b.position))
      discardDraft(draft.id)
      toast.success(`Question ${question.number} approved.`)
    } catch (error) {
      if (error instanceof ApiError && error.status === 409) {
        // The draft must stay available for the teacher to fix the number
        // and retry, not disappear as if it had been discarded.
        toast.error(duplicateNumberMessage(draft.number))
        return
      }
      toast.error((error as Error).message)
    }
  }

  async function addQuestion(input: QuestionInput): Promise<boolean> {
    try {
      const question = await api.createQuestion(assessment.id, input)
      setQuestions((current) => [...current, question].sort((a, b) => a.position - b.position))
      toast.success(`Question ${question.number} added.`)
      return true
    } catch (error) {
      if (error instanceof ApiError && error.status === 409) {
        toast.error(duplicateNumberMessage(input.number))
        return false
      }
      toast.error((error as Error).message)
      return false
    }
  }

  async function updateQuestion(question: Question, patch: Partial<QuestionInput>): Promise<boolean> {
    try {
      const updated = await api.updateQuestion(question.id, patch)
      setQuestions((current) => current.map((item) => (item.id === updated.id ? updated : item)))
      return true
    } catch (error) {
      if (error instanceof ApiError && error.status === 409) {
        toast.error(duplicateNumberMessage(patch.number ?? question.number))
        return false
      }
      toast.error((error as Error).message)
      return false
    }
  }

  async function deleteQuestion(question: Question) {
    try {
      await api.deleteQuestion(question.id)
      setQuestions((current) => current.filter((item) => item.id !== question.id))
      toast.success(`Question ${question.number} removed.`)
    } catch (error) {
      toast.error((error as Error).message)
    }
  }

  const hasPaper = assessment.question_paper_original_filename !== null

  return (
    <section className="mb-6 space-y-4">
      <div className="bg-background flex flex-wrap items-center justify-between gap-3 rounded-lg border p-4">
        <div>
          <h2 className="font-heading text-sm font-semibold">Question paper</h2>
          {hasPaper ? (
            <p className="text-muted-foreground mt-1 flex flex-wrap items-center gap-1.5 text-sm">
              <a
                className="text-foreground underline underline-offset-4"
                href={api.questionPaperFileUrl(assessment.id)}
                target="_blank"
                rel="noreferrer"
              >
                {assessment.question_paper_original_filename}
              </a>
              {assessment.question_paper_page_count ? (
                <span>
                  ({assessment.question_paper_page_count} page
                  {assessment.question_paper_page_count === 1 ? '' : 's'})
                </span>
              ) : null}
            </p>
          ) : (
            <p className="text-muted-foreground mt-1 text-sm">No question paper uploaded yet.</p>
          )}
        </div>
        <div className="flex items-center gap-2">
          <input
            ref={fileInputRef}
            type="file"
            accept="application/pdf"
            className="hidden"
            onChange={(event) => void handleFile(event)}
          />
          <Button
            variant={hasPaper ? 'outline' : 'default'}
            size="sm"
            disabled={uploading}
            onClick={() => fileInputRef.current?.click()}
          >
            <Upload className="size-4" />
            {hasPaper ? 'Replace' : 'Upload PDF'}
          </Button>
          <Button
            variant="outline"
            size="sm"
            disabled={!hasPaper || extracting}
            onClick={() => void handleExtract()}
          >
            <ScanText className="size-4" />
            {extracting ? 'Extracting…' : 'Extract questions'}
          </Button>
        </div>
      </div>

      {drafts.length > 0 ? (
        <div className="space-y-2 rounded-lg border border-dashed p-4">
          <h3 className="text-muted-foreground text-xs font-semibold uppercase">
            Extraction candidates — review before approving
          </h3>
          <ul className="space-y-2">
            {drafts.map((draft) => (
              <DraftRow
                key={draft.id}
                draft={draft}
                onChange={(patch) => updateDraft(draft.id, patch)}
                onApprove={() => void approveDraft(draft)}
                onDiscard={() => discardDraft(draft.id)}
              />
            ))}
          </ul>
        </div>
      ) : null}

      {!loading ? (
        <QuestionList
          questions={questions}
          onAdd={addQuestion}
          onUpdate={updateQuestion}
          onDelete={(question) => void deleteQuestion(question)}
        />
      ) : null}
    </section>
  )
}

function DraftRow({
  draft,
  onChange,
  onApprove,
  onDiscard,
}: {
  draft: DraftItem
  onChange: (patch: Partial<QuestionInput>) => void
  onApprove: () => void
  onDiscard: () => void
}) {
  return (
    <li className="bg-background space-y-2 rounded-md border p-3">
      <div className="flex items-start gap-2">
        <Input
          value={draft.number}
          onChange={(event) => onChange({ number: event.target.value })}
          className="w-24 shrink-0 font-mono"
          aria-label="Draft question number"
        />
        <Textarea
          value={draft.statement}
          rows={Math.min(draft.statement.split('\n').length + 1, 8)}
          className="flex-1 font-mono text-xs"
          onChange={(event) => onChange({ statement: event.target.value })}
          aria-label="Draft question statement"
        />
      </div>
      <LaTeXPreview text={draft.statement} className="bg-muted/40 rounded-md border px-2 py-1.5" />
      <div className="flex justify-end gap-1">
        <Button size="sm" variant="ghost" onClick={onDiscard}>
          <X className="size-4" />
          Discard
        </Button>
        <Button size="sm" onClick={onApprove}>
          <Check className="size-4" />
          Approve
        </Button>
      </div>
    </li>
  )
}

function QuestionList({
  questions,
  onAdd,
  onUpdate,
  onDelete,
}: {
  questions: Question[]
  onAdd: (input: QuestionInput) => Promise<boolean>
  onUpdate: (question: Question, patch: Partial<QuestionInput>) => Promise<boolean>
  onDelete: (question: Question) => void
}) {
  const [adding, setAdding] = useState(false)
  const [form, setForm] = useState<QuestionInput>({ number: '', statement: '' })
  const [saving, setSaving] = useState(false)

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault()
    setSaving(true)
    try {
      if (await onAdd(form)) {
        setForm({ number: '', statement: '' })
        setAdding(false)
      }
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <h3 className="font-heading text-sm font-semibold">Questions</h3>
        <Button variant="ghost" size="sm" onClick={() => setAdding((value) => !value)}>
          <Plus className="size-4" />
          {adding ? 'Cancel' : 'Add question'}
        </Button>
      </div>

      {adding ? (
        <form
          onSubmit={(event) => void handleSubmit(event)}
          className="bg-background flex items-start gap-2 rounded-lg border p-3"
        >
          <Input
            required
            placeholder="1"
            maxLength={20}
            className="w-24 shrink-0"
            value={form.number}
            onChange={(event) => setForm({ ...form, number: event.target.value })}
            aria-label="Question number"
          />
          <Textarea
            required
            placeholder="Statement, in Markdown with $…$/$$…$$ for formulas."
            className="flex-1 font-mono text-xs"
            value={form.statement}
            onChange={(event) => setForm({ ...form, statement: event.target.value })}
            aria-label="Question statement"
          />
          <Button type="submit" size="sm" disabled={saving}>
            Save
          </Button>
        </form>
      ) : null}

      {questions.length === 0 ? (
        <p className="text-muted-foreground text-sm">No questions yet.</p>
      ) : (
        <ul className="space-y-1">
          {questions.map((question) => (
            <QuestionRow
              key={question.id}
              question={question}
              onUpdate={(patch) => onUpdate(question, patch)}
              onDelete={() => onDelete(question)}
            />
          ))}
        </ul>
      )}
    </div>
  )
}

function QuestionRow({
  question,
  onUpdate,
  onDelete,
}: {
  question: Question
  onUpdate: (patch: Partial<QuestionInput>) => Promise<boolean>
  onDelete: () => void
}) {
  const [editing, setEditing] = useState(false)
  const [number, setNumber] = useState(question.number)
  const [statement, setStatement] = useState(question.statement)
  const [saving, setSaving] = useState(false)

  async function save() {
    setSaving(true)
    try {
      if (await onUpdate({ number, statement })) setEditing(false)
    } finally {
      setSaving(false)
    }
  }

  function cancel() {
    setNumber(question.number)
    setStatement(question.statement)
    setEditing(false)
  }

  return (
    <li className="rounded-md border px-3 py-2">
      {editing ? (
        <div className="space-y-2">
          <div className="flex items-start gap-2">
            <Input
              value={number}
              maxLength={20}
              onChange={(event) => setNumber(event.target.value)}
              className="w-24 shrink-0"
              aria-label={`Number of question ${question.number}`}
            />
            <Textarea
              value={statement}
              rows={Math.min(statement.split('\n').length + 1, 8)}
              className="flex-1 font-mono text-xs"
              onChange={(event) => setStatement(event.target.value)}
              aria-label={`Statement of question ${question.number}`}
            />
          </div>
          <div className="flex justify-end gap-1">
            <Button
              size="icon-sm"
              variant="ghost"
              aria-label="Save"
              disabled={saving}
              onClick={() => void save()}
            >
              <Check className="size-4" />
            </Button>
            <Button size="icon-sm" variant="ghost" aria-label="Cancel" onClick={cancel}>
              <X className="size-4" />
            </Button>
          </div>
        </div>
      ) : (
        <div className="flex items-start gap-2">
          <span className="text-muted-foreground w-24 shrink-0 font-mono text-sm">
            {question.number}
          </span>
          <LaTeXPreview text={question.statement} className="min-w-0 flex-1" />
          <div className="flex shrink-0 items-center">
            <Button
              size="icon-sm"
              variant="ghost"
              aria-label={`Edit question ${question.number}`}
              onClick={() => setEditing(true)}
            >
              <Pencil className="size-3.5" />
            </Button>
            <Button
              size="icon-sm"
              variant="ghost"
              aria-label={`Delete question ${question.number}`}
              onClick={onDelete}
            >
              <Trash2 className="size-3.5" />
            </Button>
          </div>
        </div>
      )}
    </li>
  )
}
