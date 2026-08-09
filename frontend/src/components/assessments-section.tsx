import { CalendarDays, Eye, FileText, Plus, Trash2 } from 'lucide-react'
import { useCallback, useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { toast } from 'sonner'

import { AssessmentForm } from '@/components/assessment-form'
import { EmptyState } from '@/components/empty-state'
import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from '@/components/ui/dialog'
import { api, type Assessment } from '@/lib/api'
import { formatDate } from '@/lib/format'

/** List of the assessments of a class, with a dialog to create new ones. */
export function AssessmentsSection({ classId }: { classId: string }) {
  const [assessments, setAssessments] = useState<Assessment[]>([])
  const [dialogOpen, setDialogOpen] = useState(false)

  const refresh = useCallback(async () => {
    try {
      setAssessments(await api.listAssessments(classId))
    } catch (error) {
      toast.error((error as Error).message)
    }
  }, [classId])

  useEffect(() => {
    void refresh()
  }, [refresh])

  async function handleDelete(assessment: Assessment) {
    try {
      await api.deleteAssessment(assessment.id)
      toast.success(`"${assessment.title}" was deleted.`)
      await refresh()
    } catch (error) {
      toast.error((error as Error).message)
    }
  }

  const newAssessmentDialog = (
    <Dialog open={dialogOpen} onOpenChange={setDialogOpen}>
      <DialogTrigger render={<Button />}>
        <Plus className="size-4" />
        New assessment
      </DialogTrigger>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>New assessment</DialogTitle>
          <DialogDescription>
            Exams of the same class must have different titles.
          </DialogDescription>
        </DialogHeader>
        <AssessmentForm
          classId={classId}
          onCreated={() => {
            setDialogOpen(false)
            void refresh()
          }}
        />
      </DialogContent>
    </Dialog>
  )

  if (assessments.length === 0) {
    return (
      <EmptyState
        icon={FileText}
        title="No assessments yet"
        description="Create the exams of this class. Later you will upload the scanned PDF each student handed in."
      >
        {newAssessmentDialog}
      </EmptyState>
    )
  }

  return (
    <div className="space-y-4">
      <div className="flex justify-end">{newAssessmentDialog}</div>

      <ul className="space-y-3">
        {assessments.map((assessment) => (
          <li
            key={assessment.id}
            className="bg-background flex flex-wrap items-center justify-between gap-4 rounded-lg border p-4"
          >
            <div className="space-y-1">
              <Link
                to={`/classes/${classId}/assessments/${assessment.id}`}
                className="font-medium hover:underline"
              >
                {assessment.title}
              </Link>
              <div className="text-muted-foreground flex flex-wrap items-center gap-3 text-sm">
                <span className="flex items-center gap-1">
                  <CalendarDays className="size-3.5" />
                  {formatDate(assessment.applied_on)}
                </span>
                <span>Max score {assessment.max_score}</span>
                <span>
                  {assessment.submission_count} submission
                  {assessment.submission_count === 1 ? '' : 's'}
                </span>
              </div>
            </div>
            <div className="flex items-center gap-2">
              <Button
                variant="ghost"
                size="icon"
                nativeButton={false}
                aria-label={`Open ${assessment.title}`}
                title="Open the assessment and upload the students' exams"
                render={<Link to={`/classes/${classId}/assessments/${assessment.id}`} />}
              >
                <Eye className="size-4" />
              </Button>
              <Button
                variant="ghost"
                size="icon"
                aria-label={`Delete ${assessment.title}`}
                onClick={() => void handleDelete(assessment)}
              >
                <Trash2 className="size-4" />
              </Button>
            </div>
          </li>
        ))}
      </ul>
    </div>
  )
}
