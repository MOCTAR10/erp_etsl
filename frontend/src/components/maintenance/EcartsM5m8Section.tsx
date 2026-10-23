import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useTranslation } from "react-i18next";

import { api } from "../../api/client";
import { formatMoney, formatNumber } from "../../lib/format";
import { describeError } from "../../lib/offlineQueue";
import { Badge, DataTable, SectionCard } from "../ui";
import type { Column } from "../ui";

interface Centre {
  id: number;
  code: string;
  label: string;
}
interface ActifCentre {
  id: string;
  code: string;
  designation: string;
  centre_analytique: number | null;
  centre_code: string;
}
interface LigneMachine {
  actif: string;
  designation: string;
  centre: string;
  compte: string;
  nb_ot: number;
  main_oeuvre: string;
  pieces: string;
  total: string;
}
interface LigneCentre {
  centre: string;
  libelle: string;
  nb_ot: number;
  mois: string[];
  total: string;
}
interface Couts {
  annee: number;
  devise: string;
  mois: string[];
  cumul: string[];
  machines: LigneMachine[];
  centres: LigneCentre[];
  total: string;
  totaux: { gr_618: string; hors_gr: string };
  provisoire: boolean;
}
interface OtCloture {
  id: string;
  code: string;
  actif_code: string;
  statut: string;
  centre_code: string;
  cout_total: string | null;
  ecriture_numero: string | null;
  motif_ecriture: string;
}

/** Matrice mensuelle : nombres exacts (l'unité FCFA est portée par l'en-tête), sinon montants complets. */
const nombre = (v: string | null | undefined) => (v === null || v === undefined ? "—" : formatNumber(v));
const fcfa = (v: string | null) => formatMoney(v);
const MOIS = Array.from({ length: 12 }, (_, i) => i);

interface LigneMatrice {
  id: string;
  centre: string;
  libelle: string;
  nb_ot: number | null;
  mois: string[];
  total: string;
}

