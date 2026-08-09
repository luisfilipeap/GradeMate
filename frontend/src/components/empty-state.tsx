import type { LucideIcon } from 'lucide-react'
import type { ReactNode } from 'react'

/** Placeholder shown when a list has no rows yet. */
export function EmptyState({
  icon: Icon,
  title,
  description,
  children,
}: {
  icon: LucideIcon
  title: string
  description: string
  children?: ReactNode
}) {
  return (
    <div className="flex flex-col items-center justify-center rounded-lg border border-dashed px-6 py-14 text-center">
      <div className="bg-muted text-muted-foreground mb-4 rounded-full p-3">
        <Icon className="size-6" />
      </div>
      <h3 className="font-heading text-base font-semibold">{title}</h3>
      <p className="text-muted-foreground mt-1 max-w-sm text-sm">{description}</p>
      {children ? <div className="mt-6">{children}</div> : null}
    </div>
  )
}
