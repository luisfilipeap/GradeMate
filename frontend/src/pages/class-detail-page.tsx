import { ArrowLeft, Trash2 } from 'lucide-react'
import { useEffect, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { toast } from 'sonner'

import { AssessmentsSection } from '@/components/assessments-section'
import { PageHeader } from '@/components/page-header'
import { StudentsSection } from '@/components/students-section'
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from '@/components/ui/alert-dialog'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { api, type ClassGroup } from '@/lib/api'

/** Students and assessments of a single class. */
export function ClassDetailPage() {
  const { classId } = useParams<{ classId: string }>()
  const navigate = useNavigate()
  const [classGroup, setClassGroup] = useState<ClassGroup | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    if (!classId) return
    api
      .getClass(classId)
      .then(setClassGroup)
      .catch((error: Error) => toast.error(error.message))
      .finally(() => setLoading(false))
  }, [classId])

  async function handleDelete() {
    if (!classGroup) return
    try {
      await api.deleteClass(classGroup.id)
      toast.success(`${classGroup.name} was deleted.`)
      navigate('/classes')
    } catch (error) {
      toast.error((error as Error).message)
    }
  }

  if (loading) return <p className="text-muted-foreground text-sm">Loading class…</p>
  if (!classGroup) return <p className="text-muted-foreground text-sm">Class not found.</p>

  return (
    <>
      <Button
        variant="ghost"
        size="sm"
        className="mb-4 -ml-2"
        nativeButton={false}
        render={<Link to="/classes" />}
      >
        <ArrowLeft className="size-4" />
        Classes
      </Button>

      <PageHeader
        title={classGroup.name}
        description={classGroup.description ?? undefined}
      >
        <AlertDialog>
          <AlertDialogTrigger render={<Button variant="ghost" />}>
            <Trash2 className="size-4" />
            Delete class
          </AlertDialogTrigger>
          <AlertDialogContent>
            <AlertDialogHeader>
              <AlertDialogTitle>Delete {classGroup.name}?</AlertDialogTitle>
              <AlertDialogDescription>
                This also deletes its students, assessments and submissions. This action cannot be
                undone.
              </AlertDialogDescription>
            </AlertDialogHeader>
            <AlertDialogFooter>
              <AlertDialogCancel>Cancel</AlertDialogCancel>
              <AlertDialogAction onClick={() => void handleDelete()}>Delete</AlertDialogAction>
            </AlertDialogFooter>
          </AlertDialogContent>
        </AlertDialog>
      </PageHeader>

      <div className="mb-6 flex flex-wrap items-center gap-2">
        {classGroup.code ? <Badge variant="secondary">{classGroup.code}</Badge> : null}
        {classGroup.academic_term ? <Badge variant="outline">{classGroup.academic_term}</Badge> : null}
      </div>

      <Tabs defaultValue="students">
        <TabsList>
          <TabsTrigger value="students">Students ({classGroup.student_count})</TabsTrigger>
          <TabsTrigger value="assessments">
            Assessments ({classGroup.assessment_count})
          </TabsTrigger>
        </TabsList>
        <TabsContent value="students" className="mt-6">
          <StudentsSection classId={classGroup.id} />
        </TabsContent>
        <TabsContent value="assessments" className="mt-6">
          <AssessmentsSection classId={classGroup.id} />
        </TabsContent>
      </Tabs>
    </>
  )
}
