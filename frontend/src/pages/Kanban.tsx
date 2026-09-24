import { useQuery } from "@tanstack/react-query";
import { AnimatePresence } from "motion/react";
import { Inbox } from "lucide-react";
import { useTranslation } from "react-i18next";

import { api } from "../api/client";
import { formatDate } from "../lib/format";
import { Board, BoardCard, BoardColumn, EmptyState, ErrorState, PageHeader, BoardSkeleton } from "../components/ui";
import type { BadgeTone } from "../components/ui";
import type { TaskStatus, WorkflowTask } from "../types";

const COLUMNS: Array<{ status: TaskStatus; badge: BadgeTone }> = [
  { status: "pending", badge: "brand" },
  { status: "delegated", badge: "warn" },
  { status: "done", badge: "ok" },
  { status: "rejected", badge: "err" },
];

function groupByStatus(tasks: WorkflowTask[]): Record<TaskStatus, WorkflowTask[]> {
  const groups: Record<TaskStatus, WorkflowTask[]> = { pending: [], done: [], rejected: [], delegated: [] };
  for (const task of tasks) groups[task.status].push(task);
  return groups;
}

function TaskCard({ task, locale, index }: { task: WorkflowTask; locale: string; index: number }) {
  const { t } = useTranslation();
  const overdue = task.status === "pending" && new Date(task.due_date) < new Date();
  return (
    <BoardCard delay={Math.min(index * 0.03, 0.3)}>
      <div className="title">{task.document_title}</div>
      <div className="meta">
        {task.circuit_label} · {task.step_name}
      </div>
      <div className="meta">
        {t("kanban.assigned")}: {task.assigned_to_email ?? "—"}
      </div>
      <div className="meta" style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <span>
          {t("kanban.due")}: {formatDate(task.due_date, locale)}
        </span>
        {overdue ? <span className="badge err">{t("kanban.overdue")}</span> : null}
      </div>
    </BoardCard>
  );
}

export function KanbanPage() {
  const { t, i18n } = useTranslation();
  const { data, isLoading, isError, refetch } = useQuery({
    queryKey: ["tasks"],
    queryFn: api.tasks,
  });

  if (isLoading) return <BoardSkeleton cols={4} rows={3} />;
  if (isError || !data)
    return <ErrorState message={t("common.error")} onRetry={() => void refetch()} retryLabel={t("common.retry")} />;

  const groups = groupByStatus(data);
  const total = data.length;

  return (
    <>
      <PageHeader
        title={t("kanban.title")}
        subtitle={`${total} ${t("kanban.tasks")}`}
      />
      <Board>
        {COLUMNS.map((col, ci) => (
          <BoardColumn
            key={col.status}
            title={t(`kanban.${col.status}`)}
            count={groups[col.status].length}
            tone={col.badge}
            delay={ci * 0.05}
          >
            {groups[col.status].length === 0 ? (
              <EmptyState icon={Inbox} label={t("common.empty")} />
            ) : (
              <AnimatePresence initial={false}>
                {groups[col.status].map((task, i) => (
                  <TaskCard key={task.id} task={task} locale={i18n.language} index={i} />
                ))}
              </AnimatePresence>
            )}
          </BoardColumn>
        ))}
      </Board>
    </>
  );
}