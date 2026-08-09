import { ArrowLeft, Check } from 'lucide-react'
import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { toast } from 'sonner'

import { AssessmentForm } from '@/components/assessment-form'
import { PageHeader } from '@/components/page-header'
import { StudentsSection } from '@/components/students-section'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import { api, type ClassGroup } from '@/lib/api'
import { cn } from '@/lib/utils'

const STEPS = [
  { title: 'Class', description: 'Name and academic term' },
  { title: 'Students', description: 'Who is enrolled' },
  { title: 'Assessment', description: 'The first exam' },
]

const EMPTY_FORM = { name: '', code: '', academic_term: '', description: '' }

/**
 * Guided flow for setting up a class: first the class itself, then its
 * students, then its first assessment. Each step is saved as it is completed,
 * so the teacher can leave at any point without losing work.
 */
export function NewClassPage() {
  const navigate = useNavigate()
  const [step, setStep] = useState(0)
  const [createdClass, setCreatedClass] = useState<ClassGroup | null>(null)
  const [form, setForm] = useState(EMPTY_FORM)
  const [saving, setSaving] = useState(false)

  async function handleCreateClass(event: React.FormEvent) {
    event.preventDefault()
    setSaving(true)
    try {
      const classGroup = await api.createClass({
        name: form.name,
        code: form.code || null,
        academic_term: form.academic_term || null,
        description: form.description || null,
      })
      setCreatedClass(classGroup)
      setStep(1)
      toast.success(`${classGroup.name} was created.`)
    } catch (error) {
      toast.error((error as Error).message)
    } finally {
      setSaving(false)
    }
  }

  function finish() {
    if (createdClass) navigate(`/classes/${createdClass.id}`)
  }

  return (
    <>
      <PageHeader title="New class" description="Three steps to get a class ready for grading.">
        <Button variant="ghost" nativeButton={false} render={<Link to="/classes" />}>
          <ArrowLeft className="size-4" />
          Back to classes
        </Button>
      </PageHeader>

      <ol className="mb-8 grid gap-3 sm:grid-cols-3">
        {STEPS.map((item, index) => (
          <li
            key={item.title}
            className={cn(
              'bg-background flex items-center gap-3 rounded-lg border p-3',
              index === step && 'border-foreground/30 shadow-sm',
              index > step && 'opacity-60',
            )}
          >
            <span
              className={cn(
                'flex size-7 shrink-0 items-center justify-center rounded-full border text-sm font-medium',
                index < step && 'bg-primary text-primary-foreground border-transparent',
                index === step && 'border-foreground/40',
              )}
            >
              {index < step ? <Check className="size-4" /> : index + 1}
            </span>
            <div>
              <p className="text-sm font-medium">{item.title}</p>
              <p className="text-muted-foreground text-xs">{item.description}</p>
            </div>
          </li>
        ))}
      </ol>

      {step === 0 ? (
        <Card className="max-w-2xl">
          <CardHeader>
            <CardTitle>Class details</CardTitle>
            <CardDescription>Only the name is required.</CardDescription>
          </CardHeader>
          <CardContent>
            <form onSubmit={handleCreateClass} className="space-y-4">
              <div className="space-y-2">
                <Label htmlFor="name">Name</Label>
                <Input
                  id="name"
                  required
                  maxLength={160}
                  placeholder="Calculus I"
                  value={form.name}
                  onChange={(event) => setForm({ ...form, name: event.target.value })}
                />
              </div>
              <div className="grid gap-4 sm:grid-cols-2">
                <div className="space-y-2">
                  <Label htmlFor="code">Code</Label>
                  <Input
                    id="code"
                    maxLength={60}
                    placeholder="MAT101-A"
                    value={form.code}
                    onChange={(event) => setForm({ ...form, code: event.target.value })}
                  />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="academic_term">Academic term</Label>
                  <Input
                    id="academic_term"
                    maxLength={40}
                    placeholder="2026.2"
                    value={form.academic_term}
                    onChange={(event) => setForm({ ...form, academic_term: event.target.value })}
                  />
                </div>
              </div>
              <div className="space-y-2">
                <Label htmlFor="description">Description</Label>
                <Textarea
                  id="description"
                  rows={3}
                  placeholder="Optional notes about this class."
                  value={form.description}
                  onChange={(event) => setForm({ ...form, description: event.target.value })}
                />
              </div>
              <Button type="submit" disabled={saving}>
                Create class and continue
              </Button>
            </form>
          </CardContent>
        </Card>
      ) : null}

      {step === 1 && createdClass ? (
        <div className="space-y-6">
          <StudentsSection classId={createdClass.id} />
          <div className="flex gap-2">
            <Button onClick={() => setStep(2)}>Continue to assessment</Button>
            <Button variant="ghost" onClick={finish}>
              Finish later
            </Button>
          </div>
        </div>
      ) : null}

      {step === 2 && createdClass ? (
        <Card className="max-w-2xl">
          <CardHeader>
            <CardTitle>First assessment</CardTitle>
            <CardDescription>
              Create the exam you are going to grade. You can add more later.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <AssessmentForm
              classId={createdClass.id}
              submitLabel="Create assessment and finish"
              onCreated={finish}
            />
            <Button variant="ghost" onClick={finish}>
              Skip for now
            </Button>
          </CardContent>
        </Card>
      ) : null}
    </>
  )
}
