import { useMutation, useQueryClient } from "@tanstack/react-query";
import type { QueryKey } from "@tanstack/react-query";
import { useId, useState } from "react";
import type { FormEvent, ReactElement, ReactNode } from "react";
import { useTranslation } from "react-i18next";

import { api } from "../../api/client";
import { describeError } from "../../lib/offlineQueue";
import { Modal, SheetClose, notify } from "../ui";

export interface PostAction {
  path: string;
  body?: unknown;
  method?: "POST" | "PATCH";
  /** Message du retour de succès (notification). */
  success: string;
}

/**
 * Action serveur avec retour par notification : succès → `notify.success` puis rechargement des requêtes
 * (`invalidate` ou toutes), refus → `notify.error` avec le motif du serveur. La garde reste côté API.
 */
export function useServerAction(invalidate?: QueryKey[]) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (a: PostAction) => (a.method === "PATCH" ? api.patch<unknown>(a.path, a.body ?? {}) : api.post<unknown>(a.path, a.body)),
    onSuccess: (_r, a) => {
      notify.success(a.success);
      if (invalidate) invalidate.forEach((queryKey) => void qc.invalidateQueries({ queryKey }));
      else void qc.invalidateQueries();
    },
    onError: (e) => notify.error(describeError(e)),
  });
}

/**
 * Fenêtre de confirmation (modale) d'une action engageante. Contrôlée (`open`/`onOpenChange`) ou ouverte par `trigger`.
 * Avec `field`, demande une valeur (motif, délai…) transmise à `onConfirm`.
 */
export function ConfirmDialog({
  open,
  onOpenChange,
  trigger,
  title,
  description,
  confirmLabel,
  danger = false,
  field,
  onConfirm,
}: {
  open?: boolean;
  onOpenChange?: (open: boolean) => void;
  trigger?: ReactElement;
  title: ReactNode;
  description?: ReactNode;
  confirmLabel: string;
  danger?: boolean;
  field?: {
    label: string;
    type?: "text" | "number" | "select" | "textarea";
    options?: { value: string; label: string }[];
    initial?: string;
    min?: number;
    required?: boolean;
  };
  onConfirm: (value: string) => void;
}) {
  const { t } = useTranslation();
  const uid = useId();
  const [inner, setInner] = useState(false);
  const isOpen = open ?? inner;
  const [value, setValue] = useState(field?.initial ?? "");
  const setOpen = (v: boolean) => {
    if (v) setValue(field?.initial ?? "");
    if (open === undefined) setInner(v);
    onOpenChange?.(v);
  };
  const formId = `${uid}-form`;
  const confirm = () => {
    if (field && field.required !== false && value.trim() === "") return;
    onConfirm(value);
    setOpen(false);
  };
  const submit = (e: FormEvent) => {
    e.preventDefault();
    confirm();
  };
  const inputProps = {
    id: `${uid}-input`,
    className: "control",
    value,
    required: field?.required !== false,
    autoFocus: true,
  };
  return (
    <Modal
      open={isOpen}
      onOpenChange={setOpen}
      trigger={trigger}
      title={title}
      description={description}
      width={460}
      footer={
        <>
          <SheetClose>
            <button type="button" className="btn ghost">
              {t("actionBar.annuler")}
            </button>
          </SheetClose>
          {field ? (
            <button type="submit" form={formId} className={`btn ${danger ? "danger" : "primary"}`}>
              {confirmLabel}
            </button>
          ) : (
            <button type="button" className={`btn ${danger ? "danger" : "primary"}`} onClick={confirm}>
              {confirmLabel}
            </button>
          )}
        </>
      }
    >
      {field ? (
        <form id={formId} onSubmit={submit} className="wf-confirm-form">
          <div className="field">
            <label htmlFor={`${uid}-input`}>{field.label}</label>
            {field.type === "select" ? (
              <select {...inputProps} onChange={(e) => setValue(e.target.value)}>
                <option value="">—</option>
                {(field.options ?? []).map((o) => (
                  <option key={o.value} value={o.value}>
                    {o.label}
                  </option>
                ))}
              </select>
            ) : field.type === "textarea" ? (
              <textarea {...inputProps} rows={3} onChange={(e) => setValue(e.target.value)} />
            ) : (
              <input {...inputProps} type={field.type ?? "text"} min={field.min} onChange={(e) => setValue(e.target.value)} />
            )}
          </div>
        </form>
      ) : null}
    </Modal>
  );
}
