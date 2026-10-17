import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Plus, X } from "lucide-react";
import { useId, useState, type FormEvent } from "react";
import { useTranslation } from "react-i18next";

import { api } from "../../api/client";
import { describeError } from "../../lib/offlineQueue";

export interface QuickField {
  name: string;
  label: string;
  type?: "text" | "textarea" | "number" | "date" | "datetime-local" | "select";
  options?: { value: string; label: string }[];
  required?: boolean;
  defaultValue?: string;
  min?: number;
  step?: string;
}

/**
 * Formulaire de création compact (saisie depuis les écrans métier) : POST sur l'endpoint DRF, erreurs de
 * validation du serveur affichées telles quelles, listes rechargées au succès. Les droits restent côté API.
 */
export function QuickForm({
  title,
  endpoint,
  fields,
  submitLabel,
  transform,
}: {
  title: string;
  endpoint: string;
  fields: QuickField[];
  submitLabel?: string;
  /** Mise en forme du corps avant envoi (ex. champs vides retirés, numériques convertis). */
  transform?: (values: Record<string, string>) => Record<string, unknown>;
}) {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const uid = useId();
  const initial = () => Object.fromEntries(fields.map((f) => [f.name, f.defaultValue ?? ""]));
  const [open, setOpen] = useState(false);
  const [values, setValues] = useState<Record<string, string>>(initial);
  const [message, setMessage] = useState<{ ok: boolean; text: string } | null>(null);

  const send = useMutation({
    mutationFn: () => {
      const cleaned = Object.fromEntries(Object.entries(values).filter(([, v]) => v !== ""));
      return api.post<unknown>(endpoint, transform ? transform(cleaned) : cleaned);
    },
    onSuccess: () => {
      setMessage({ ok: true, text: t("quickForm.created") });
      setValues(initial());
      void qc.invalidateQueries();
    },
    onError: (e) => setMessage({ ok: false, text: describeError(e) }),
  });

  if (!open)
    return (
      <button type="button" className="btn primary" onClick={() => setOpen(true)}>
        <Plus size={16} aria-hidden="true" /> {title}
      </button>
    );

  const submit = (e: FormEvent) => {
    e.preventDefault();
    setMessage(null);
    send.mutate();
  };

  return (
    <form className="card quick-form" onSubmit={submit} aria-label={title}>
      <div className="quick-form-head">
        <strong>{title}</strong>
        <button type="button" className="icon-btn" aria-label={t("quickForm.close")} onClick={() => setOpen(false)}>
          <X size={16} aria-hidden="true" />
        </button>
      </div>
      <div className="quick-form-grid">
        {fields.map((f) => {
          const id = `${uid}-${f.name}`;
          const common = {
            id,
            name: f.name,
            required: f.required,
            value: values[f.name] ?? "",
            onChange: (e: { target: { value: string } }) => setValues((v) => ({ ...v, [f.name]: e.target.value })),
          };
          return (
            <div key={f.name} className={`field${f.type === "textarea" ? " wide" : ""}`}>
              <label htmlFor={id}>
                {f.label}
                {f.required ? " *" : ""}
              </label>
              {f.type === "select" ? (
                <select {...common}>
                  {!f.required || !f.defaultValue ? <option value="">—</option> : null}
                  {(f.options ?? []).map((o) => (
                    <option key={o.value} value={o.value}>
                      {o.label}
                    </option>
                  ))}
                </select>
              ) : f.type === "textarea" ? (
                <textarea rows={3} {...common} />
              ) : (
                <input type={f.type ?? "text"} min={f.min} step={f.step} {...common} />
              )}
            </div>
          );
        })}
      </div>
      <div className="quick-form-actions">
        <button type="submit" className="btn primary" disabled={send.isPending}>
          {send.isPending ? t("common.loading") : (submitLabel ?? t("quickForm.save"))}
        </button>
        {message && (
          <p className={message.ok ? "quick-form-ok" : "action-error"} role={message.ok ? "status" : "alert"}>
            {message.text}
          </p>
        )}
      </div>
    </form>
  );
}