/** Écarts maintenance : centre analytique par machine, écriture du coût à la clôture d'OT, coûts annuels → contrôle de gestion. */
export function CoutsMaintenanceSection() {
  const { t, i18n } = useTranslation();
  const qc = useQueryClient();
  const [annee, setAnnee] = useState(String(new Date().getFullYear()));
  const [error, setError] = useState<string | null>(null);
  const couts = useQuery({
    queryKey: ["m5m8", "couts-maint", annee],
    queryFn: () => api.get<Couts>(`/api/maintenance/ordres/couts-annuels/?annee=${annee}`),
    enabled: /^\d{4}$/.test(annee),
    retry: 0,
  });
  const centres = useQuery({ queryKey: ["m5m8", "centres"], queryFn: () => api.get<Centre[]>("/api/maintenance/actifs/centres/"), retry: 0 }).data ?? [];
  const actifs = useQuery({ queryKey: ["m5m8", "actifs"], queryFn: () => api.listAll<ActifCentre>("/api/maintenance/actifs/"), retry: 0 }).data ?? [];
  const clotures = (useQuery({ queryKey: ["m5m8", "ot-clotures"], queryFn: () => api.listAll<OtCloture>("/api/maintenance/ordres/"), retry: 0 }).data ?? [])
    .filter((o) => o.statut === "cloture" || o.statut === "archive")
    .slice(0, 10);
  const affecter = useMutation({
    mutationFn: (v: { id: string; centre: string }) => api.patch(`/api/maintenance/actifs/${v.id}/`, { centre_analytique: v.centre ? Number(v.centre) : null }),
    onSuccess: () => {
      setError(null);
      void qc.invalidateQueries({ queryKey: ["m5m8"] });
    },
    onError: (e) => setError(describeError(e)),
  });
  const exporter = (fmt: "xlsx" | "pdf") =>
    api.download(`/api/maintenance/ordres/couts-annuels/?annee=${annee}&export=${fmt}`, `couts-maintenance-${annee}.${fmt}`).catch((e) => setError(describeError(e)));
  const c = couts.data;
  const moisCourt = (m: number) => new Date(2000, m, 1).toLocaleDateString(i18n.language || "fr", { month: "short" });
  const gras = (r: LigneMatrice, v: string) => (r.id === "__cumul" ? <strong>{v}</strong> : v);

  const lignesMatrice: LigneMatrice[] = c
    ? [
        ...c.centres.map((r) => ({ id: r.centre, centre: r.centre, libelle: r.libelle, nb_ot: r.nb_ot, mois: r.mois, total: r.total })),
        { id: "__cumul", centre: t("ecarts_m5m8.maint.cumul"), libelle: "", nb_ot: null, mois: c.cumul, total: c.total },
      ]
    : [];
  const colsMatrice: Column<LigneMatrice>[] = [
    {
      key: "centre",
      header: t("ecarts_m5m8.maint.centre"),
      render: (r) =>
        r.nb_ot === null ? (
          <strong>{r.centre}</strong>
        ) : (
          <span title={r.libelle}>
            {r.centre} <span className="muted">· {t("tableaux.maintenance.nbOt", { count: r.nb_ot })}</span>
          </span>
        ),
    },
    ...MOIS.map<Column<LigneMatrice>>((m) => ({ key: `m${m}`, header: moisCourt(m), num: true, render: (r) => gras(r, nombre(r.mois[m])) })),
    { key: "total", header: t("tableaux.maintenance.totalFcfa"), num: true, render: (r) => gras(r, nombre(r.total)) },
  ];

  const colsMachines: Column<LigneMachine & { id: string }>[] = [
    { key: "machine", header: t("ecarts_m5m8.maint.machine"), render: (r) => `${r.actif} · ${r.designation}`, sortValue: (r) => r.actif },
    { key: "centre", header: t("ecarts_m5m8.maint.centre"), render: (r) => r.centre, sortValue: (r) => r.centre },
    { key: "compte", header: t("ecarts_m5m8.maint.compte"), render: (r) => r.compte },
    { key: "ot", header: t("tableaux.maintenance.ot"), num: true, render: (r) => formatNumber(r.nb_ot), sortValue: (r) => r.nb_ot },
    { key: "mo", header: t("ecarts_m5m8.maint.mo"), num: true, render: (r) => fcfa(r.main_oeuvre), sortValue: (r) => Number(r.main_oeuvre) },
    { key: "pieces", header: t("ecarts_m5m8.maint.pieces"), num: true, render: (r) => fcfa(r.pieces), sortValue: (r) => Number(r.pieces) },
    { key: "total", header: t("ecarts_m5m8.maint.totalCol"), num: true, render: (r) => fcfa(r.total), sortValue: (r) => Number(r.total) },
  ];

  const colsClotures: Column<OtCloture>[] = [
    { key: "ot", header: t("tableaux.maintenance.ot"), render: (o) => o.code },
    { key: "machine", header: t("ecarts_m5m8.maint.machine"), render: (o) => o.actif_code },
    { key: "centre", header: t("ecarts_m5m8.maint.centre"), render: (o) => o.centre_code },
    { key: "total", header: t("ecarts_m5m8.maint.totalCol"), num: true, render: (o) => fcfa(o.cout_total) },
    {
      key: "ecriture",
      header: t("ecarts_m5m8.maint.ecriture"),
      render: (o) => (o.ecriture_numero ? <Badge tone="ok">{o.ecriture_numero}</Badge> : <span className="muted">{o.motif_ecriture || "—"}</span>),
    },
  ];

  const colsAffectation: Column<ActifCentre>[] = [
    { key: "machine", header: t("ecarts_m5m8.maint.machine"), render: (a) => `${a.code} · ${a.designation}`, sortValue: (a) => a.code },
    {
      key: "centre",
      header: t("ecarts_m5m8.maint.centre"),
      render: (a) => (
        <select
          className="control"
          aria-label={`${t("ecarts_m5m8.maint.centre")} ${a.code}`}
          value={a.centre_analytique === null ? "" : String(a.centre_analytique)}
          onChange={(ev) => affecter.mutate({ id: a.id, centre: ev.target.value })}
        >
          <option value="">{t("ecarts_m5m8.maint.centreAuto", { code: a.centre_code })}</option>
          {centres.map((ce) => (
            <option key={ce.id} value={String(ce.id)}>
              {ce.code} · {ce.label}
            </option>
          ))}
        </select>
      ),
    },
  ];

  return (
    <SectionCard title={t("ecarts_m5m8.maint.title")}>
      <div data-testid="couts-maintenance">
        <p className="muted">
          <Badge tone="warn">{t("ecarts_m5m8.provisoire")}</Badge> {t("ecarts_m5m8.maint.provisoireNote")}
        </p>
        {error && <p className="action-error" role="alert">{error}</p>}
        <div className="action-bar-buttons">
          <label>
            {t("ecarts_m5m8.annee")} <input type="number" min={2000} max={2100} value={annee} onChange={(ev) => setAnnee(ev.target.value)} style={{ width: "6rem" }} />
          </label>
          {c && (
            <>
              <button type="button" className="btn ghost sm" onClick={() => void exporter("xlsx")}>{t("ecarts_m5m8.exportXlsx")}</button>
              <button type="button" className="btn ghost sm" onClick={() => void exporter("pdf")}>{t("ecarts_m5m8.exportPdf")}</button>
            </>
          )}
        </div>
        {couts.isError && <p className="muted">{t("ecarts_m5m8.maint.reserve")}</p>}
        {c && (
          <>
            <p>
              {t("ecarts_m5m8.maint.total")} : <strong>{formatMoney(c.total, { currency: c.devise || "FCFA" })}</strong> · {t("tableaux.maintenance.gr618")} : {fcfa(c.totaux.gr_618)} · {t("ecarts_m5m8.maint.horsGr")} : {fcfa(c.totaux.hors_gr)}{" "}
              {c.provisoire && <Badge tone="warn">{t("ecarts_m5m8.provisoire")}</Badge>}
            </p>
            <div data-testid="couts-centres">
              <DataTable caption={t("ecarts_m5m8.maint.title")} density="compact" columns={colsMatrice} rows={lignesMatrice} />
            </div>
            <div data-testid="couts-machines">
              <DataTable caption={t("tableaux.maintenance.coutsMachines")} columns={colsMachines} rows={c.machines.map((r) => ({ ...r, id: r.actif }))} />
            </div>
          </>
        )}

        <h4>{t("ecarts_m5m8.maint.ecritures")}</h4>
        <div data-testid="ecritures-ot">
          <DataTable caption={t("ecarts_m5m8.maint.ecritures")} columns={colsClotures} rows={clotures} emptyLabel={t("ecarts_m5m8.maint.aucuneCloture")} />
        </div>

        <h4>{t("ecarts_m5m8.maint.affectation")}</h4>
        <div data-testid="centres-machines">
          <DataTable caption={t("ecarts_m5m8.maint.affectation")} columns={colsAffectation} rows={actifs} />
        </div>
      </div>
    </SectionCard>
  );
}
