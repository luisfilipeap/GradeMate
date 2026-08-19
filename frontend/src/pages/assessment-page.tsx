import { ArrowLeft, CalendarDays, Check, FileText, ScanText, Trash2, Upload } from 'lucide-react'
import { useCallback, useEffect, useRef, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { toast } from 'sonner'

import { EmptyState } from '@/components/empty-state'
import { PageHeader } from '@/components/page-header'
import { QuestionPaperSection } from '@/components/question-paper-section'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import { api, type Assessment, type Student, type Submission } from '@/lib/api'
import { formatDate } from '@/lib/format'

/**
 * One assessment, with the class roster and the PDF each student handed in.
 * Every student is a row, whether or not their exam has been uploaded yet.
 */
export function AssessmentPage() {
  const { classId, assessmentId } = useParams<{ classId: string; assessmentId: string }>()
  const [assessment, setAssessment] = useState<Assessment | null>(null)
  const [students, setStudents] = useState<Student[]>([])
  const [submissions, setSubmissions] = useState<Record<string, Submission>>({})
  const [loading, setLoading] = useState(true)

  const refreshSubmissions = useCallback(async () => {
    if (!assessmentId) return
    const rows = await api.listSubmissions(assessmentId)
    setSubmissions(Object.fromEntries(rows.map((row) => [row.student_id, row])))
  }, [assessmentId])

  useEffect(() => {
    if (!classId || !assessmentId) return
    Promise.all([
      api.getAssessment(assessmentId).then(setAssessment),
      api.listStudents(classId).then(setStudents),
      refreshSubmissions(),
    ])
      .catch((error: Error) => toast.error(error.message))
      .finally(() => setLoading(false))
  }, [classId, assessmentId, refreshSubmissions])

  if (loading) return <p className="text-muted-foreground text-sm">Loading assessment…</p>
  if (!assessment) return <p className="text-muted-foreground text-sm">Assessment not found.</p>

  const uploaded = Object.keys(submissions).length

  return (
    <>
      <Button
        variant="ghost"
        size="sm"
        className="mb-4 -ml-2"
        nativeButton={false}
        render={<Link to={`/classes/${classId}`} />}
      >
        <ArrowLeft className="size-4" />
        Back to class
      </Button>

      <PageHeader title={assessment.title} description={assessment.description ?? undefined}>
        <Badge variant="secondary">
          {uploaded} of {students.length} uploaded
        </Badge>
      </PageHeader>

      <div className="text-muted-foreground mb-6 flex flex-wrap items-center gap-4 text-sm">
        <span className="flex items-center gap-1.5">
          <CalendarDays className="size-4" />
          {formatDate(assessment.applied_on)}
        </span>
        <span>Maximum score {assessment.max_score}</span>
      </div>

      <QuestionPaperSection assessment={assessment} onAssessmentChange={setAssessment} />

      {students.length === 0 ? (
        <EmptyState
          icon={FileText}
          title="This class has no students"
          description="Add the students of the class before uploading their exams."
        >
          <Button nativeButton={false} render={<Link to={`/classes/${classId}`} />}>
            Go to the class
          </Button>
        </EmptyState>
      ) : (
        <div className="bg-background overflow-hidden rounded-lg border">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Student</TableHead>
                <TableHead>Registration no.</TableHead>
                <TableHead>Exam</TableHead>
                <TableHead className="w-56 text-right">Actions</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {students.map((student) => (
                <StudentRow
                  key={student.id}
                  classId={classId!}
                  assessmentId={assessment.id}
                  student={student}
                  submission={submissions[student.id]}
                  onChanged={() => void refreshSubmissions().catch(() => undefined)}
                />
              ))}
            </TableBody>
          </Table>
        </div>
      )}
    </>
  )
}

function StudentRow({
  classId,
  assessmentId,
  student,
  submission,
  onChanged,
}: {
  classId: string
  assessmentId: string
  student: Student
  submission: Submission | undefined
  onChanged: () => void
}) {
  const inputRef = useRef<HTMLInputElement>(null)
  const [busy, setBusy] = useState(false)

  async function handleFile(event: React.ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0]
    // Let the same file be picked again after a failed upload.
    event.target.value = ''
    if (!file) return

    setBusy(true)
    try {
      await api.uploadSubmission(assessmentId, student.id, file)
      toast.success(`Exam of ${student.full_name} was uploaded.`)
      onChanged()
    } catch (error) {
      toast.error((error as Error).message)
    } finally {
      setBusy(false)
    }
  }

  async function handleDelete() {
    if (!submission) return
    setBusy(true)
    try {
      await api.deleteSubmission(submission.id)
      toast.success(`Exam of ${student.full_name} was removed.`)
      onChanged()
    } catch (error) {
      toast.error((error as Error).message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <TableRow>
      <TableCell className="font-medium">{student.full_name}</TableCell>
      <TableCell className="text-muted-foreground">{student.registration_number}</TableCell>
      <TableCell>
        {submission ? (
          <span className="flex items-center gap-2 text-sm">
            <Check className="size-4" />
            <a
              className="underline underline-offset-4"
              href={api.submissionFileUrl(submission.id)}
              target="_blank"
              rel="noreferrer"
            >
              {submission.original_filename ?? 'exam.pdf'}
            </a>
            <span className="text-muted-foreground">
              {describeSubmission(submission)}
            </span>
          </span>
        ) : (
          <span className="text-muted-foreground text-sm">Not uploaded</span>
        )}
      </TableCell>
      <TableCell className="text-right">
        <input
          ref={inputRef}
          type="file"
          accept="application/pdf"
          className="hidden"
          onChange={(event) => void handleFile(event)}
        />
        <div className="flex items-center justify-end gap-1">
          {submission ? (
            <Button
              variant="outline"
              size="sm"
              nativeButton={false}
              render={
                <Link
                  to={`/classes/${classId}/assessments/${assessmentId}/submissions/${submission.id}/review`}
                />
              }
            >
              <ScanText className="size-4" />
              Correct
            </Button>
          ) : null}
          <Button
            variant={submission ? 'ghost' : 'default'}
            size="sm"
            disabled={busy}
            onClick={() => inputRef.current?.click()}
          >
            <Upload className="size-4" />
            {submission ? 'Replace' : 'Upload PDF'}
          </Button>
          {submission ? (
            <Button
              variant="ghost"
              size="icon-sm"
              disabled={busy}
              aria-label={`Remove the exam of ${student.full_name}`}
              onClick={() => void handleDelete()}
            >
              <Trash2 className="size-4" />
            </Button>
          ) : null}
        </div>
      </TableCell>
    </TableRow>
  )
}

function describeSubmission(submission: Submission): string {
  const parts: string[] = []
  if (submission.page_count) {
    parts.push(`${submission.page_count} page${submission.page_count === 1 ? '' : 's'}`)
  }
  if (submission.file_size_bytes) {
    parts.push(formatBytes(submission.file_size_bytes))
  }
  return parts.length ? `(${parts.join(', ')})` : ''
}

function formatBytes(bytes: number): string {
  const megabytes = bytes / 1024 / 1024
  return megabytes >= 1 ? `${megabytes.toFixed(1)} MB` : `${Math.round(bytes / 1024)} KB`
}
