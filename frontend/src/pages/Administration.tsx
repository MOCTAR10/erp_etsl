import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Check, Download, KeyRound, Minus, ShieldOff, Trash2, UserCheck, UserCog, UserX } from "lucide-react";
import { useState } from "react";
import type { ReactNode } from "react";
import { useTranslation } from "react-i18next";

import { api } from "../api/client";
import { SiteCompte, SitesSection } from "../components/sites/SitesSection";
import { Badge, Menu, Modal, PageHeader, PagedDataGrid, QuickForm, SectionCard, SheetClose, notify } from "../components/ui";
import type { BadgeTone, GridColumn, MenuEntry } from "../components/ui";
import { formatDateTime } from "../lib/format";
import { APP_NAV_KEY, sansCode, type ErpApp } from "../lib/modules";
import { describeError } from "../lib/offlineQueue";
import { initiales, roleLabel } from "../lib/roles";
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

const AUDIT_TONE: Record<string, BadgeTone> = { create: "ok", delete: "err", update: "info", acl_grant: "brand", acl_revoke: "warn" };

const court = (v: unknown) => {
  const s = typeof v === "string" ? v : JSON.stringify(v);
  return s && s.length > 60 ? `${s.slice(0, 60)}…` : (s ?? "—");
};

const nomCompte = (c: Compte) => [c.first_name, c.last_name].filter(Boolean).join(" ") || c.email;

/** Action de compte en cours (fenêtre de confirmation / saisie). */
type Dialogue = { type: "role" | "mdp" | "mfa"; compte: Compte } | null;

/** Mutation d'administration : retour par notification, rafraîchissement des listes. */
function useActionAdmin() {
  const { t } = useTranslation();
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ path, body, patch }: { path: string; body?: Record<string, unknown>; patch?: boolean; ok: string }) =>
      patch ? api.patch<unknown>(path, body ?? {}) : api.post<unknown>(path, body),
    onSuccess: (_r, v) => {
      notify.success(v.ok);
      void qc.invalidateQueries();
    },
    onError: (e) => notify.error(t("shell.admin.erreur"), { description: describeError(e) }),
  });
}

async function telecharger(path: string, fichier: string, ok: string, ko: string) {
  try {
    await api.download(path, fichier);
    notify.success(ok);
  } catch (e) {
    notify.error(ko, { description: describeError(e) });
  }
}

function Referentiel({ path, cle }: { path: string; cle: string }) {
  const { t } = useTranslation();
  const list = usePagedList<RefRow>(`ref-${cle}`, (q) => api.get<Paginated<RefRow>>(`${path}${q}`), { pageSize: 20 });
  const columns: GridColumn<RefRow>[] = [
    { key: "code", header: t("ecarts_tr.admin.code"), width: 160, sortValue: (r) => r.code, render: (r) => <span className="num">{r.code}</span> },
    { key: "label", header: t("ecarts_tr.admin.libelle"), sortValue: (r) => r.name ?? r.label, render: (r) => r.name ?? r.label ?? "—" },
    { key: "info", header: "", render: (r) => <span className="muted">{r.kind_label ?? r.article_type_label ?? r.unit_code ?? ""}</span> },
    {
      key: "actif",
      header: t("ecarts_tr.admin.etat"),
      width: 110,
      render: (r) => (r.is_active === false ? <Badge tone="neutral">{t("ecarts_tr.admin.inactif")}</Badge> : <Badge tone="ok">{t("ecarts_tr.admin.actif")}</Badge>),
    },
  ];
  return <PagedDataGrid list={list} columns={columns} caption={t(`ecarts_tr.admin.ref.${cle}`)} searchPlaceholder={t("common.searchPlaceholder")} density="compact" />;
}

