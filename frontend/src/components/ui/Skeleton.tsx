import type { CSSProperties } from "react";

export function Skeleton({ className = "", style }: { className?: string; style?: CSSProperties }) {
  return <div className={`skeleton ${className}`.trim()} style={style} />;
}

export function KpiSkeleton() {
  return (
    <div className="card kpi" aria-hidden>
      <Skeleton style={{ height: 12, width: "55%" }} />
      <Skeleton style={{ height: 28, width: "45%" }} />
      <Skeleton style={{ height: 12, width: "70%", marginTop: "auto" }} />
    </div>
  );
}

export function KpiGridSkeleton({ count = 4 }: { count?: number }) {
  return (
    <div className="kpi-grid" aria-busy="true">
      {Array.from({ length: count }, (_, i) => (
        <KpiSkeleton key={i} />
      ))}
    </div>
  );
}

export function BoardSkeleton({ cols = 4, rows = 3 }: { cols?: number; rows?: number }) {
  return (
    <div className="board" aria-busy="true">
      {Array.from({ length: cols }, (_, c) => (
        <div className="board-col" key={c}>
          <Skeleton style={{ height: 14, width: "60%", marginBottom: 4 }} />
          {Array.from({ length: rows }, (_, r) => (
            <div className="task-card" key={r} aria-hidden>
              <Skeleton style={{ height: 13, width: "80%" }} />
              <Skeleton style={{ height: 12, width: "55%" }} />
            </div>
          ))}
        </div>
      ))}
    </div>
  );
}