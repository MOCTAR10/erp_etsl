import { AlertCircle } from "lucide-react";

export function ErrorState({
  message,
  onRetry,
  retryLabel,
}: {
  message: string;
  onRetry?: () => void;
  retryLabel?: string;
}) {
  return (
    <div className="empty-state">
      <AlertCircle size={28} aria-hidden />
      <div>{message}</div>
      {onRetry ? (
        <button className="btn ghost" onClick={onRetry}>
          {retryLabel ?? "Réessayer"}
        </button>
      ) : null}
    </div>
  );
}