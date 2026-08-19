/**
 * Thin client for the GradeMate API.
 *
 * In development Vite proxies every /api request to the FastAPI backend, so the
 * browser always talks to a single origin and no CORS setup is needed.
 */

export class ApiError extends Error {
  status: number

  constructor(message: string, status: number) {
    super(message)
    this.name = 'ApiError'
    this.status = status
  }
}

export type ClassGroup = {
  id: string
  name: string
  code: string | null
  academic_term: string | null
  description: string | null
  created_at: string
  updated_at: string
  student_count: number
  assessment_count: number
}

export type Student = {
  id: string
  class_id: string
  full_name: string
  registration_number: string
  email: string
  created_at: string
  updated_at: string
}

export type Assessment = {
  id: string
  class_id: string
  title: string
  description: string | null
  applied_on: string | null
  max_score: string
  created_at: string
  updated_at: string
  submission_count: number
  question_count: number
  /** Metadata about the uploaded question paper. `null` means none was uploaded yet. */
  question_paper_original_filename: string | null
  question_paper_page_count: number | null
}

export type Submission = {
  id: string
  class_id: string
  assessment_id: string
  student_id: string
  original_filename: string | null
  file_size_bytes: number | null
  page_count: number | null
  checksum_sha256: string | null
  created_at: string
  updated_at: string
}

export type OcrLine = {
  id: string
  page_id: string
  position: number
  text: string
  corrected_text: string | null
  accepted: boolean
  /** Region type: "text", "inline_formula", "display_formula", "table"… */
  label: string | null
  /** Polygon in pixels of the page image: [[x, y], ...]. */
  box: number[][]
  /**
   * LLM-normalized LaTeX/Markdown, set only when normalization ran and passed
   * the semantic guard. `null` whenever `normalization_incomplete` is true.
   */
  normalized_text: string | null
  /** True when normalization did not produce a usable `normalized_text`. */
  normalization_incomplete: boolean
}

export type SubmissionPage = {
  id: string
  submission_id: string
  number: number
  width: number
  height: number
  lines: OcrLine[]
}

export type Review = {
  submission_id: string
  student_id: string
  assessment_id: string
  page_count: number
  pages: SubmissionPage[]
}

export type Question = {
  id: string
  assessment_id: string
  // The teacher's own numbering ("1", "1a", "2.1"...), not assumed numeric.
  number: string
  statement: string
  // Reading order within the assessment; independent of what `number` reads.
  position: number
  created_at: string
  updated_at: string
}

export type QuestionInput = {
  number: string
  statement: string
}

/** An extraction candidate: same shape as `QuestionInput`, not yet a `Question`. */
export type QuestionDraft = {
  number: string
  statement: string
}

export type ClassInput = {
  name: string
  code?: string | null
  academic_term?: string | null
  description?: string | null
}

export type StudentInput = {
  full_name: string
  registration_number: string
  email: string
}

export type AssessmentInput = {
  title: string
  description?: string | null
  applied_on?: string | null
  max_score: string
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`/api${path}`, {
    // Only JSON bodies get an explicit type: for FormData the browser has to set
    // the header itself, because it carries the multipart boundary.
    headers: typeof init?.body === 'string' ? { 'Content-Type': 'application/json' } : undefined,
    ...init,
  })

  if (!response.ok) {
    throw new ApiError(await readErrorMessage(response), response.status)
  }

  return response.status === 204 ? (undefined as T) : ((await response.json()) as T)
}

/** Turn a FastAPI error body into a single sentence we can show to the teacher. */
async function readErrorMessage(response: Response): Promise<string> {
  try {
    const body = await response.json()
    if (typeof body.detail === 'string') return body.detail
    if (Array.isArray(body.detail)) {
      return body.detail.map((item: { msg?: string }) => item.msg ?? '').join(' ')
    }
  } catch {
    // Fall through to the generic message below.
  }
  return `Request failed with status ${response.status}.`
}

