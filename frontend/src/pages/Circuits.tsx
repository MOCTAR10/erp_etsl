import { useQuery } from "@tanstack/react-query";
import { ArrowDown, ArrowUp, Clock, Pencil, Plus, Power, Trash2, UserCog, Workflow } from "lucide-react";
import { useId, useState } from "react";
import type { FormEvent, ReactElement } from "react";
import { useTranslation } from "react-i18next";

import { api } from "../api/client";
import { formatNumber } from "../lib/format";
import { cleanLabel } from "../components/workflow/libelle";
import { ConfirmDialog, useServerAction } from "../components/workflow/actions";
import { Badge, BoardSkeleton, DataGrid, EmptyState, ErrorState, Menu, PageHeader, Sheet, SheetClose } from "../components/ui";
import type { GridColumn } from "../components/ui";
import { useAuth } from "../store/auth";
import type { Circuit, CircuitStep, Paginated } from "../types";

/** Rôles autorisés à modifier les circuits à chaud — le serveur reste la garde. */
const GESTION_CIRCUITS = ["admin", "pdg", "dga"];
/** Secours si `/api/users/roles/` est indisponible ; la liste de référence vient du serveur (`User.Role`). */
const ROLES_SECOURS: Record<string, string> = {
  pdg: "PDG",
  dga: "DGA",
  secretaire_general: "Secrétariat général",
  directeur_projets: "Directeur projets",
  directeur_operations: "Directeur des opérations",
  rh: "Ressources humaines",
  finance: "Finance / comptabilité / contrôle de gestion",
  qaqc: "Qualité (QA/QC)",
  hse: "HSE",
  logistique: "Logistique",
  maintenance: "Maintenance",
  chef_atelier: "Chef d'atelier",
  charge_affaires: "Chargé d'affaires",
  controleur_gestion: "Contrôleur de gestion",
  admin: "Administrateur",
  direction: "Direction",
  chef_service: "Chef de service",
  comptable: "Comptable",
};

type Option = { value: string; label: string };
type Field = { name: string; label: string; type?: "text" | "number" | "select"; options?: Option[]; initial?: string; min?: number };

/** Identifiant technique d'un nouveau circuit, déduit du libellé (jamais saisi ni affiché). */
const slug = (label: string) =>
  `circuit_${label
    .normalize("NFD")
    .replace(/[̀-ͯ]/g, "")
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "_")
    .replace(/^_|_$/g, "")
    .slice(0, 40)}`;

/** Formulaire en panneau latéral (création de circuit, ajout d'étape). */
function FormSheet({
  title,
  description,
  trigger,
  fields,
  submitLabel,
  onSubmit,
}: {
  title: string;
  description?: string;
  trigger: ReactElement;
  fields: Field[];
  submitLabel: string;
  onSubmit: (values: Record<string, string>) => void;
}) {
  const { t } = useTranslation();
  const uid = useId();
  const [open, setOpen] = useState(false);
  const submit = (e: FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    const values = Object.fromEntries(new FormData(e.currentTarget).entries()) as Record<string, string>;
    onSubmit(values);
    setOpen(false);
  };
  return (
    <Sheet
      open={open}
      onOpenChange={setOpen}
      trigger={trigger}
      title={title}
      description={description}
      width={440}
      footer={
        <>
          <SheetClose>
            <button type="button" className="btn ghost">
              {t("actionBar.annuler")}
            </button>
          </SheetClose>
          <button type="submit" form={`${uid}-form`} className="btn primary">
            {submitLabel}
          </button>
        </>
      }
    >
      <form id={`${uid}-form`} onSubmit={submit}>
        {fields.map((f, i) => (
          <div className="field" key={f.name}>
            <label htmlFor={`${uid}-${f.name}`}>{f.label}</label>
            {f.type === "select" ? (
              <select id={`${uid}-${f.name}`} name={f.name} className="control" required defaultValue={f.initial ?? ""} autoFocus={i === 0}>
                <option value="">—</option>
                {(f.options ?? []).map((o) => (
                  <option key={o.value} value={o.value}>
                    {o.label}
                  </option>
                ))}
              </select>
            ) : (
              <input
                id={`${uid}-${f.name}`}
                name={f.name}
                className="control"
                type={f.type ?? "text"}
                min={f.min}
                required
                defaultValue={f.initial}
                autoFocus={i === 0}
              />
            )}
          </div>
        ))}
      </form>
    </Sheet>
  );
}

type Edition = { kind: "delai" | "acteur" | "retirer"; step: CircuitStep } | { kind: "renommer" | "activation" } | null;

