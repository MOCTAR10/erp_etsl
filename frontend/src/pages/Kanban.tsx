import { useQuery } from "@tanstack/react-query";
import { AnimatePresence, motion } from "motion/react";
import { useTranslation } from "react-i18next";

import { api } from "../api/client";
import { formatDate } from "../lib/format";
import { motionTokens } from "../theme/tokens";
import type { TaskStatus, WorkflowTask } from "../types";

const COLUMNS: Array<{ status: TaskStatus; badge: "brand" | "warn" | "ok" | "err" }> = [
  { status: "pending", badge: "brand" },
  { status: "delegated", badge: "warn" },
  { status: "done", badge: "ok" },
  { status: "rejected", badge: "err" },
];

function groupByStatus(tasks: WorkflowTask[]): Record<TaskStatus, WorkflowTask[]> {
  const groups: Record<TaskStatus, WorkflowTask[]> = {
    pending: [],
    done: [],
    rejected: [],
    delegated: [],
  };
  for (const task of tasks) groups[task.status].push(task);
  return groups;
}

function TaskCard({ task, locale }: { task: WorkflowTask; locale: string }) {
  const { t } = useTranslation();
  const overdue = task.status === "pending" && new Date(task.due_date) < new Date();
  return (
    <motion.div
      layout
      initial={{ opacity: 0, y: motionTokens.distance.xs, scale: 0.98 }}
      animate={{ opacity: 1, y: 0, scale: 1 }}
      exit={{ opacity: 0, scale: 0.96 }}
      transition={{ duration: motionTokens.duration.base, ease: motionTokens.ease.out }}
      className="task-card"
    >
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
        {overdue ? (
          <span className="badge err">{t("kanban.overdue")}</span>
        ) : null}
      </div>
    </motion.div>
  );
}

export function KanbanPage() {
  const { t, i18n } = useTranslation();
  const { data, isLoading, isError, refetch } = useQuery({
    queryKey: ["tasks"],
    queryFn: api.tasks,
  });

  if (isLoading) return <p className="muted">{t("common.loading")}</p>;
  if (isError || !data)
    return (
      <p>
        {t("common.error")}{" "}
        <button className="btn ghost" onClick={() => void refetch()}>
          {t("common.retry")}
        </button>
      </p>
    );

  const groups = groupByStatus(data);

  return (
    <>
      <h2>{t("kanban.title")}</h2>
      <div className="board">
        {COLUMNS.map((col) => (
          <motion.div
            key={col.status}
            layout
            className="board-col"
            initial={{ opacity: 0, y: motionTokens.distance.sm }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: motionTokens.duration.base, ease: motionTokens.ease.out }}
          >
            <div className="board-col-head">
              <span>{t(`kanban.${col.status}`)}</span>
              <span className={`badge ${col.badge}`}>{groups[col.status].length}</span>
            </div>
            <AnimatePresence initial={false}>
              {groups[col.status].map((task) => (
                <TaskCard key={task.id} task={task} locale={i18n.language} />
              ))}
            </AnimatePresence>
          </motion.div>
        ))}
      </div>
    </>
  );
}