/** Administration (EX-G-01) : comptes et rôles, matrice rôle → modules, référentiels centraux, piste d'audit. */
export function AdministrationPage() {
  const { t } = useTranslation();
  const [role, setRole] = useState("");
  const [onglet, setOnglet] = useState<(typeof REFERENTIELS)[number]["key"]>("partners");
  const [module, setModule] = useState("");
  const [dialogue, setDialogue] = useState<Dialogue>(null);
  const [nouveauRole, setNouveauRole] = useState("");
  const [motDePasse, setMotDePasse] = useState("");
  const [purge, setPurge] = useState(false);
  const action = useActionAdmin();

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
  const libelleRole = (code: string) => roleLabel(t, code);
  const roleOpts = roles.map((r) => ({ value: r.role, label: libelleRole(r.role) }));

  const ouvrir = (type: "role" | "mdp" | "mfa", compte: Compte) => {
    setNouveauRole(compte.role);
    setMotDePasse("");
    setDialogue({ type, compte });
  };
  const fermer = () => setDialogue(null);
  const valider = () => {
    if (!dialogue) return;
    const { compte } = dialogue;
    const base = `/api/users/users/${compte.id}/`;
    const fin = { onSuccess: fermer };
    if (dialogue.type === "role") action.mutate({ path: base, patch: true, body: { role: nouveauRole }, ok: t("shell.admin.roleOk") }, fin);
    if (dialogue.type === "mdp")
      action.mutate({ path: `${base}reinitialiser-mot-de-passe/`, body: { mot_de_passe: motDePasse }, ok: t("shell.admin.reinitMdpOk") }, fin);
    if (dialogue.type === "mfa") action.mutate({ path: `${base}reinitialiser-mfa/`, ok: t("shell.admin.reinitMfaOk") }, fin);
  };

  const actionsCompte = (c: Compte): MenuEntry[] => [
    { label: t("shell.admin.changerRole"), icon: UserCog, onSelect: () => ouvrir("role", c) },
    { label: t("shell.admin.reinitMdp"), icon: KeyRound, onSelect: () => ouvrir("mdp", c) },
    c.mfa_active && { label: t("ecarts_tr.admin.reinitMfa"), icon: ShieldOff, onSelect: () => ouvrir("mfa", c) },
    "separator",
    c.is_active
      ? {
          label: t("ecarts_tr.admin.desactiver"),
          icon: UserX,
          danger: true,
          onSelect: () => action.mutate({ path: `/api/users/users/${c.id}/`, patch: true, body: { is_active: false }, ok: t("shell.admin.desactiverOk") }),
        }
      : {
          label: t("ecarts_tr.admin.reactiver"),
          icon: UserCheck,
          onSelect: () => action.mutate({ path: `/api/users/users/${c.id}/`, patch: true, body: { is_active: true }, ok: t("shell.admin.reactiverOk") }),
        },
  ];

  const colComptes: GridColumn<Compte>[] = [
    {
      key: "compte",
      header: t("ecarts_tr.admin.compte"),
      sortValue: (c) => nomCompte(c),
      render: (c) => (
        <span className="compte-cell">
          <span className="compte-avatar" aria-hidden="true">
            {initiales(nomCompte(c))}
          </span>
          <span className="compte-text">
            <span className="compte-nom">{nomCompte(c)}</span>
            <span className="compte-mail">{c.email}</span>
          </span>
        </span>
      ),
    },
    { key: "role", header: t("ecarts_tr.admin.role"), sortValue: (c) => libelleRole(c.role), render: (c) => libelleRole(c.role) },
    { key: "site", header: t("ecarts_a5.siteCompte"), render: (c) => <SiteCompte id={c.id} email={c.email} site={c.site_etsl} /> },
    {
      key: "etat",
      header: t("ecarts_tr.admin.etat"),
      sortValue: (c) => c.is_active,
      render: (c) => (
        <span className="badge-row">
          <Badge tone={c.is_active ? "ok" : "neutral"}>{c.is_active ? t("ecarts_tr.admin.actif") : t("ecarts_tr.admin.inactif")}</Badge>
          {c.mfa_active ? <Badge tone="brand">MFA</Badge> : null}
        </span>
      ),
    },
    { key: "modules", header: t("ecarts_tr.admin.modules"), num: true, width: 100, sortValue: (c) => c.modules.length, render: (c) => c.modules.length },
    {
      key: "connexion",
      header: t("ecarts_tr.admin.derniereConnexion"),
      sortValue: (c) => c.last_login,
      render: (c) => <span className="num">{c.last_login ? formatDateTime(c.last_login) : <span className="muted">{t("shell.admin.jamais")}</span>}</span>,
    },
  ];
  const colAudit: GridColumn<Audit>[] = [
    { key: "quand", header: t("ecarts_tr.audit.quand"), width: 170, render: (a) => <span className="num">{formatDateTime(a.created_at)}</span> },
    { key: "qui", header: t("ecarts_tr.audit.qui"), render: (a) => a.user_email ?? "—" },
    {
      key: "action",
      header: t("ecarts_tr.audit.action"),
      render: (a) => <Badge tone={AUDIT_TONE[a.action] ?? "neutral"}>{t(`shell.admin.actionsAudit.${a.action}`, { defaultValue: a.action })}</Badge>,
    },
    {
      key: "objet",
      header: t("ecarts_tr.audit.objet"),
      render: (a) => (
        <span className="audit-objet">
          {a.object_type} <span className="muted num">{a.object_id.slice(0, 8)}</span>
        </span>
      ),
    },
    {
      key: "detail",
      header: t("ecarts_tr.audit.avantApres"),
      render: (a) =>
        a.detail.champs ? (
          <ul className="audit-diff">
            {a.detail.champs.slice(0, 4).map((k) => (
              <li key={k}>
                <span className="audit-champ">{k}</span> <span className="muted">{court(a.detail.avant?.[k])}</span> → {court(a.detail.apres?.[k])}
              </li>
            ))}
          </ul>
        ) : (
          <span className="muted audit-brut">{court(a.detail.apres ?? a.detail.avant ?? a.detail)}</span>
        ),
    },
  ];

  const qsRole = role ? `&role=${role}` : "";
  const qsModule = module ? `&module=${module}` : "";
  const exportBtn = (label: string, items: MenuEntry[]) => (
    <Menu
      align="end"
      items={items}
      trigger={
        <button type="button" className="btn ghost">
          <Download size={15} aria-hidden="true" />
          {label}
        </button>
      }
    />
  );

  let dialogueContenu: { titre: string; texte: ReactNode; corps?: ReactNode; danger?: boolean; pret: boolean } | null = null;
  if (dialogue) {
    const nom = nomCompte(dialogue.compte);
    if (dialogue.type === "role")
      dialogueContenu = {
        titre: t("shell.admin.changerRoleTitre", { nom }),
        texte: t("shell.admin.changerRoleAide"),
        pret: Boolean(nouveauRole) && nouveauRole !== dialogue.compte.role,
        corps: (
          <div className="field">
            <label htmlFor="admin-nouveau-role">{t("ecarts_tr.admin.role")}</label>
            <select id="admin-nouveau-role" value={nouveauRole} onChange={(e) => setNouveauRole(e.target.value)}>
              {roleOpts.map((o) => (
                <option key={o.value} value={o.value}>
                  {o.label}
                </option>
              ))}
            </select>
          </div>
        ),
      };
    if (dialogue.type === "mdp")
      dialogueContenu = {
        titre: t("shell.admin.reinitMdpTitre", { nom }),
        texte: t("shell.admin.reinitMdpAide"),
        pret: motDePasse.length >= 8,
        corps: (
          <div className="field">
            <label htmlFor="admin-mdp">{t("ecarts_tr.mdp.reinitAdminPrompt")}</label>
            <input id="admin-mdp" type="password" autoComplete="new-password" value={motDePasse} onChange={(e) => setMotDePasse(e.target.value)} />
          </div>
        ),
      };
    if (dialogue.type === "mfa")
      dialogueContenu = { titre: t("shell.admin.reinitMfaTitre", { nom }), texte: t("ecarts_tr.admin.confirmReinitMfa"), danger: true, pret: true };
  }

  return (
    <div className="shell-page">
      <PageHeader title={t("ecarts_tr.admin.title")} subtitle={t("ecarts_tr.admin.subtitle")} />

      <SectionCard
        title={t("ecarts_tr.admin.comptes")}
        actions={
          <div className="action-bar-buttons">
            {exportBtn(t("shell.admin.exporter"), [
              {
                label: t("shell.admin.exportExcel"),
                icon: Download,
                onSelect: () => void telecharger(`/api/users/users/?export=xlsx${qsRole}`, "utilisateurs.xlsx", t("shell.admin.exportOk"), t("shell.admin.erreur")),
              },
            ])}
            <QuickForm
              title={t("ecarts_tr.admin.nouveauCompte")}
              endpoint="/api/users/users/"
              fields={[
                { name: "email", label: "E-mail", required: true },
                { name: "first_name", label: t("ecarts_tr.admin.prenom") },
                { name: "last_name", label: t("ecarts_tr.admin.nom") },
                { name: "role", label: t("ecarts_tr.admin.role"), type: "select", options: roleOpts, required: true },
                { name: "password", label: t("ecarts_tr.admin.motDePasse"), required: true },
              ]}
            />
          </div>
        }
      >
        <div className="list-tools">
        <div className="shell-toolbar inline">
          <label className="sr-only" htmlFor="admin-role">
            {t("shell.admin.filtreRole")}
          </label>
          <select id="admin-role" className="control" value={role} onChange={(e) => setRole(e.target.value)}>
            <option value="">{t("shell.admin.tousRoles")}</option>
            {roleOpts.map((o) => (
              <option key={o.value} value={o.value}>
                {o.label}
              </option>
            ))}
          </select>
        </div>
        <PagedDataGrid list={comptes} columns={colComptes} caption={t("ecarts_tr.admin.comptes")} searchPlaceholder={t("common.searchPlaceholder")} rowActions={actionsCompte} maxHeight="none" />
        </div>
      </SectionCard>

      <SectionCard title={t("ecarts_tr.admin.matrice")} subtitle={t("ecarts_tr.admin.matriceAide")}>
        <div className="table-wrap matrice-wrap" tabIndex={0} role="region" aria-label={t("ecarts_tr.admin.matrice")}>
          <table className="table matrice" data-testid="matrice-roles">
            <caption className="sr-only">{t("ecarts_tr.admin.matrice")}</caption>
            <thead>
              <tr>
                <th scope="col">{t("ecarts_tr.admin.role")}</th>
                {(matrice?.modules ?? []).map((m) => (
                  <th key={m} scope="col" className="matrice-mod">
                    {sansCode(t(APP_NAV_KEY[m] ?? m))}
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
                  <th scope="row">{libelleRole(r.role)}</th>
                  {(matrice?.modules ?? []).map((m) => (
                    <td key={m} className="matrice-cell" aria-label={r.modules.includes(m) ? t("ecarts_tr.admin.lecture") : t("ecarts_tr.admin.aucun")}>
                      {r.modules.includes(m) ? (
                        <span className="matrice-oui">
                          <Check size={13} strokeWidth={2.5} aria-hidden="true" />
                        </span>
                      ) : (
                        <Minus size={13} className="matrice-non" aria-hidden="true" />
                      )}
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
                { name: "email", label: "E-mail" },
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
        <div className="shell-toolbar inline">
          <div className="seg" role="tablist" aria-label={t("ecarts_tr.admin.referentiels")}>
            {REFERENTIELS.map((r) => (
              <button key={r.key} type="button" role="tab" aria-selected={onglet === r.key} onClick={() => setOnglet(r.key)}>
                {t(`ecarts_tr.admin.ref.${r.key}`)}
              </button>
            ))}
          </div>
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
            {exportBtn(t("shell.admin.exporter"), [
              {
                label: t("shell.admin.exportCsv"),
                icon: Download,
                onSelect: () => void telecharger(`/api/documents/audit/?export=csv${qsModule}`, "piste_audit.csv", t("shell.admin.exportOk"), t("shell.admin.erreur")),
              },
              {
                label: t("shell.admin.exportExcel"),
                icon: Download,
                onSelect: () => void telecharger(`/api/documents/audit/?export=xlsx${qsModule}`, "piste_audit.xlsx", t("shell.admin.exportOk"), t("shell.admin.erreur")),
              },
            ])}
            <Menu items={[{ label: t("ecarts_tr.audit.purger"), icon: Trash2, danger: true, onSelect: () => setPurge(true) }]} />
          </div>
        }
      >
        {retention?.provisoire ? (
          <div className="banner warn" role="note">
            <div className="banner-body">
              <div className="banner-text">{t("ecarts_tr.audit.retentionProvisoire")}</div>
            </div>
          </div>
        ) : null}
        <div className="list-tools">
        <div className="shell-toolbar inline">
          <label className="sr-only" htmlFor="audit-module">
            {t("shell.admin.filtreModule")}
          </label>
          <input
            id="audit-module"
            className="control"
            value={module}
            placeholder={t("shell.admin.filtreModuleAide")}
            onChange={(e) => setModule(e.target.value.trim())}
          />
        </div>
        <PagedDataGrid list={audit} columns={colAudit} caption={t("ecarts_tr.audit.title")} density="compact" maxHeight="none" />
        </div>
      </SectionCard>

      <Modal
        open={dialogue !== null}
        onOpenChange={(o) => {
          if (!o) fermer();
        }}
        title={dialogueContenu?.titre ?? ""}
        description={dialogueContenu?.texte}
        width={480}
        footer={
          <>
            <SheetClose>
              <button type="button" className="btn ghost">
                {t("shell.admin.annuler")}
              </button>
            </SheetClose>
            <button
              type="button"
              className={dialogueContenu?.danger ? "btn danger" : "btn primary"}
              disabled={!dialogueContenu?.pret || action.isPending}
              onClick={valider}
            >
              {t("shell.admin.valider")}
            </button>
          </>
        }
      >
        {dialogueContenu?.corps}
      </Modal>

      <Modal
        open={purge}
        onOpenChange={setPurge}
        title={t("shell.admin.purgerTitre")}
        description={t("ecarts_tr.audit.confirmPurger")}
        width={480}
        footer={
          <>
            <SheetClose>
              <button type="button" className="btn ghost">
                {t("shell.admin.annuler")}
              </button>
            </SheetClose>
            <button
              type="button"
              className="btn danger"
              disabled={action.isPending}
              onClick={() => action.mutate({ path: "/api/documents/audit/purger/", ok: t("shell.admin.purgeOk") }, { onSuccess: () => setPurge(false) })}
            >
              {t("ecarts_tr.audit.purger")}
            </button>
          </>
        }
      />
    </div>
  );
}