function CircuitCard({ circuit, gestion, roleOpts }: { circuit: Circuit; gestion: boolean; roleOpts: Option[] }) {
  const { t } = useTranslation();
  const [edit, setEdit] = useState<Edition>(null);
  const action = useServerAction([["circuits"]]);
  const base = `/api/workflow/circuits/${circuit.id}`;
  const label = cleanLabel(circuit.label);
  const steps = [...circuit.steps].sort((a, b) => a.order - b.order);

  const columns: GridColumn<CircuitStep>[] = [
    { key: "order", header: "#", width: 48, render: (s) => <span className="circ-order">{s.order}</span> },
    { key: "name", header: t("circuits2.etape"), render: (s) => <strong className="circ-step">{s.name}</strong> },
    { key: "actor", header: t("circuits.actor"), render: (s) => <span className="circ-actor">{s.actor_role_label}</span> },
    { key: "days", header: t("circuits2.delai"), num: true, width: 110, render: (s) => t("circuits2.jours", { count: s.max_days }) },
  ];

  const rowActions = (s: CircuitStep) => [
    { label: t("circuits2.monter"), icon: ArrowUp, disabled: s.order === steps[0]?.order, onSelect: () => action.mutate({ path: `${base}/deplacer-etape/`, body: { etape: s.id, sens: "haut" }, success: t("circuits2.deplace") }) },
    { label: t("circuits2.descendre"), icon: ArrowDown, disabled: s.order === steps[steps.length - 1]?.order, onSelect: () => action.mutate({ path: `${base}/deplacer-etape/`, body: { etape: s.id, sens: "bas" }, success: t("circuits2.deplace") }) },
    "separator" as const,
    { label: t("circuits2.modifierDelai"), icon: Clock, onSelect: () => setEdit({ kind: "delai", step: s }) },
    { label: t("circuits2.changerActeur"), icon: UserCog, onSelect: () => setEdit({ kind: "acteur", step: s }) },
    "separator" as const,
    { label: t("ecarts_tr.circuits.retirer"), icon: Trash2, danger: true, onSelect: () => setEdit({ kind: "retirer", step: s }) },
  ];

  const close = (open: boolean) => {
    if (!open) setEdit(null);
  };

  return (
    <section className="card circ-card" aria-labelledby={`circ-${circuit.id}`}>
      <header className="circ-head">
        <span className="circ-icon" aria-hidden>
          <Workflow size={17} strokeWidth={1.8} />
        </span>
        <div className="circ-titles">
          <h3 id={`circ-${circuit.id}`} className="card-title">
            {label}
          </h3>
          <p className="card-sub">
            {t("circuits2.resume", { count: steps.length, jours: formatNumber(circuit.max_days) })}
          </p>
        </div>
        <Badge tone={circuit.is_active ? "ok" : "neutral"}>{circuit.is_active ? t("circuits.active") : t("circuits.inactive")}</Badge>
        {gestion ? (
          <span className="circ-actions">
            <FormSheet
              title={t("ecarts_tr.circuits.ajouterEtape")}
              description={label}
              trigger={
                <button type="button" className="btn ghost sm">
                  <Plus size={15} aria-hidden />
                  {t("circuits2.etapeCourt")}
                </button>
              }
              fields={[
                { name: "name", label: t("circuits2.etape") },
                { name: "actor_role", label: t("circuits.actor"), type: "select", options: roleOpts },
                { name: "max_days", label: t("circuits2.delaiJours"), type: "number", min: 1, initial: "2" },
              ]}
              submitLabel={t("ecarts_tr.circuits.ajouterEtape")}
              onSubmit={(v) => action.mutate({ path: `${base}/ajouter-etape/`, body: { ...v, max_days: Number(v.max_days) }, success: t("circuits2.etapeAjoutee") })}
            />
            <Menu
              size="sm"
              label={t("circuits2.actionsCircuit", { nom: label })}
              items={[
                { label: t("ecarts_tr.circuits.renommer"), icon: Pencil, onSelect: () => setEdit({ kind: "renommer" }) },
                { label: circuit.is_active ? t("ecarts_tr.circuits.desactiver") : t("ecarts_tr.circuits.activer"), icon: Power, danger: circuit.is_active, onSelect: () => setEdit({ kind: "activation" }) },
              ]}
            />
          </span>
        ) : null}
      </header>

      <DataGrid
        columns={columns}
        rows={steps}
        caption={label}
        density="compact"
        maxHeight="none"
        rowActions={gestion ? rowActions : undefined}
        emptyLabel={t("circuits2.aucuneEtape")}
      />

      {edit?.kind === "delai" ? (
        <ConfirmDialog
          open
          onOpenChange={close}
          title={t("circuits2.modifierDelai")}
          description={edit.step.name}
          confirmLabel={t("circuits2.enregistrer")}
          field={{ label: t("circuits2.delaiJours"), type: "number", min: 1, initial: String(edit.step.max_days) }}
          onConfirm={(v) => action.mutate({ path: `${base}/modifier-etape/`, body: { etape: edit.step.id, max_days: Number(v) }, success: t("circuits2.modifie") })}
        />
      ) : null}
      {edit?.kind === "acteur" ? (
        <ConfirmDialog
          open
          onOpenChange={close}
          title={t("circuits2.changerActeur")}
          description={edit.step.name}
          confirmLabel={t("circuits2.enregistrer")}
          field={{ label: t("circuits.actor"), type: "select", options: roleOpts }}
          onConfirm={(v) => action.mutate({ path: `${base}/modifier-etape/`, body: { etape: edit.step.id, actor_role: v }, success: t("circuits2.modifie") })}
        />
      ) : null}
      {edit?.kind === "retirer" ? (
        <ConfirmDialog
          open
          onOpenChange={close}
          title={t("ecarts_tr.circuits.confirmRetirer")}
          description={edit.step.name}
          confirmLabel={t("ecarts_tr.circuits.retirer")}
          danger
          onConfirm={() => action.mutate({ path: `${base}/retirer-etape/`, body: { etape: edit.step.id }, success: t("circuits2.retiree") })}
        />
      ) : null}
      {edit?.kind === "renommer" ? (
        <ConfirmDialog
          open
          onOpenChange={close}
          title={t("ecarts_tr.circuits.renommer")}
          confirmLabel={t("circuits2.enregistrer")}
          field={{ label: t("ecarts_tr.circuits.libelle"), initial: label }}
          onConfirm={(v) => action.mutate({ path: `${base}/`, method: "PATCH", body: { label: v }, success: t("circuits2.modifie") })}
        />
      ) : null}
      {edit?.kind === "activation" ? (
        <ConfirmDialog
          open
          onOpenChange={close}
          title={circuit.is_active ? t("circuits2.desactiverTitre") : t("circuits2.activerTitre")}
          description={t("ecarts_tr.circuits.aide")}
          confirmLabel={circuit.is_active ? t("ecarts_tr.circuits.desactiver") : t("ecarts_tr.circuits.activer")}
          danger={circuit.is_active}
          onConfirm={() =>
            action.mutate({ path: `${base}/`, method: "PATCH", body: { is_active: !circuit.is_active }, success: t("circuits2.modifie") })
          }
        />
      ) : null}
    </section>
  );
}

