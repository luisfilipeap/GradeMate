import { useState } from 'react'
import { toast } from 'sonner'

import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import { api, type Assessment } from '@/lib/api'

const EMPTY_FORM = { title: '', applied_on: '', max_score: '100', description: '' }

/** Form used both in the new-class flow and on the class detail screen. */
export function AssessmentForm({
  classId,
  submitLabel = 'Create assessment',
  onCreated,
}: {
  classId: string
  submitLabel?: string
  onCreated: (assessment: Assessment) => void
}) {
  const [form, setForm] = useState(EMPTY_FORM)
  const [saving, setSaving] = useState(false)

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault()
    setSaving(true)
    try {
      const assessment = await api.createAssessment(classId, {
        title: form.title,
        applied_on: form.applied_on || null,
        max_score: form.max_score,
        description: form.description || null,
      })
      setForm(EMPTY_FORM)
      toast.success(`"${assessment.title}" was created.`)
      onCreated(assessment)
    } catch (error) {
      toast.error((error as Error).message)
    } finally {
      setSaving(false)
    }
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-4">
      <div className="grid gap-4 sm:grid-cols-3">
        <div className="space-y-2 sm:col-span-3">
          <Label htmlFor="title">Title</Label>
          <Input
            id="title"
            required
            maxLength={160}
            placeholder="Midterm exam"
            value={form.title}
            onChange={(event) => setForm({ ...form, title: event.target.value })}
          />
        </div>
        <div className="space-y-2">
          <Label htmlFor="applied_on">Date</Label>
          <Input
            id="applied_on"
            type="date"
            value={form.applied_on}
            onChange={(event) => setForm({ ...form, applied_on: event.target.value })}
          />
        </div>
        <div className="space-y-2">
          <Label htmlFor="max_score">Maximum score</Label>
          <Input
            id="max_score"
            type="number"
            min="0.01"
            step="0.01"
            required
            value={form.max_score}
            onChange={(event) => setForm({ ...form, max_score: event.target.value })}
          />
        </div>
      </div>

      <div className="space-y-2">
        <Label htmlFor="description">Description</Label>
        <Textarea
          id="description"
          rows={3}
          placeholder="Optional notes about this assessment."
          value={form.description}
          onChange={(event) => setForm({ ...form, description: event.target.value })}
        />
      </div>

      <Button type="submit" disabled={saving}>
        {submitLabel}
      </Button>
    </form>
  )
}
