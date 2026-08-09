import { GraduationCap, Users } from 'lucide-react'
import type { ReactNode } from 'react'
import { NavLink } from 'react-router-dom'

import { cn } from '@/lib/utils'

const NAVIGATION = [{ to: '/classes', label: 'Classes', icon: Users }]

/** Sidebar shell shared by every screen. */
export function AppLayout({ children }: { children: ReactNode }) {
  return (
    <div className="bg-muted/30 text-foreground min-h-screen">
      <div className="mx-auto flex min-h-screen w-full max-w-[1400px]">
        <aside className="bg-background hidden w-64 shrink-0 border-r md:flex md:flex-col">
          <div className="flex h-16 items-center gap-2 border-b px-6">
            <GraduationCap className="size-5" />
            <span className="font-heading text-base font-semibold tracking-tight">GradeMate</span>
          </div>

          <nav className="flex flex-1 flex-col gap-1 p-3">
            {NAVIGATION.map(({ to, label, icon: Icon }) => (
              <NavLink
                key={to}
                to={to}
                className={({ isActive }) =>
                  cn(
                    'flex items-center gap-2 rounded-md px-3 py-2 text-sm font-medium transition-colors',
                    isActive
                      ? 'bg-accent text-accent-foreground'
                      : 'text-muted-foreground hover:bg-accent/60 hover:text-accent-foreground',
                  )
                }
              >
                <Icon className="size-4" />
                {label}
              </NavLink>
            ))}
          </nav>

          <p className="text-muted-foreground border-t px-6 py-4 text-xs">
            Grading assistant for scanned exams
          </p>
        </aside>

        <main className="flex-1 px-6 py-8 md:px-10">{children}</main>
      </div>
    </div>
  )
}