export const api = {
  listClasses: () => request<ClassGroup[]>('/classes'),
  getClass: (classId: string) => request<ClassGroup>(`/classes/${classId}`),
  createClass: (input: ClassInput) =>
    request<ClassGroup>('/classes', { method: 'POST', body: JSON.stringify(input) }),
  deleteClass: (classId: string) => request<void>(`/classes/${classId}`, { method: 'DELETE' }),

  listStudents: (classId: string) => request<Student[]>(`/classes/${classId}/students`),
  createStudent: (classId: string, input: StudentInput) =>
    request<Student>(`/classes/${classId}/students`, {
      method: 'POST',
      body: JSON.stringify(input),
    }),
  deleteStudent: (studentId: string) =>
    request<void>(`/students/${studentId}`, { method: 'DELETE' }),

  listAssessments: (classId: string) => request<Assessment[]>(`/classes/${classId}/assessments`),
  getAssessment: (assessmentId: string) => request<Assessment>(`/assessments/${assessmentId}`),
  createAssessment: (classId: string, input: AssessmentInput) =>
    request<Assessment>(`/classes/${classId}/assessments`, {
      method: 'POST',
      body: JSON.stringify(input),
    }),
  deleteAssessment: (assessmentId: string) =>
    request<void>(`/assessments/${assessmentId}`, { method: 'DELETE' }),

  listSubmissions: (assessmentId: string) =>
    request<Submission[]>(`/assessments/${assessmentId}/submissions`),
  uploadSubmission: (assessmentId: string, studentId: string, file: File) => {
    const body = new FormData()
    body.append('file', file)
    // No Content-Type header: the browser sets the multipart boundary itself.
    return request<Submission>(`/assessments/${assessmentId}/students/${studentId}/submission`, {
      method: 'PUT',
      body,
    })
  },
  deleteSubmission: (submissionId: string) =>
    request<void>(`/submissions/${submissionId}`, { method: 'DELETE' }),
  submissionFileUrl: (submissionId: string) => `/api/submissions/${submissionId}/file`,

  uploadQuestionPaper: (assessmentId: string, file: File) => {
    const body = new FormData()
    body.append('file', file)
    // No Content-Type header: the browser sets the multipart boundary itself.
    return request<void>(`/assessments/${assessmentId}/question-paper`, {
      method: 'PUT',
      body,
    })
  },
  questionPaperFileUrl: (assessmentId: string) =>
    `/api/assessments/${assessmentId}/question-paper/file`,

  listQuestions: (assessmentId: string) =>
    request<Question[]>(`/assessments/${assessmentId}/questions`),
  createQuestion: (assessmentId: string, input: QuestionInput) =>
    request<Question>(`/assessments/${assessmentId}/questions`, {
      method: 'POST',
      body: JSON.stringify(input),
    }),
  updateQuestion: (questionId: string, input: Partial<QuestionInput>) =>
    request<Question>(`/questions/${questionId}`, { method: 'PATCH', body: JSON.stringify(input) }),
  deleteQuestion: (questionId: string) =>
    request<void>(`/questions/${questionId}`, { method: 'DELETE' }),
  extractQuestions: (assessmentId: string) =>
    request<{ questions: QuestionDraft[] }>(
      `/assessments/${assessmentId}/question-paper/extract`,
      { method: 'POST' },
    ),

  getReview: (submissionId: string) => request<Review>(`/submissions/${submissionId}/review`),
  runOcr: (submissionId: string) =>
    request<Review>(`/submissions/${submissionId}/ocr`, { method: 'POST' }),
  updateLine: (lineId: string, input: { corrected_text?: string | null; accepted?: boolean }) =>
    request<OcrLine>(`/ocr-lines/${lineId}`, { method: 'PATCH', body: JSON.stringify(input) }),
  pageImageUrl: (pageId: string) => `/api/pages/${pageId}/image`,
}
