import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Check, Download, Minus } from "lucide-react";
import { useState } from "react";
import { useTranslation } from "react-i18next";

import { api } from "../api/client";
import { SiteCompte, SitesSection } from "../components/sites/SitesSection";
import { ActionBar, Badge, PageHeader, PagedDataTable, QuickForm, SectionCard } from "../components/ui";
import type { Column } from "../components/ui";
import { formatDateTime } from "../lib/format";
import { APP_NAV_KEY, type ErpApp } from "../lib/modules";
import { describeError } from "../lib/offlineQueue";
import { usePagedList } from "../lib/usePagedList";
import type { Paginated } from "../types";

interface Compte {
  id: string;
  email: string;
  first_name: string;
  last_name: string;
  role: string;
  role_label: string;
  is_active: boolean;
  mfa_active: boolean;
  modules: string[];
  last_login: string | null;
  site_etsl: number | null;
}
interface Matrice {
  modules: ErpApp[];
  roles: { role: string; label: string; modules: string[]; comptes_actifs: number }[];
}
interface Audit {
  id: string;
  user_email: string | null;
  action: string;
  object_type: string;
  object_id: string;
  detail: { champs?: string[]; avant?: Record<string, unknown>; apres?: Record<string, unknown>; [k: string]: unknown };
  ip_address: string | null;
  created_at: string;
}
interface Retention {
  retention_ans: number;
  provisoire: boolean;
  total: number;
  purgeables: number;
  journal_acces_purgeables: number;
}
interface RefRow {
  id: string | number;
  code: string;
  label?: string;
  name?: string;
  kind_label?: string;
  article_type_label?: string;
  unit_code?: string | null;
  is_active?: boolean;
}

const REFERENTIELS = [
  { key: "partners", path: "/api/referentiels/partners/" },
  { key: "articles", path: "/api/referentiels/articles/" },
  { key: "units", path: "/api/referentiels/units/" },
  { key: "currencies", path: "/api/referentiels/currencies/" },
  { key: "accounts", path: "/api/referentiels/accounts/" },
] as const;

const court = (v: unknown) => {
  const s = typeof v === "string" ? v : JSON.stringify(v);
  return s && s.length > 60 ? `${s.slice(0, 60)}…` : (s ?? "—");
};

/** Rôle modifiable sur place (PATCH du compte) ; refus serveur affiché. */
function RoleCompte({ c, roles }: { c: Compte; roles: Matrice["roles"] }) {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const [erreur, setErreur] = useState<string | null>(null);
  const patch = useMutation({
    mutationFn: (body: Record<string, unknown>) => api.patch<Compte>(`/api/users/users/${c.id}/`, body),
    onSuccess: () => {
      setErreur(null);
      void qc.invalidateQueries();
    },
    onError: (e) => setErreur(describeError(e)),
  });
  return (
    <>
      <label className="sr-only" htmlFor={`role-${c.id}`}>
        {c.email}
      </label>
      <select id={`role-${c.id}`} value={c.role} disabled={patch.isPending} onChange={(e) => patch.mutate({ role: e.target.value })}>
        {roles.map((r) => (
          <option key={r.role} value={r.role}>
            {r.label}
          </option>
        ))}
      </select>
      <button type="button" className="btn ghost" disabled={patch.isPending} onClick={() => patch.mutate({ is_active: !c.is_active })}>
        {c.is_active ? t("ecarts_tr.admin.desactiver") : t("ecarts_tr.admin.reactiver")}
      </button>
      {erreur && (
        <p className="action-error" role="alert">
          {erreur}
        </p>
      )}
    </>
  );
}

