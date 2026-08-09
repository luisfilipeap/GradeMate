import { FileText, Plus, Users } from 'lucide-react'
import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { toast } from 'sonner'

import { EmptyState } from '@/components/empty-state'
import { PageHeader } from '@/components/page-header'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { api, type ClassGroup } from '@/lib/api'

/** Landing screen: every class the teacher has registered. */
export function ClassesPage() {
  const [classes, setClasses] = useState<ClassGroup[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    api
      .listClasses()
      .then(setClasses)
      .catch((error: Error) => toast.error(error.message))
      .finally(() => setLoading(false))
  }, [])

  const newClassButton = (
    <Button nativeButton={false} render={<Link to="/classes/new" />}>
      <Plus className="size-4" />
      New class
    </Button>
  )

  return (
    <>
      <PageHeader
        title="Classes"
        description="Every class you teach, with its students and assessments."
      >
        {classes.length > 0 ? newClassButton : null}
      </PageHeader>

      {loading ? (
        <p className="text-muted-foreground text-sm">Loading classes…</p>
      ) : classes.length === 0 ? (
        <EmptyState
          icon={Users}
          title="No classes yet"
          description="Start by creating a class. You will then add its students and its first assessment."
        >
          {newClassButton}
        </EmptyState>
      ) : (
        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
          {classes.map((classGroup) => (
            <Link key={classGroup.id} to={`/classes/${classGroup.id}`} className="group">
              <Card className="hover:border-foreground/20 h-full transition-colors">
                <CardHeader>
                  <CardTitle className="flex items-start justify-between gap-2">
                    <span className="group-hover:underline">{classGroup.name}</span>
                    {classGroup.code ? (
                      <Badge variant="secondary">{classGroup.code}</Badge>
                    ) : null}
                  </CardTitle>
                  <CardDescription>
                    {classGroup.academic_term ?? 'No academic term set'}
                  </CardDescription>
                </CardHeader>
                <CardContent className="text-muted-foreground flex items-center gap-4 text-sm">
                  <span className="flex items-center gap-1.5">
                    <Users className="size-4" />
                    {classGroup.student_count} student
                    {classGroup.student_count === 1 ? '' : 's'}
                  </span>
                  <span className="flex items-center gap-1.5">
                    <FileText className="size-4" />
                    {classGroup.assessment_count} assessment
                    {classGroup.assessment_count === 1 ? '' : 's'}
                  </span>
                </CardContent>
              </Card>
            </Link>
          ))}
        </div>
      )}
    </>
  )
}
