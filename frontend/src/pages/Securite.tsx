import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowRight, Download, KeyRound, ShieldCheck, ShieldOff, UserX } from "lucide-react";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";

import { api } from "../api/client";
import { Badge, DataGrid, Modal, PageHeader, PagedDataGrid, QuickForm, SectionCard, SheetClose, notify } from "../components/ui";
import type { GridColumn } from "../components/ui";
import { formatDate, formatDateTime } from "../lib/format";
import { describeError } from "../lib/offlineQueue";
import { usePagedList } from "../lib/usePagedList";
import { useAuth } from "../store/auth";
import type { Delegation, JournalAcces, Me, Paginated } from "../types";

const EVENEMENTS = [
  "connexion",
  "echec_connexion",
  "connexion_bloquee",
  "mfa_enrolement",
  "mfa_succes",
  "mfa_echec",
  "mfa_reinitialisation",
  "export",
];

/** Sécurité (lot 15b) : MFA du compte, délégations temporaires (EX-G-02), journal des accès pour l'admin (EX-G-10). */
export function SecuritePage() {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const user = useAuth((s) => s.user) as (Me & { mfa_active?: boolean; mfa_requise?: boolean }) | null;
  const admin = user?.role === "admin";
  const [evenement, setEvenement] = useState("");
  const [aAnnuler, setAAnnuler] = useState<Delegation | null>(null);

  const delegations = useQuery({
    queryKey: ["delegations"],
    queryFn: () => api.listAll<Delegation>("/api/workflow/delegations/"),
  });
  // Journal d'accès : paginé (volume élevé), filtre d'événement transmis au serveur.
  const journal = usePagedList<JournalAcces>(
    "journal-acces",
    (q) => api.get<Paginated<JournalAcces>>(`/api/users/journal-acces/${q}`),
    { pageSize: 50, extra: evenement ? `evenement=${evenement}` : "", enabled: admin },
  );

  const annuler = useMutation({
    mutationFn: (d: Delegation) => api.post<unknown>(`/api/workflow/delegations/${d.id}/annuler/`),
    onSuccess: () => {
      setAAnnuler(null);
      notify.success(t("shell.secu.annulerOk"));
      void qc.invalidateQueries({ queryKey: ["delegations"] });
    },
    onError: (e) => notify.error(t("shell.admin.erreur"), { description: describeError(e) }),
  });

  const exporter = async () => {
    try {
      await api.download(`/api/users/journal-acces/?export=csv${evenement ? `&evenement=${evenement}` : ""}`, "journal_acces.csv");
      notify.success(t("shell.secu.exportOk"));
    } catch (e) {
      notify.error(t("shell.secu.exportKo"), { description: describeError(e) });
    }
  };

  const delegationColumns: GridColumn<Delegation>[] = [
    { key: "code", header: "Code", width: 130, sortValue: (d) => d.code, render: (d) => <span className="num">{d.code}</span> },
    {
      key: "qui",
      header: t("securite.delegataire"),
      sortValue: (d) => d.delegataire_email,
      render: (d) => (
        <span className="deleg-qui">
          <span className="muted">{d.delegant_email}</span>
          <ArrowRight size={13} aria-hidden="true" className="muted" />
          <span>{d.delegataire_email}</span>
        </span>
      ),
    },
    {
      key: "periode",
      header: t("shell.secu.periode"),
      sortValue: (d) => d.date_debut,
      render: (d) => (
        <span className="num">
          {formatDate(d.date_debut)} – {formatDate(d.date_fin)}
        </span>
      ),
    },
    { key: "motif", header: t("securite.motif"), render: (d) => d.motif },
    {
      key: "etat",
      header: t("shell.secu.etat"),
      width: 120,
      sortValue: (d) => d.active,
      render: (d) => <Badge tone={d.active ? "ok" : "neutral"}>{d.active ? t("securite.active") : t("securite.inactive")}</Badge>,
    },
  ];
  const journalColumns: GridColumn<JournalAcces>[] = [
    { key: "quand", header: t("securite.col.quand"), width: 180, render: (j) => <span className="num">{formatDateTime(j.cree_le)}</span> },
    {
      key: "evenement",
      header: t("securite.col.evenement"),
      render: (j) => (
        <Badge tone={/echec|bloquee/.test(j.evenement) ? "err" : j.evenement === "export" ? "info" : "neutral"}>
          {t(`shell.secu.evenements.${j.evenement}`, { defaultValue: j.evenement_label })}
        </Badge>
      ),
    },
    { key: "compte", header: t("securite.col.compte"), render: (j) => j.email || "—" },
    { key: "ip", header: t("securite.col.ip"), width: 140, render: (j) => <span className="num">{j.ip ?? "—"}</span> },
    { key: "ressource", header: t("securite.col.ressource"), render: (j) => <code className="shell-path">{j.chemin}</code> },
  ];

  const mfaActive = Boolean(user?.mfa_active);
  return (
    <>
      <PageHeader title={t("securite.title")} subtitle={t("shell.secu.sousTitre")} />

      <SectionCard title={t("securite.mfa")}>
        <div className="mfa-row">
          <span className={mfaActive ? "mfa-icon ok" : "mfa-icon"} aria-hidden="true">
            {mfaActive ? <ShieldCheck size={18} /> : <ShieldOff size={18} />}
          </span>
          <div className="mfa-text">
            <div className="mfa-status">
              <Badge tone={mfaActive ? "ok" : user?.mfa_requise ? "warn" : "neutral"}>
                {mfaActive ? t("securite.mfaActive") : t("securite.mfaInactive")}
              </Badge>
              {user?.mfa_requise ? <span className="muted">{t("securite.mfaRequise")}</span> : null}
            </div>
            <p className="muted">{t("shell.secu.mfaTexte")}</p>
          </div>
          <Link to="/mon-mot-de-passe" className="btn ghost">
            <KeyRound size={15} aria-hidden="true" />
            {t("shell.secu.motDePasse")}
          </Link>
        </div>
      </SectionCard>

      <SectionCard
        title={t("securite.delegations")}
        subtitle={t("securite.delegationsIntro")}
        actions={
          <QuickForm
            title={t("securite.nouvelle")}
            endpoint="/api/workflow/delegations/"
            fields={[
              { name: "email_delegataire", label: t("securite.delegataire"), required: true },
              { name: "date_debut", label: t("securite.du"), type: "date", required: true },
              { name: "date_fin", label: t("securite.au"), type: "date", required: true },
              { name: "motif", label: t("securite.motif"), required: true },
            ]}
          />
        }
      >
        <DataGrid
          columns={delegationColumns}
          rows={delegations.data ?? []}
          loading={delegations.isLoading}
          caption={t("securite.delegations")}
          emptyIcon={UserX}
          emptyLabel={t("securite.aucune")}
          initialSort={{ id: "periode", desc: true }}
          rowActions={(d) =>
            !d.annulee_le && d.delegant_email === user?.email
              ? [{ label: t("securite.annuler"), icon: UserX, danger: true, onSelect: () => setAAnnuler(d) }]
              : []
          }
        />
      </SectionCard>

      {admin ? (
        <SectionCard
          title={t("securite.journal")}
          subtitle={t("securite.journalIntro")}
          actions={
            <button type="button" className="btn ghost" onClick={() => void exporter()}>
              <Download size={15} aria-hidden="true" />
              {t("securite.exporter")}
            </button>
          }
        >
          <div className="shell-toolbar inline">
            <label className="sr-only" htmlFor="journal-evenement">
              {t("securite.col.evenement")}
            </label>
            <select
              id="journal-evenement"
              className="control"
              value={evenement}
              onChange={(e) => {
                setEvenement(e.target.value);
                journal.setPage(1);
              }}
            >
              <option value="">{t("securite.tous")}</option>
              {EVENEMENTS.map((e) => (
                <option key={e} value={e}>
                  {t(`shell.secu.evenements.${e}`)}
                </option>
              ))}
            </select>
          </div>
          <PagedDataGrid list={journal} columns={journalColumns} caption={t("securite.journal")} density="compact" />
        </SectionCard>
      ) : null}

      <Modal
        open={aAnnuler !== null}
        onOpenChange={(o) => {
          if (!o) setAAnnuler(null);
        }}
        title={t("shell.secu.annulerTitre")}
        description={aAnnuler ? `${aAnnuler.code} · ${aAnnuler.delegataire_email}` : undefined}
        width={460}
        footer={
          <>
            <SheetClose>
              <button type="button" className="btn ghost">
                {t("shell.secu.garder")}
              </button>
            </SheetClose>
            <button type="button" className="btn danger" disabled={annuler.isPending} onClick={() => aAnnuler && annuler.mutate(aAnnuler)}>
              {t("securite.annuler")}
            </button>
          </>
        }
      >
        <p className="muted">{t("shell.secu.annulerTexte")}</p>
      </Modal>
    </>
  );
}
