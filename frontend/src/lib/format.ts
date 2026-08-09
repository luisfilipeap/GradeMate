/** Format an ISO date (YYYY-MM-DD) for display, without timezone surprises. */
export function formatDate(value: string | null): string {
  if (!value) return 'No date set'
  const [year, month, day] = value.split('-').map(Number)
  return new Date(year, month - 1, day).toLocaleDateString(undefined, {
    day: '2-digit',
    month: 'short',
    year: 'numeric',
  })
}
