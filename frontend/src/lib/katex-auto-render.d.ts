/**
 * `katex/contrib/auto-render` ships without a `types` entry in its package
 * exports map, so TypeScript can't resolve it under `moduleResolution:
 * "bundler"`. This is a minimal ambient declaration for the subset we use
 * (see node_modules/katex/dist/contrib/auto-render.mjs for the full API).
 */
declare module 'katex/contrib/auto-render' {
  export type AutoRenderDelimiter = {
    left: string
    right: string
    display: boolean
  }

  export type AutoRenderOptions = {
    delimiters?: AutoRenderDelimiter[]
    ignoredTags?: string[]
    ignoredClasses?: string[]
    errorCallback?: (message: string, error: Error) => void
    throwOnError?: boolean
    preProcess?: (math: string) => string
  }

  export default function renderMathInElement(
    element: HTMLElement,
    options?: AutoRenderOptions,
  ): void
}
