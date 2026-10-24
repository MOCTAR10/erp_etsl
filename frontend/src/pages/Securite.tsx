import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowRight, Download, KeyRound, ShieldCheck, ShieldOff, UserX } from "lucide-react";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";

import { api } from "../api/client";
import { Badge, DataGrid, Modal, PageHeader, PagedDataGrid, QuickForm, SectionCard, SheetClose, notify } from "../components/ui";
import type { GridColumn } from "../components/ui";
import { formatDate, formatDateTime } from "../lib/format";
import { displayName } from "../lib/people";
import { describeError } from "../lib/offlineQueue";
import { usePagedList } from "../lib/usePagedList";
import { useAuth } from "../store/auth";
import type { Delegation, JournalAcces, Me, Paginated } from "../types";
import { EnrolementTotp, useModeSignature } from "./Signatures";

/** Ligne du journal regroupée : connexions consécutives identiques (même compte, même poste) fusionnées (A-20). */
type LigneJournal = JournalAcces & { n: number; debut: string };

function regrouper(rows: JournalAcces[]): LigneJournal[] {
  const out: LigneJournal[] = [];
  for (const r of rows) {
    const prev = out[out.length - 1];
    if (prev && prev.evenement === r.evenement && prev.email === r.email && prev.ip === r.ip && prev.chemin === r.chemin) {
      prev.n += 1;
      prev.debut = r.cree_le; // liste triée du plus récent au plus ancien
    } else {
      out.push({ ...r, n: 1, debut: r.cree_le });
    }
  }
  return out;
}

const memeJour = (a: string, b: string) => new Date(a).toDateString() === new Date(b).toDateString();
const heure = (iso: string, locale: string) => new Date(iso).toLocaleTimeString(locale, { hour: "2-digit", minute: "2-digit" });

/** Adresse lisible : boucle locale → « Poste local ». */
const POSTE_LOCAL = /^(127\.|::1$|localhost$)/;

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

/** Zone fonctionnelle d'un chemin d'API journalisé (« /api/achats/… » → « Achats ») ; le chemin exact reste en infobulle. */
function zoneLisible(chemin: string, tr: (cle: string) => string): string {
  if (/^\/api\/users\/token/.test(chemin)) return tr("revueR1.secu.zones.connexion");
  const cle = `revueR1.secu.zones.${chemin.split("/")[2] ?? ""}`;
  const v = tr(cle);
  return v === cle ? tr("revueR1.secu.zones.autre") : v;
}

