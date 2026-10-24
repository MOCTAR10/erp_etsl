import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Check, Plus } from "lucide-react";
import { useEffect, useId, useRef, useState, type FormEvent } from "react";
import { useTranslation } from "react-i18next";

import { api } from "../../api/client";
import { describeError } from "../../lib/offlineQueue";
import { DatePicker } from "./DatePicker";
import { Sheet } from "./Sheet";
import { notify } from "./Toaster";

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

/** Délai d'affichage de « Enregistré. » dans le panneau avant sa fermeture (retour visuel, puis liste visible). */
const CLOSE_DELAY = 700;
/** Le rappel « Enregistré. » près du bouton s'efface ensuite. */
const DONE_TTL = 8000;

/**
 * Formulaire de création (saisie depuis les écrans métier) : un bouton ouvre un panneau latéral (`Sheet`) ;
 * POST sur l'endpoint DRF, erreurs de validation du serveur affichées telles quelles dans le panneau,
 * notification (toast) au succès comme à l'échec, listes rechargées au succès. Les droits restent côté API.
 * Le `<form>` porte le nom `title` (tests : `getByRole("form", { name })`) et contient son bouton d'envoi.
 */
export function QuickForm({
  title,
  endpoint,
  fields,
  submitLabel,
  transform,
  variant = "primary",
}: {
  title: string;
  endpoint: string;
  fields: QuickField[];
  submitLabel?: string;
  /** Mise en forme du corps avant envoi (ex. champs vides retirés, numériques convertis). */
  transform?: (values: Record<string, string>) => Record<string, unknown>;
  /**
   * Style du déclencheur : `primary` (défaut, action principale d'un écran) ou `secondary`. Dans une carte, une
   * barre d'actions de section ou une barre d'outils, le déclencheur est de toute façon rendu secondaire (CSS) :
   * un seul primaire par écran.
   */
  variant?: "primary" | "secondary";
}) {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const uid = useId();
  const formId = `${uid}-form`;
  const initial = () => Object.fromEntries(fields.map((f) => [f.name, f.defaultValue ?? ""]));
  const [open, setOpen] = useState(false);
  const [values, setValues] = useState<Record<string, string>>(initial);
  const [message, setMessage] = useState<{ ok: boolean; text: string } | null>(null);
  // Rappel « Enregistré. » près du bouton, une fois le panneau refermé (après son animation de sortie).
  const [done, setDone] = useState(false);
  const timers = useRef<number[]>([]);
  const later = (fn: () => void, ms: number) => {
    timers.current.push(window.setTimeout(fn, ms));
  };
  useEffect(() => () => timers.current.forEach((id) => window.clearTimeout(id)), []);

  const dirty = Object.entries(values).some(([k, v]) => v !== (fields.find((f) => f.name === k)?.defaultValue ?? ""));

  const send = useMutation({
    mutationFn: () => {
      const cleaned = Object.fromEntries(Object.entries(values).filter(([, v]) => v !== ""));
      return api.post<unknown>(endpoint, transform ? transform(cleaned) : cleaned);
    },
    onSuccess: () => {
      setMessage({ ok: true, text: t("quickForm.created") });
      setValues(initial());
      void qc.invalidateQueries();
      notify.success(t("formulaires.quickForm.toastOk"), { description: title });
      later(() => {
        setOpen(false);
        later(() => {
          setDone(true);
          later(() => setDone(false), DONE_TTL);
        }, 400);
      }, CLOSE_DELAY);
    },
    onError: (e) => {
      const text = describeError(e);
      setMessage({ ok: false, text });
      notify.error(t("formulaires.quickForm.toastErr"), { description: text });
    },
  });

  const openSheet = () => {
    timers.current.forEach((id) => window.clearTimeout(id));
    timers.current = [];
    setMessage(null);
    setDone(false);
    setOpen(true);
  };

  const submit = (e: FormEvent) => {
    e.preventDefault();
    setMessage(null);
    send.mutate();
  };

  return (
    <span className="quick-form-anchor" {...(done && !open ? { role: "form", "aria-label": title } : {})}>
      <button type="button" className={`btn ${variant === "secondary" ? "ghost" : "primary"}`} onClick={openSheet}>
        <Plus size={16} aria-hidden="true" /> {title}
      </button>
      {done && !open ? (
        <span className="quick-form-done" role="status">
          <Check size={14} aria-hidden="true" />
          {t("quickForm.created")}
        </span>
      ) : null}
      <Sheet
        open={open}
        onOpenChange={setOpen}
        title={title}
        width={480}
        preventOutsideClose={dirty || send.isPending}
        className="quick-form-sheet"
      >
        <form id={formId} className="quick-form" onSubmit={submit} aria-label={title}>
          <div className="quick-form-fields">
            {fields.map((f) => {
              const id = `${uid}-${f.name}`;
              const set = (v: string) => setValues((cur) => ({ ...cur, [f.name]: v }));
              const common = {
                id,
                name: f.name,
                required: f.required,
                value: values[f.name] ?? "",
                onChange: (e: { target: { value: string } }) => set(e.target.value),
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
                  ) : f.type === "date" ? (
                    <DatePicker id={id} value={values[f.name] ?? ""} onChange={set} required={f.required} />
                  ) : (
                    <input type={f.type ?? "text"} min={f.min} step={f.step} {...common} />
                  )}
                </div>
              );
            })}
          </div>
          <div className="quick-form-foot">
            <div className="quick-form-feedback">
              {message ? (
                <p className={message.ok ? "quick-form-ok" : "action-error"} role={message.ok ? "status" : "alert"}>
                  {message.ok ? <Check size={14} aria-hidden="true" /> : null}
                  {message.text}
                </p>
              ) : fields.some((f) => f.required) ? (
                <p className="quick-form-hint">{t("formulaires.quickForm.requis")}</p>
              ) : null}
            </div>
            <button type="button" className="btn ghost" onClick={() => setOpen(false)}>
              {t("actionBar.annuler")}
            </button>
            <button type="submit" className="btn primary" disabled={send.isPending}>
              {send.isPending ? t("common.loading") : (submitLabel ?? t("quickForm.save"))}
            </button>
          </div>
        </form>
      </Sheet>
    </span>
  );
}
