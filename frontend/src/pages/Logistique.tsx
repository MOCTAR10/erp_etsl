import { useQuery } from "@tanstack/react-query";
import { motion } from "motion/react";
import { useTranslation } from "react-i18next";

import { api } from "../api/client";
import { formatDate, formatNumber } from "../lib/format";
import { motionTokens } from "../theme/tokens";
import type {
  DemandeMobilisation,
  EquipementParc,
  EquipementStatut,
  LocationGR,
  Paginated,
} from "../types";

type Groups = Record<EquipementStatut, EquipementParc[]>;

const STATUS_BADGE: Record<EquipementStatut, "ok" | "warn" | "err" | "brand"> = {
  disponible: "ok",
  affecte: "brand",
  en_location: "warn",
  hors_service: "err",
  maintenance: "warn",
};
const VALID_STATUSES = new Set<EquipementStatut>([
  "disponible",
  "affecte",
  "en_location",
  "hors_service",
  "maintenance",
]);
const BOARD_ORDER: EquipementStatut[] = ["disponible", "affecte", "en_location", "maintenance", "hors_service"];

function EquipementCard({ eq }: { eq: EquipementParc }) {
  const { t } = useTranslation();
  return (
    <motion.div
      layout
      initial={{ opacity: 0, y: motionTokens.distance.xs, scale: 0.98 }}
      animate={{ opacity: 1, y: 0, scale: 1 }}
      transition={{ duration: motionTokens.duration.base, ease: motionTokens.ease.out }}
      className="task-card"
    >
      <div className="title">
        {eq.is_global_rental ? (
          <span className="badge warn" title={t("logistique.globalRental")}>
            GR
          </span>
        ) : null}{" "}
        <span className="muted">{eq.code}</span> · {eq.label}
      </div>
      <div className="meta">
        {eq.categorie_label}
        {eq.registration ? ` · ${eq.registration}` : ""}
      </div>
      <div className="meta" style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <span className={`badge ${STATUS_BADGE[eq.statut] ?? "brand"}`}>{eq.statut_label}</span>
        <span>
          {eq.compteur_type_label}: {formatNumber(Number(eq.compteur_value))}
        </span>
      </div>
      {eq.site || eq.proprietaire_code ? (
        <div className="meta muted">
          {[eq.site, eq.proprietaire_code].filter(Boolean).join(" · ")}
        </div>
      ) : null}
    </motion.div>
  );
}

function LocationCard({ loc }: { loc: LocationGR }) {
  const { t } = useTranslation();
  const masked = loc.montant_estime === null;
  return (
    <div className="card kpi" key={loc.id}>
      <span className="kpi-label">
        {loc.code} · {loc.statut_label} {loc.imputation_618 ? `· 618` : ""}
      </span>
      <span className="kpi-value">
        {masked ? t("logistique.masked") : formatNumber(Number(loc.montant_estime))}
      </span>
      <span className="meta muted">
        {loc.equipement_code} — {loc.partenaire_name} · {loc.periodicite_label} ·{" "}
        {loc.consommation === null ? "—" : `${formatNumber(Number(loc.consommation))}`}
      </span>
    </div>
  );
}

function DemandeCard({ demande }: { demande: DemandeMobilisation }) {
  const { t } = useTranslation();
  return (
    <div className="card kpi" key={demande.id}>
      <span className="kpi-label">
        {demande.code} · {demande.statut_label}
      </span>
      <span className="kpi-value">{demande.label}</span>
      <span className="meta muted">
        {demande.departement}
        {demande.date_debut ? ` · ${t("logistique.debut")} ${formatDate(demande.date_debut, "fr")}` : ""}
        {demande.affaire_code ? ` · ${demande.affaire_code}` : ""}
      </span>
    </div>
  );
}

