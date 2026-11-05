import { cn } from "@/lib/utils"

type SectionHeadingProps = {
  eyebrow: string
  title: string
  description?: string
  className?: string
  tone?: "light" | "dark"
}

export function SectionHeading({
  eyebrow,
  title,
  description,
  className,
  tone = "light",
}: SectionHeadingProps) {
  const dark = tone === "dark"
  return (
    <div className={cn("max-w-3xl", className)}>
      <p className={cn("eyebrow", dark && "text-sage")}>{eyebrow}</p>
      <h2
        className={cn(
          "mt-4 text-4xl leading-[1.04] text-ink sm:text-5xl lg:text-[3.4rem]",
          "editorial",
          dark && "text-paper",
        )}
      >
        {title}
      </h2>
      {description ? (
        <p
          className={cn(
            "mt-5 max-w-2xl text-base leading-7 text-muted-foreground sm:text-[1.05rem]",
            dark && "text-paper/70",
          )}
        >
          {description}
        </p>
      ) : null}
    </div>
  )
}
