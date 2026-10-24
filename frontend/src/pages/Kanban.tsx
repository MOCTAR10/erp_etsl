import { useQuery } from "@tanstack/react-query";
import { AnimatePresence } from "motion/react";
import { CalendarClock, Check, FileText, Inbox, UserRound, XCircle } from "lucide-react";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";

import { api } from "../api/client";
import { formatDate } from "../lib/format";
import { cleanLabel } from "../components/workflow/libelle";
import { ConfirmDialog, useServerAction } from "../components/workflow/actions";
import { Badge, Board, BoardCard, BoardColumn, EmptyState, ErrorState, Menu, PageHeader, BoardSkeleton } from "../components/ui";
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

/** Carte de tâche sobre : document, circuit / étape, échéance ; une action principale et le menu ⋯. */
function TaskCard({ task, locale, index }: { task: WorkflowTask; locale: string; index: number }) {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const [rejet, setRejet] = useState(false);
  const action = useServerAction([["tasks"]]);
  const ouverte = task.status === "pending" || task.status === "delegated";
  const overdue = ouverte && new Date(task.due_date) < new Date();
  return (
    <BoardCard delay={Math.min(index * 0.03, 0.3)} className="kb-card">
      <div className="kb-card-head">
        <span className="title">{task.document_title}</span>
        <Menu
          size="sm"
          label={t("kanban2.actions", { titre: task.document_title })}
          items={[
            { label: t("kanban2.ouvrirGed"), icon: FileText, onSelect: () => navigate("/documents") },
            ouverte && "separator",
            ouverte && { label: t("kanban2.rejeter"), icon: XCircle, danger: true, onSelect: () => setRejet(true) },
          ]}
        />
      </div>
      <div className="meta kb-step">
        {cleanLabel(task.circuit_label)} · {task.step_name}
      </div>
      <div className="meta kb-foot">
        <span className={`kb-due${overdue ? " is-late" : ""}`}>
          <CalendarClock size={13} aria-hidden />
          {formatDate(task.due_date, locale)}
        </span>
        {overdue ? <Badge tone="err">{t("kanban.overdue")}</Badge> : null}
        {task.assigned_to_email ? (
          <span className="kb-assignee" title={task.assigned_to_email}>
            <UserRound size={13} aria-hidden />
            <span className="sr-only">{t("kanban.assigned")} : </span>
            <span className="kb-assignee-mail">{task.assigned_to_email}</span>
          </span>
        ) : null}
      </div>
      {ouverte ? (
        <button
          type="button"
          className="btn primary sm kb-primary"
          disabled={action.isPending}
          onClick={() => action.mutate({ path: `/api/workflow/tasks/${task.id}/complete/`, success: t("kanban2.valide", { titre: task.document_title }) })}
        >
          <Check size={15} aria-hidden />
          {t("kanban2.valider")}
        </button>
      ) : null}
      <ConfirmDialog
        open={rejet}
        onOpenChange={setRejet}
        title={t("kanban2.rejeterTitre")}
        description={task.document_title}
        confirmLabel={t("kanban2.rejeter")}
        danger
        field={{ label: t("kanban2.motif"), type: "textarea" }}
        onConfirm={(reason) =>
          action.mutate({ path: `/api/workflow/tasks/${task.id}/reject/`, body: { reason }, success: t("kanban2.rejete", { titre: task.document_title }) })
        }
      />
    </BoardCard>
  );
}

export function KanbanPage() {
  const { t, i18n } = useTranslation();
  const { data, isLoading, isError, refetch } = useQuery({
    queryKey: ["tasks"],
    queryFn: api.tasks,
  });

  const header = (n?: number) => (
    <PageHeader title={t("kanban.title")} subtitle={n === undefined ? t("kanban2.sub") : n === 0 ? t("kanban2.aucune") : t("kanban2.total", { count: n })} />
  );
  if (isLoading)
    return (
      <>
        {header()}
        <BoardSkeleton cols={4} rows={3} />
      </>
    );
  if (isError || !data)
    return (
      <>
        {header()}
        <ErrorState message={t("common.error")} onRetry={() => void refetch()} retryLabel={t("common.retry")} />
      </>
    );

  const groups = groupByStatus(data);

  return (
    <>
      {header(data.length)}
      <Board className="kb-board">
        {COLUMNS.map((col, ci) => (
          <BoardColumn key={col.status} title={t(`kanban.${col.status}`)} count={groups[col.status].length} tone={col.badge} delay={ci * 0.04}>
            {groups[col.status].length === 0 ? (
              <EmptyState icon={Inbox} label={t(`kanban2.vide.${col.status}`)} compact />
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
