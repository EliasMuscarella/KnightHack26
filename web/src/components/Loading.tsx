import { PageContainer, Skeleton } from "@/components/ui";

export function PageLoading({ label, variant = "list" }: { label: string; variant?: "list" | "detail" | "grid" | "text" }) {
  return (
    <PageContainer className="py-10">
      <p role="status" className="mb-6 flex items-center gap-2 text-sm text-ink-secondary">
        <span aria-hidden="true" className="rd-spin inline-block h-4 w-4 rounded-full border-2 border-line border-t-ink" />
        {label}
      </p>
      <Skeleton className="h-4 w-24" />
      <Skeleton className="mt-3 h-9 w-[520px]" />
      {variant === "grid" ? (
        <div className="mt-8 grid grid-cols-3 gap-5">
          {Array.from({ length: 6 }).map((_, i) => (
            <Skeleton key={i} className="h-44" />
          ))}
        </div>
      ) : variant === "detail" ? (
        <div className="mt-8 grid grid-cols-[minmax(0,1fr)_400px] gap-8">
          <div className="space-y-3">
            {Array.from({ length: 10 }).map((_, i) => (
              <Skeleton key={i} className="h-6" />
            ))}
          </div>
          <Skeleton className="h-[420px]" />
        </div>
      ) : variant === "text" ? (
        <div className="mt-8 max-w-[80ch] space-y-3">
          {Array.from({ length: 8 }).map((_, i) => (
            <Skeleton key={i} className="h-5" />
          ))}
        </div>
      ) : (
        <div className="mt-8 space-y-3">
          <div className="flex gap-4">
            <Skeleton className="h-48 flex-1" />
            <Skeleton className="h-48 flex-1" />
          </div>
          {Array.from({ length: 6 }).map((_, i) => (
            <Skeleton key={i} className="h-16" />
          ))}
        </div>
      )}
    </PageContainer>
  );
}