export function LogistiquePage() {
  const { t } = useTranslation();

  const byStatus = useQuery({
    queryKey: ["equipements"],
    queryFn: () => api.equipements(`?page_size=100`),
    select: (page: Paginated<EquipementParc>) => {
      const groups: Groups = {
        disponible: [],
        affecte: [],
        en_location: [],
        hors_service: [],
        maintenance: [],
      };
      for (const eq of page.results) {
        if (VALID_STATUSES.has(eq.statut)) groups[eq.statut].push(eq);
      }
      return groups;
    },
  });

  const parc = useQuery({
    queryKey: ["parc"],
    queryFn: () => api.parcStats(),
  });

  const locations = useQuery({
    queryKey: ["locations"],
    queryFn: () => api.locationsGR(`?page_size=100`),
    select: (page: Paginated<LocationGR>) => page.results,
  });

  const demandes = useQuery({
    queryKey: ["demandes"],
    queryFn: () => api.demandesLog(`?page_size=50`),
    select: (page: Paginated<DemandeMobilisation>) => page.results,
  });

  if (byStatus.isLoading || parc.isLoading)
    return <p className="muted">{t("common.loading")}</p>;
  if (byStatus.isError || parc.isError || !byStatus.data)
    return (
      <p>
        {t("common.error")}{" "}
        <button
          className="btn ghost"
          onClick={() => {
            void byStatus.refetch();
            void parc.refetch();
            void locations.refetch();
            void demandes.refetch();
          }}
        >
          {t("common.retry")}
        </button>
      </p>
    );

  const groups = byStatus.data;
  const stats = parc.data;

  const statutLabel = (key: EquipementStatut) => t(`logistique.${key}`);

  return (
    <>
      <h2>{t("logistique.title")}</h2>

      <div className="kpis">
        <div className="card kpi">
          <span className="kpi-label">
            {t("logistique.parc")} · {stats?.parc.total ?? groups.disponible.length}
          </span>
          <span className="kpi-value">
            {stats ? formatNumber(stats.parc.global_rental) : 0} GR · {stats ? formatNumber(stats.parc.propre) : 0}{" "}
            {t("logistique.propre")}
          </span>
          <span className="meta muted">
            {t("logistique.equipements")} · {stats ? formatNumber(stats.parc.total) : 0}
          </span>
        </div>
        <div className="card kpi">
          <span className="kpi-label">{t("logistique.locationsActives")}</span>
          <span className="kpi-value">{stats ? stats.locations.actives : "—"}</span>
          <span className="meta muted">
            {stats?.locations.total_montant_estime !== undefined
              ? `${formatNumber(stats.locations.total_montant_estime)} FCFA`
              : t("logistique.masked")}
          </span>
        </div>
        <div className="card kpi">
          <span className="kpi-label">{t("logistique.demandes")}</span>
          <span className="kpi-value">{demandes.data?.length ?? "—"}</span>
        </div>
      </div>

      <div className="board" style={{ overflowX: "auto" }}>
        {BOARD_ORDER.map((st) => (
          <motion.div
            key={st}
            layout
            className="board-col"
            style={{ minWidth: 260 }}
            initial={{ opacity: 0, y: motionTokens.distance.sm }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: motionTokens.duration.base, ease: motionTokens.ease.out }}
          >
            <div className="board-col-head">
              <span>{statutLabel(st)}</span>
              <span className={`badge ${STATUS_BADGE[st]}`}>{groups[st].length}</span>
            </div>
            {groups[st].length === 0 ? (
              <p className="muted" style={{ padding: "0.5rem 0.25rem" }}>
                {t("common.empty")}
              </p>
            ) : (
              groups[st].map((eq) => <EquipementCard key={eq.id} eq={eq} />)
            )}
          </motion.div>
        ))}
      </div>

      {(locations.data ?? []).length > 0 ? (
        <h3 className="muted" style={{ marginTop: "2rem" }}>
          {t("logistique.locationsActives")} — GLOBAL RENTAL
        </h3>
      ) : null}
      <div className="kpis" style={{ flexWrap: "wrap" }}>
        {(locations.data ?? []).map((loc) => (
          <LocationCard key={loc.id} loc={loc} />
        ))}
      </div>

      {(demandes.data ?? []).length > 0 ? (
        <>
          <h3 className="muted" style={{ marginTop: "2rem" }}>
            {t("logistique.demandes")}
          </h3>
          <div className="kpis" style={{ flexWrap: "wrap" }}>
            {(demandes.data ?? []).map((demande) => (
              <DemandeCard key={demande.id} demande={demande} />
            ))}
          </div>
        </>
      ) : null}
    </>
  );
}