/** Sécurité (lot 15b) : MFA du compte, délégations temporaires (EX-G-02), journal des accès pour l'admin (EX-G-10). */
export function SecuritePage() {
  const { t, i18n } = useTranslation();
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
    { pageSize: 20, extra: evenement ? `evenement=${evenement}` : "", enabled: admin },
  );
  const journalGroupe = { ...journal, rows: regrouper(journal.rows) } as unknown as ReturnType<typeof usePagedList<LigneJournal>>;
  // Comptes (admin) : le journal affiche un nom, l'e-mail reste en infobulle.
  const annuaire = useQuery({
    queryKey: ["admin-comptes-annuaire"],
    queryFn: () => api.listAll<Me>("/api/users/users/"),
    enabled: admin,
    retry: 0,
    staleTime: 300_000,
  }).data;
  const nomParEmail = (email: string) => {
    const c = (annuaire ?? []).find((u) => u.email?.toLowerCase() === email.toLowerCase());
    return displayName(t, c ?? { email });
  };
  // Double authentification : état servi par le mode de signature (à jour après l'enrôlement), sinon la session.
  const modeSig = useModeSignature().data;
  const [enrolement, setEnrolement] = useState(false);

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
      header: t("shell.secu.qui"),
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
  const journalColumns: GridColumn<LigneJournal>[] = [
    {
      key: "quand",
      header: t("securite.col.quand"),
      width: 200,
      render: (j) =>
        j.n > 1 ? (
          <span className="num">
            {formatDateTime(j.debut)} → {memeJour(j.debut, j.cree_le) ? heure(j.cree_le, i18n.language) : formatDateTime(j.cree_le)}
          </span>
        ) : (
          <span className="num">{formatDateTime(j.cree_le)}</span>
        ),
    },
    {
      key: "evenement",
      header: t("securite.col.evenement"),
      render: (j) => (
        <span className="badge-row">
          <Badge tone={/echec|bloquee/.test(j.evenement) ? "err" : j.evenement === "export" ? "info" : "neutral"}>
            {j.n > 1
              ? t("premiumPilotage.securite.groupe", { count: j.n, evenement: t(`shell.secu.evenements.${j.evenement}`, { defaultValue: j.evenement_label }) })
              : t(`shell.secu.evenements.${j.evenement}`, { defaultValue: j.evenement_label })}
          </Badge>
        </span>
      ),
    },
    {
      key: "compte",
      header: t("securite.col.compte"),
      render: (j) => (j.email ? <span title={j.email}>{nomParEmail(j.email)}</span> : "—"),
    },
    {
      key: "ip",
      header: t("securite.col.ip"),
      width: 140,
      render: (j) =>
        !j.ip ? (
          "—"
        ) : POSTE_LOCAL.test(j.ip) ? (
          <span title={j.ip}>{t("premiumPilotage.securite.posteLocal")}</span>
        ) : (
          <span className="num">{j.ip}</span>
        ),
    },
    {
      key: "ressource",
      header: t("securite.col.ressource"),
      render: (j) => {
        const zone = zoneLisible(j.chemin, (k) => t(k));
        const evt = t(`shell.secu.evenements.${j.evenement}`, { defaultValue: j.evenement_label });
        // Ressource identique à l'événement (« Connexion » / « Connexion ») : rien à ajouter.
        return zone.toLowerCase() === evt.toLowerCase() ? (
          <span className="muted" title={j.chemin}>
            —
          </span>
        ) : (
          <span className="shell-zone" title={j.chemin}>
            {zone}
          </span>
        );
      },
    },
  ];

  const mfaActive = Boolean(modeSig?.mfa_active ?? user?.mfa_active);
  return (
    <div className="shell-page">
      <PageHeader title={t("securite.title")} subtitle={t("shell.secu.sousTitre")} />

      <SectionCard title={t("securite.mfa")}>
        <div className="mfa-row">
          <span className={mfaActive ? "mfa-icon ok" : "mfa-icon"} aria-hidden="true">
            {mfaActive ? <ShieldCheck size={18} /> : <ShieldOff size={18} />}
          </span>
          <div className="mfa-text">
            <div className="mfa-status">
              <strong className="mfa-etat">{mfaActive ? t("revueR1.secu.mfaOn") : t("revueR1.secu.mfaOff")}</strong>
              {user?.mfa_requise ? <Badge tone="warn">{t("securite.mfaRequise")}</Badge> : null}
            </div>
            <p className="muted">{t("shell.secu.mfaTexte")}</p>
          </div>
          <div className="mfa-actions">
            {!mfaActive && !enrolement ? (
              <button type="button" className="btn primary" onClick={() => setEnrolement(true)}>
                <ShieldCheck size={15} aria-hidden="true" />
                {t("premiumPilotage.securite.activer")}
              </button>
            ) : null}
            <Link to="/mon-mot-de-passe" className="mfa-link">
              <KeyRound size={14} aria-hidden="true" />
              {t("shell.secu.motDePasse")}
            </Link>
          </div>
        </div>
      </SectionCard>
      {/* Même enrôlement que l'écran Signatures (A-19). */}
      {!mfaActive && enrolement ? <EnrolementTotp /> : null}

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
          <PagedDataGrid list={journalGroupe} columns={journalColumns} caption={t("securite.journal")} density="compact" maxHeight="none" />
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
    </div>
  );
}
