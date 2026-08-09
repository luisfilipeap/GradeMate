import { cn } from '@/lib/utils'
import { api, type OcrLine, type SubmissionPage } from '@/lib/api'

/** Bounding rectangle of a polygon, in percentages of the page image. */
function boxStyle(line: OcrLine, page: SubmissionPage) {
  const xs = line.box.map(([x]) => x)
  const ys = line.box.map(([, y]) => y)
  const left = Math.min(...xs)
  const top = Math.min(...ys)
  return {
    left: `${(left / page.width) * 100}%`,
    top: `${(top / page.height) * 100}%`,
    width: `${((Math.max(...xs) - left) / page.width) * 100}%`,
    height: `${((Math.max(...ys) - top) / page.height) * 100}%`,
  }
}

/**
 * The rendered exam page with one box drawn over every recognised line.
 *
 * The image is the exact raster the OCR read, so the boxes are positioned as
 * percentages of it and stay aligned at any display size.
 */
export function PageCanvas({
  page,
  activeLineId,
  onHoverLine,
  onSelectLine,
}: {
  page: SubmissionPage
  activeLineId: string | null
  onHoverLine: (lineId: string | null) => void
  onSelectLine: (lineId: string) => void
}) {
  return (
    <div className="bg-background relative overflow-hidden rounded-lg border">
      <img
        src={api.pageImageUrl(page.id)}
        alt={`Page ${page.number}`}
        className="block w-full"
        width={page.width}
        height={page.height}
      />
      {page.lines.map((line) => (
        <button
          key={line.id}
          type="button"
          style={boxStyle(line, page)}
          aria-label={line.text}
          onMouseEnter={() => onHoverLine(line.id)}
          onMouseLeave={() => onHoverLine(null)}
          onClick={() => onSelectLine(line.id)}
          className={cn(
            'absolute cursor-pointer rounded-[2px] border-2 transition-colors',
            line.id === activeLineId
              ? 'border-sky-500 bg-sky-500/25'
              : line.accepted
                ? 'border-emerald-500/70 bg-emerald-500/10 hover:bg-emerald-500/20'
                : 'border-amber-500/70 bg-amber-500/10 hover:bg-amber-500/20',
          )}
        />
      ))}
    </div>
  )
}