export function CircuitsPage() {
  const { t } = useTranslation();
  const role = useAuth((s) => s.user?.role) ?? "";
  const gestion = GESTION_CIRCUITS.includes(role);
  const action = useServerAction([["circuits"]]);
  const roles = useQuery({
    queryKey: ["roles-applicatifs"],
    queryFn: () => api.get<{ results: { role: string; label: string }[] }>("/api/users/roles/").then((r) => r.results),
    enabled: gestion,
    retry: 0,
    staleTime: 300_000,
  }).data;
  const { data, isLoading, isError, refetch } = useQuery({
    queryKey: ["circuits", gestion],
    queryFn: () =>
      gestion
        ? api.get<Paginated<Circuit>>("/api/workflow/circuits/?tous=1&page_size=100").then((p) => p.results)
        : api.circuits(),
  });

  const roleOpts: Option[] = roles?.length
    ? roles.map((r) => ({ value: r.role, label: r.label }))
    : Object.entries(ROLES_SECOURS).map(([value, label]) => ({ value, label }));

  const header = (
    <PageHeader
      title={t("circuits.title")}
      subtitle={gestion ? t("ecarts_tr.circuits.aide") : t("circuits2.sub")}
      actions={
        gestion ? (
          <FormSheet
            title={t("ecarts_tr.circuits.nouveau")}
            trigger={
              <button type="button" className="btn primary">
                <Plus size={16} aria-hidden />
                {t("ecarts_tr.circuits.nouveau")}
              </button>
            }
            fields={[
              { name: "label", label: t("ecarts_tr.circuits.libelle") },
              { name: "max_days", label: t("circuits2.delaiTotal"), type: "number", min: 1, initial: "5" },
            ]}
            submitLabel={t("circuits2.creer")}
            onSubmit={(v) =>
              action.mutate({ path: "/api/workflow/circuits/", body: { code: slug(v.label), label: v.label, max_days: Number(v.max_days) }, success: t("circuits2.cree") })
            }
          />
        ) : undefined
      }
    />
  );

  if (isLoading)
    return (
      <>
        {header}
        <BoardSkeleton cols={1} rows={3} />
      </>
    );
  if (isError || !data)
    return (
      <>
        {header}
        <ErrorState message={t("common.error")} onRetry={() => void refetch()} retryLabel={t("common.retry")} />
      </>
    );

  return (
    <>
      {header}
      {data.length === 0 ? (
        <EmptyState icon={Workflow} label={t("circuits2.aucun")} />
      ) : (
        <div className="circ-list">
          {data.map((circuit) => (
            <CircuitCard key={circuit.id} circuit={circuit} gestion={gestion} roleOpts={roleOpts} />
          ))}
        </div>
      )}
    </>
  );
}
