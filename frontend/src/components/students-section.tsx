import { Trash2, UserPlus, Users } from 'lucide-react'
import { useCallback, useEffect, useState } from 'react'
import { toast } from 'sonner'

import { EmptyState } from '@/components/empty-state'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import { api, type Student } from '@/lib/api'

const EMPTY_FORM = { full_name: '', registration_number: '', email: '' }

/** Roster of a class: inline "add student" form plus the list of students. */
export function StudentsSection({ classId }: { classId: string }) {
  const [students, setStudents] = useState<Student[]>([])
  const [form, setForm] = useState(EMPTY_FORM)
  const [saving, setSaving] = useState(false)

  const refresh = useCallback(async () => {
    try {
      setStudents(await api.listStudents(classId))
    } catch (error) {
      toast.error((error as Error).message)
    }
  }, [classId])

  useEffect(() => {
    void refresh()
  }, [refresh])

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault()
    setSaving(true)
    try {
      const student = await api.createStudent(classId, form)
      setForm(EMPTY_FORM)
      toast.success(`${student.full_name} was added to the class.`)
      await refresh()
    } catch (error) {
      toast.error((error as Error).message)
    } finally {
      setSaving(false)
    }
  }

  async function handleDelete(student: Student) {
    try {
      await api.deleteStudent(student.id)
      toast.success(`${student.full_name} was removed.`)
      await refresh()
    } catch (error) {
      toast.error((error as Error).message)
    }
  }

  return (
    <div className="space-y-6">
      <form
        onSubmit={handleSubmit}
        className="bg-background grid gap-4 rounded-lg border p-4 sm:grid-cols-[2fr_1fr_2fr_auto] sm:items-end"
      >
        <div className="space-y-2">
          <Label htmlFor="full_name">Full name</Label>
          <Input
            id="full_name"
            required
            maxLength={160}
            placeholder="Ana Souza"
            value={form.full_name}
            onChange={(event) => setForm({ ...form, full_name: event.target.value })}
          />
        </div>
        <div className="space-y-2">
          <Label htmlFor="registration_number">Registration no.</Label>
          <Input
            id="registration_number"
            required
            maxLength={40}
            placeholder="2026001"
            value={form.registration_number}
            onChange={(event) => setForm({ ...form, registration_number: event.target.value })}
          />
        </div>
        <div className="space-y-2">
          <Label htmlFor="email">E-mail</Label>
          <Input
            id="email"
            type="email"
            required
            maxLength={255}
            placeholder="ana@university.edu"
            value={form.email}
            onChange={(event) => setForm({ ...form, email: event.target.value })}
          />
        </div>
        <Button type="submit" disabled={saving}>
          <UserPlus className="size-4" />
          Add
        </Button>
      </form>

      {students.length === 0 ? (
        <EmptyState
          icon={Users}
          title="No students yet"
          description="Add the students of this class using the form above. Registration numbers and e-mail addresses must be unique within the class."
        />
      ) : (
        <div className="bg-background overflow-hidden rounded-lg border">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Name</TableHead>
                <TableHead>Registration no.</TableHead>
                <TableHead>E-mail</TableHead>
                <TableHead className="w-16" />
              </TableRow>
            </TableHeader>
            <TableBody>
              {students.map((student) => (
                <TableRow key={student.id}>
                  <TableCell className="font-medium">{student.full_name}</TableCell>
                  <TableCell className="text-muted-foreground">
                    {student.registration_number}
                  </TableCell>
                  <TableCell className="text-muted-foreground">{student.email}</TableCell>
                  <TableCell>
                    <Button
                      variant="ghost"
                      size="icon"
                      aria-label={`Remove ${student.full_name}`}
                      onClick={() => void handleDelete(student)}
                    >
                      <Trash2 className="size-4" />
                    </Button>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      )}
    </div>
  )
}
