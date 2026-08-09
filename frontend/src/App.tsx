import { Navigate, Route, Routes } from 'react-router-dom'

import { AppLayout } from '@/components/app-layout'
import { Toaster } from '@/components/ui/sonner'
import { AssessmentPage } from '@/pages/assessment-page'
import { ClassDetailPage } from '@/pages/class-detail-page'
import { ClassesPage } from '@/pages/classes-page'
import { NewClassPage } from '@/pages/new-class-page'
import { ReviewPage } from '@/pages/review-page'

export default function App() {
  return (
    <AppLayout>
      <Routes>
        <Route path="/" element={<Navigate to="/classes" replace />} />
        <Route path="/classes" element={<ClassesPage />} />
        <Route path="/classes/new" element={<NewClassPage />} />
        <Route path="/classes/:classId" element={<ClassDetailPage />} />
        <Route path="/classes/:classId/assessments/:assessmentId" element={<AssessmentPage />} />
        <Route
          path="/classes/:classId/assessments/:assessmentId/submissions/:submissionId/review"
          element={<ReviewPage />}
        />
        <Route path="*" element={<Navigate to="/classes" replace />} />
      </Routes>
      <Toaster />
    </AppLayout>
  )
}
