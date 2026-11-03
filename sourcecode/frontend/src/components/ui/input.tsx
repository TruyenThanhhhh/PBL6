import type { InputHTMLAttributes, ReactNode, TextareaHTMLAttributes } from "react"
import { cn } from "@/utils/cn"

export type FieldValidationState = "default" | "error" | "warning" | "success"

const stateClasses: Record<FieldValidationState, string> = {
  default: "border-line hover:border-muted/60 focus-visible:border-ink focus-visible:outline-ink",
  error: "border-error bg-error-soft/30 focus-visible:border-error focus-visible:outline-error",
  warning: "border-warning bg-warning-soft/30 focus-visible:border-warning focus-visible:outline-warning",
  success: "border-success bg-success-soft/30 focus-visible:border-success focus-visible:outline-success",
}

export interface InputProps extends InputHTMLAttributes<HTMLInputElement> {
  state?: FieldValidationState
}

export function Input({ className, state = "default", ...props }: InputProps) {
  return (
    <input
      aria-invalid={state === "error" || undefined}
      className={cn(
        "h-9 w-full rounded-md border bg-bg px-3 text-sm text-ink transition-colors placeholder:text-muted focus-visible:outline-2 focus-visible:outline-offset-0 disabled:cursor-not-allowed disabled:bg-bg-secondary disabled:opacity-50",
        stateClasses[state],
        className,
      )}
      {...props}
    />
  )
}

export interface TextareaProps extends TextareaHTMLAttributes<HTMLTextAreaElement> {
  state?: FieldValidationState
}

export function Textarea({ className, state = "default", ...props }: TextareaProps) {
  return (
    <textarea
      aria-invalid={state === "error" || undefined}
      className={cn(
        "min-h-[88px] w-full rounded-md border bg-bg px-3 py-2 text-sm text-ink transition-colors placeholder:text-muted focus-visible:outline-2 focus-visible:outline-offset-0 disabled:cursor-not-allowed disabled:bg-bg-secondary disabled:opacity-50",
        stateClasses[state],
        className,
      )}
      {...props}
    />
  )
}

export function FormField({
  label,
  hint,
  message,
  state = "default",
  children,
  className,
}: {
  label?: string
  hint?: string
  message?: string
  state?: FieldValidationState
  children: ReactNode
  className?: string
}) {
  const messageTone = {
    default: "text-muted",
    error: "text-error",
    warning: "text-warning",
    success: "text-success",
  }[state]

  return (
    <div className={cn("space-y-1.5", className)}>
      {label ? (
        <div className="flex items-center justify-between gap-2">
          <label className="text-xs font-medium text-ink">{label}</label>
          {hint ? <span className="text-[11px] text-muted">{hint}</span> : null}
        </div>
      ) : null}
      {children}
      {message ? <p className={cn("text-xs", messageTone)}>{message}</p> : null}
    </div>
  )
}
