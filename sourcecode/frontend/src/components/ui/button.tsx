import { cva, type VariantProps } from "class-variance-authority"
import { Loader2 } from "lucide-react"
import type { ButtonHTMLAttributes, ReactNode } from "react"
import { cn } from "@/utils/cn"

const buttonVariants = cva(
  "inline-flex items-center justify-center gap-2 whitespace-nowrap rounded-xl text-sm font-medium transition-all select-none focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand disabled:pointer-events-none disabled:opacity-45",
  {
    variants: {
      variant: {
        default: "bg-primary text-primary-fg shadow-xs hover:opacity-92",
        secondary: "bg-brand-soft text-brand hover:bg-bg-active",
        outline: "border border-line bg-bg text-ink hover:bg-bg-hover active:bg-bg-active",
        ghost: "text-ink hover:bg-bg-hover active:bg-bg-active",
        danger: "border border-transparent text-error hover:bg-error-soft",
        success: "border border-success/30 bg-success-soft text-success hover:opacity-90",
        warning: "border border-warning/30 bg-warning-soft text-warning hover:opacity-90",
      },
      size: {
        xs: "h-7 px-2.5 text-xs",
        sm: "h-8 px-3 text-xs",
        md: "h-9 px-3.5 text-sm",
        lg: "h-10 px-4 text-sm",
        icon: "h-8 w-8 p-0",
      },
    },
    defaultVariants: { variant: "default", size: "md" },
  },
)

export interface ButtonProps
  extends ButtonHTMLAttributes<HTMLButtonElement>,
    VariantProps<typeof buttonVariants> {
  loading?: boolean
  leftIcon?: ReactNode
}

export function Button({
  className,
  variant,
  size,
  type = "button",
  loading = false,
  leftIcon,
  disabled,
  children,
  ...props
}: ButtonProps) {
  return (
    <button
      type={type}
      disabled={disabled || loading}
      aria-busy={loading || undefined}
      className={cn(buttonVariants({ variant, size }), className)}
      {...props}
    >
      {loading ? <Loader2 className="h-3.5 w-3.5 shrink-0 animate-spin" /> : leftIcon}
      {children}
    </button>
  )
}