function Referentiel({ path, cle }: { path: string; cle: string }) {
  const { t } = useTranslation();
  const list = usePagedList<RefRow>(`ref-${cle}`, (q) => api.get<Paginated<RefRow>>(`${path}${q}`), { pageSize: 20 });
  const columns: Column<RefRow>[] = [
    { key: "code", header: t("ecarts_tr.admin.code"), render: (r) => r.code },
    { key: "label", header: t("ecarts_tr.admin.libelle"), render: (r) => r.name ?? r.label ?? "—" },
    { key: "info", header: "", render: (r) => r.kind_label ?? r.article_type_label ?? r.unit_code ?? "" },
    {
      key: "actif",
      header: t("ecarts_tr.admin.actif"),
      render: (r) => (r.is_active === false ? <Badge tone="neutral">{t("ecarts_tr.admin.inactif")}</Badge> : <Badge tone="ok">{t("ecarts_tr.admin.actif")}</Badge>),
    },
  ];
  return <PagedDataTable list={list} columns={columns} caption={t(`ecarts_tr.admin.ref.${cle}`)} searchPlaceholder={t("common.searchPlaceholder")} />;
}

/** Administration (EX-G-01) : comptes et rôles, matrice rôle → modules, référentiels centraux, piste d'audit. */
export function AdministrationPage() {
  const { t } = useTranslation();
  const [role, setRole] = useState("");
  const [onglet, setOnglet] = useState<(typeof REFERENTIELS)[number]["key"]>("partners");
  const [module, setModule] = useState("");
  const matrice = useQuery({ queryKey: ["matrice-roles"], queryFn: () => api.get<Matrice>("/api/users/users/matrice/"), retry: 0 }).data;
  const roles = matrice?.roles ?? [];
  const comptes = usePagedList<Compte>("admin-comptes", (q) => api.get<Paginated<Compte>>(`/api/users/users/${q}`), {
    pageSize: 20,
    extra: role ? `role=${role}` : "",
  });
  const audit = usePagedList<Audit>("admin-audit", (q) => api.get<Paginated<Audit>>(`/api/documents/audit/${q}`), {
    pageSize: 20,
    extra: module ? `module=${module}` : "",
  });
  const retention = useQuery({ queryKey: ["audit-retention"], queryFn: () => api.get<Retention>("/api/documents/audit/retention/"), retry: 0 }).data;
  const roleOpts = roles.map((r) => ({ value: r.role, label: r.label }));

  const colComptes: Column<Compte>[] = [
    {
      key: "compte",
      header: t("ecarts_tr.admin.compte"),
      render: (c) => (
        <>
          <strong>{[c.first_name, c.last_name].filter(Boolean).join(" ") || c.email}</strong>
          <div className="muted" style={{ fontSize: 12 }}>
            {c.email}
          </div>
        </>
      ),
    },
    { key: "role", header: t("ecarts_tr.admin.role"), render: (c) => <RoleCompte c={c} roles={roles} /> },
    { key: "site", header: t("ecarts_a5.siteCompte"), render: (c) => <SiteCompte id={c.id} email={c.email} site={c.site_etsl} /> },
    {
      key: "etat",
      header: t("ecarts_tr.admin.etat"),
      render: (c) => (
        <>
          <Badge tone={c.is_active ? "ok" : "neutral"}>{c.is_active ? t("ecarts_tr.admin.actif") : t("ecarts_tr.admin.inactif")}</Badge>{" "}
          {c.mfa_active ? <Badge tone="brand">MFA</Badge> : null}
        </>
      ),
    },
    { key: "modules", header: t("ecarts_tr.admin.modules"), num: true, render: (c) => c.modules.length },
    { key: "connexion", header: t("ecarts_tr.admin.derniereConnexion"), render: (c) => (c.last_login ? formatDateTime(c.last_login) : "—") },
    {
      key: "mfa",
      header: "",
      render: (c) => (
        <ActionBar
          actions={[
            {
              label: t("ecarts_tr.mdp.reinitAdmin"),
              path: `/api/users/users/${c.id}/reinitialiser-mot-de-passe/`,
              tone: "ghost" as const,
              prompt: { name: "mot_de_passe", label: t("ecarts_tr.mdp.reinitAdminPrompt") },
            },
            ...(c.mfa_active
              ? [{ label: t("ecarts_tr.admin.reinitMfa"), path: `/api/users/users/${c.id}/reinitialiser-mfa/`, tone: "ghost" as const, confirm: t("ecarts_tr.admin.confirmReinitMfa") }]
              : []),
          ]}
        />
      ),
    },
  ];
  const colAudit: Column<Audit>[] = [
    { key: "quand", header: t("ecarts_tr.audit.quand"), render: (a) => formatDateTime(a.created_at) },
    { key: "qui", header: t("ecarts_tr.audit.qui"), render: (a) => a.user_email ?? "—" },
    { key: "action", header: t("ecarts_tr.audit.action"), render: (a) => <Badge tone={a.action === "delete" ? "err" : a.action === "create" ? "ok" : "brand"}>{a.action}</Badge> },
    { key: "objet", header: t("ecarts_tr.audit.objet"), render: (a) => `${a.object_type} · ${a.object_id.slice(0, 8)}` },
    {
      key: "detail",
      header: t("ecarts_tr.audit.avantApres"),
      render: (a) =>
        a.detail.champs ? (
          <ul style={{ margin: 0, paddingLeft: "1rem", fontSize: 12 }}>
            {a.detail.champs.slice(0, 4).map((k) => (
              <li key={k}>
                <strong>{k}</strong> : {court(a.detail.avant?.[k])} → {court(a.detail.apres?.[k])}
              </li>
            ))}
          </ul>
        ) : (
          <span className="muted" style={{ fontSize: 12 }}>
            {court(a.detail.apres ?? a.detail.avant ?? a.detail)}
          </span>
        ),
    },
  ];

  return (
    <>
      <PageHeader title={t("ecarts_tr.admin.title")} subtitle={t("ecarts_tr.admin.subtitle")} />

      <SectionCard
        title={t("ecarts_tr.admin.comptes")}
        actions={
          <div className="action-bar-buttons">
            <QuickForm
              title={t("ecarts_tr.admin.nouveauCompte")}
              endpoint="/api/users/users/"
              fields={[
                { name: "email", label: "Email", required: true },
                { name: "first_name", label: t("ecarts_tr.admin.prenom") },
                { name: "last_name", label: t("ecarts_tr.admin.nom") },
                { name: "role", label: t("ecarts_tr.admin.role"), type: "select", options: roleOpts, required: true },
                { name: "password", label: t("ecarts_tr.admin.motDePasse"), required: true },
              ]}
            />
            <button type="button" className="btn ghost" onClick={() => void api.download(`/api/users/users/?export=xlsx${role ? `&role=${role}` : ""}`, "utilisateurs.xlsx")}>
              <Download size={14} aria-hidden="true" /> Excel
            </button>
          </div>
        }
      >
        <div className="field" style={{ maxWidth: 320 }}>
          <label htmlFor="admin-role">{t("ecarts_tr.admin.role")}</label>
          <select id="admin-role" value={role} onChange={(e) => setRole(e.target.value)}>
            <option value="">{t("ecarts_tr.parametres.tous")}</option>
            {roleOpts.map((o) => (
              <option key={o.value} value={o.value}>
                {o.label}
              </option>
            ))}
          </select>
        </div>
        <PagedDataTable list={comptes} columns={colComptes} caption={t("ecarts_tr.admin.comptes")} searchPlaceholder={t("common.searchPlaceholder")} />
      </SectionCard>

      <SectionCard title={t("ecarts_tr.admin.matrice")} subtitle={t("ecarts_tr.admin.matriceAide")}>
        <div className="table-wrap">
          <table className="table" data-testid="matrice-roles">
            <thead>
              <tr>
                <th scope="col">{t("ecarts_tr.admin.role")}</th>
                {(matrice?.modules ?? []).map((m) => (
                  <th key={m} scope="col">
                    {t(APP_NAV_KEY[m] ?? m)}
                  </th>
                ))}
                <th scope="col" className="num">
                  {t("ecarts_tr.admin.comptesActifs")}
                </th>
              </tr>
            </thead>
            <tbody>
              {roles.map((r) => (
                <tr key={r.role}>
                  <td>{r.label}</td>
                  {(matrice?.modules ?? []).map((m) => (
                    <td key={m} aria-label={r.modules.includes(m) ? t("ecarts_tr.admin.lecture") : t("ecarts_tr.admin.aucun")}>
                      {r.modules.includes(m) ? <Check size={14} aria-hidden="true" /> : <Minus size={14} className="muted" aria-hidden="true" />}
                    </td>
                  ))}
                  <td className="num">{r.comptes_actifs}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </SectionCard>

      <SitesSection />

      <SectionCard
        title={t("ecarts_tr.admin.referentiels")}
        subtitle={t("ecarts_tr.admin.referentielsAide")}
        actions={
          onglet === "partners" ? (
            <QuickForm
              title={t("ecarts_tr.admin.nouveauTiers")}
              endpoint="/api/referentiels/partners/"
              fields={[
                { name: "code", label: t("ecarts_tr.admin.code"), required: true },
                { name: "name", label: t("ecarts_tr.admin.libelle"), required: true },
                {
                  name: "kind",
                  label: t("ecarts_tr.admin.typeTiers"),
                  type: "select",
                  required: true,
                  options: ["client", "fournisseur", "both", "autre"].map((k) => ({ value: k, label: t(`ecarts_tr.admin.kinds.${k}`) })),
                },
                { name: "tax_id", label: "NIF" },
                { name: "email", label: "Email" },
                { name: "phone", label: t("ecarts_tr.admin.telephone") },
              ]}
            />
          ) : onglet === "units" ? (
            <QuickForm
              title={t("ecarts_tr.admin.nouvelleUnite")}
              endpoint="/api/referentiels/units/"
              fields={[
                { name: "code", label: t("ecarts_tr.admin.code"), required: true },
                { name: "label", label: t("ecarts_tr.admin.libelle"), required: true },
              ]}
            />
          ) : null
        }
      >
        <div className="action-bar-buttons" role="tablist" aria-label={t("ecarts_tr.admin.referentiels")}>
          {REFERENTIELS.map((r) => (
            <button
              key={r.key}
              type="button"
              role="tab"
              aria-selected={onglet === r.key}
              className={`btn ${onglet === r.key ? "primary" : "ghost"}`}
              onClick={() => setOnglet(r.key)}
            >
              {t(`ecarts_tr.admin.ref.${r.key}`)}
            </button>
          ))}
        </div>
        {REFERENTIELS.filter((r) => r.key === onglet).map((r) => (
          <Referentiel key={r.key} path={r.path} cle={r.key} />
        ))}
      </SectionCard>

      <SectionCard
        title={t("ecarts_tr.audit.title")}
        subtitle={
          retention
            ? t("ecarts_tr.audit.retention", { ans: retention.retention_ans, total: retention.total, purgeables: retention.purgeables + retention.journal_acces_purgeables })
            : undefined
        }
        actions={
          <div className="action-bar-buttons">
            <button type="button" className="btn ghost" onClick={() => void api.download(`/api/documents/audit/?export=csv${module ? `&module=${module}` : ""}`, "piste_audit.csv")}>
              <Download size={14} aria-hidden="true" /> CSV
            </button>
            <button type="button" className="btn ghost" onClick={() => void api.download(`/api/documents/audit/?export=xlsx${module ? `&module=${module}` : ""}`, "piste_audit.xlsx")}>
              <Download size={14} aria-hidden="true" /> Excel
            </button>
            <ActionBar actions={[{ label: t("ecarts_tr.audit.purger"), path: "/api/documents/audit/purger/", tone: "danger", confirm: t("ecarts_tr.audit.confirmPurger") }]} />
          </div>
        }
      >
        {retention?.provisoire ? (
          <p className="action-error" role="note">
            {t("ecarts_tr.audit.retentionProvisoire")}
          </p>
        ) : null}
        <div className="field" style={{ maxWidth: 320 }}>
          <label htmlFor="audit-module">{t("ecarts_tr.parametres.module")}</label>
          <input id="audit-module" value={module} placeholder="stocks, achats, users…" onChange={(e) => setModule(e.target.value.trim())} />
        </div>
        <PagedDataTable list={audit} columns={colAudit} caption={t("ecarts_tr.audit.title")} />
      </SectionCard>
    </>
  );
}
