import { useQuery } from "@tanstack/react-query";
import { motion } from "motion/react";
import { useTranslation } from "react-i18next";

import { api } from "../api/client";
import { formatNumber } from "../lib/format";
import { motionTokens } from "../theme/tokens";
import type { AlertesAgregees, DashboardDirection, ReportingPetrolier } from "../types";

const BANDE_BADGE: Record<string, "ok" | "warn" | "err"> = {
  en_cours: "ok",
  j90: "ok",
  j60: "warn",
  j30: "warn",
  expiree: "err",
};

function Kpi({
  label,
  value,
  desc,
}: {
  label: string;
  value: string | number;
  desc?: string;
}) {
  return (
    <motion.div
      layout
      initial={{ opacity: 0, y: motionTokens.distance.xs, scale: 0.98 }}
      animate={{ opacity: 1, y: 0, scale: 1 }}
      transition={{ duration: motionTokens.duration.base, ease: motionTokens.ease.out }}
      className="card kpi"
    >
      <span className="kpi-label">{label}</span>
      <span className="kpi-value">{value}</span>
      {desc ? <span className="meta muted">{desc}</span> : null}
    </motion.div>
  );
}

function SectionTitle({ text }: { text: string }) {
  return (
    <h3 className="muted" style={{ marginTop: "2rem" }}>
      {text}
    </h3>
  );
}

export function DirectionPage() {
  return <DirectionInner />;
}

function DirectionInner() {
  const { t } = useTranslation();

  const direction = useQuery({
    queryKey: ["direction"],
    queryFn: () => api.dashboardDirection(),
  });
  const petrolier = useQuery({
    queryKey: ["petrolier"],
    queryFn: () => api.reportingPetrolier(),
  });
  const alertes = useQuery({
    queryKey: ["alertes-agregees"],
    queryFn: () => api.alertesAgregees(),
  });

  if (direction.isPending || petrolier.isPending || alertes.isPending) {
    return <p className="muted">{t("common.loading")}</p>;
  }
  if (direction.isError || petrolier.isError || alertes.isError) {
    return (
      <p>
        {t("common.error")}{" "}
        <button
          className="btn ghost"
          onClick={() => {
            void direction.refetch();
            void petrolier.refetch();
            void alertes.refetch();
          }}
        >
          {t("common.retry")}
        </button>
      </p>
    );
  }

  const d = direction.data as DashboardDirection;
  const p = petrolier.data as ReportingPetrolier;
  const a = alertes.data as AlertesAgregees;
  const taux = (p.asmr.taux_disponibilite * 100).toFixed(1);
  const j4 = d.controle_gestion.conformite_j4;
  const j4Taux = (j4.taux * 100).toFixed(0);

  const listes: { clé: string; items: { type: string; code: string | null; libelle: string; date_echeance: string | null; bande: string; jours: number | null }[] }[] = [
    { clé: "documents", items: a.documents },
    {
      clé: "juridique",
      items: [
        ...(a.juridique.conventions ?? []),
        ...(a.juridique.cautions ?? []),
        ...(a.juridique.assurances ?? []),
      ],
    },
    { clé: "rh", items: a.rh },
    { clé: "maintenance", items: a.maintenance },
  ];

  return (
    <>
      <h2>{t("direction.title")}</h2>
      <p className="muted">{t("direction.subtitle")}</p>

      <SectionTitle text={t("direction.directionKPIs")} />
      <div className="kpis">
        <Kpi label={t("direction.documentsRetention")} value={d.documents.total} desc={`${d.documents.dossiers} dossiers`} />
        <Kpi label={t("nav.pipeline")} value={d.commercial.opportunites_ouvertes} desc={`${d.commercial.ca_gagne !== null ? formatNumber(d.commercial.ca_gagne) : "••••••"} F`} />
        <Kpi label={t("nav.stocks")} value={d.stocks.lots} desc={d.stocks.valorisation !== null ? `${formatNumber(d.stocks.valorisation)} F` : "••••••"} />
        <Kpi label={t("nav.hse")} value={d.hse.incidents_ouverts} desc={`${d.hse.jours_sans_accident ?? "—"} ${t("direction.joursSansAccident")}`} />
        <Kpi label={t("nav.rhPaie")} value={d.rh_paie.effectif} desc={`${d.rh_paie.bulletins_mois} ${t("nav.controleGestion")}`} />
        <Kpi label={t("direction.annuel")} value={`${j4.conformes}/${j4.periodes}`} desc={`${j4Taux}%`} />
        <Kpi label={t("nav.juridique")} value={d.juridique.contentieux_ouverts} desc={`${d.juridique.courriers} courriers`} />
        <Kpi label={t("nav.controleGestion")} value={d.controle_gestion.clotures_realisees} desc={`${d.controle_gestion.budgets_approuves} budgets`} />
      </div>

      <SectionTitle text={t("direction.reportPetrolier")} />
      <div className="kpis">
        <Kpi label={t("direction.tauxDisponibilite")} value={`${taux} %`} desc={`${p.asmr.operationnels}/${p.asmr.equipements}`} />
        <Kpi label={t("direction.joursSansAccident")} value={p.hse.jours_sans_accident ?? "—"} desc={`${p.hse.accidents} accidents`} />
        <Kpi label="NC ouvertes" value={p.qualite.nc_ouvertes} desc={`${p.qualite.nc_critiques} critiques`} />
        <Kpi label="Soudeurs qualifiés" value={p.qualite.soudeurs_qualifies} desc={`${p.qualite.soudeurs_expires} expirés`} />
        <Kpi label="Permis ATEX" value={p.hse.permis_atex} desc={`${p.hse.equipements_atex_quarantaine} quarantaine`} />
        <Kpi label="EPI à renouveler" value={p.hse.epi_a_renouveler} desc={`${p.hse.permis_actifs} permis actifs`} />
      </div>

      <SectionTitle text={`${t("direction.alertes")} · ${a.total}`} />
      <div className="kpis" style={{ flexWrap: "wrap" }}>
        {(["expiree", "j30", "j60", "j90"] as const).map((bande) => {
          const count = a.compteurs[bande] ?? 0;
          return (
            <Kpi
              key={bande}
              label={t(`juridique.bande.${bande}`)}
              value={count}
              desc={count > 0 ? String(count) : undefined}
            />
          );
        })}
      </div>
      {a.total > 0 && (
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(260px, 1fr))", gap: "0.5rem" }}>
          {listes.flatMap(({ items }) =>
            items.map((el, i) => (
              <motion.div
                key={`${el.type}-${el.code ?? i}`}
                layout
                initial={{ opacity: 0, y: motionTokens.distance.xs, scale: 0.98 }}
                animate={{ opacity: 1, y: 0, scale: 1 }}
                transition={{ duration: motionTokens.duration.base, ease: motionTokens.ease.out }}
                className="card kpi"
              >
                <span className="kpi-label">
                  {el.type} · {el.code ?? "—"}
                  <span className={`badge ${BANDE_BADGE[el.bande] ?? "ok"}`}>
                    {t(`juridique.bande.${el.bande}`) ?? el.bande}
                  </span>
                </span>
                <span className="kpi-value">{el.libelle}</span>
                <span className="meta muted">
                  {el.date_echeance ?? "—"} · {el.jours !== null ? `${el.jours} j` : "—"}
                </span>
              </motion.div>
            ))
          )}
        </div>
      )}
    </>
  );
}