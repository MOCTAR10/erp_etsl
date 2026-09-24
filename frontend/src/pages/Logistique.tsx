import { useQuery } from "@tanstack/react-query";
import { ClipboardList, MapPin, Truck } from "lucide-react";
import { useTranslation } from "react-i18next";

import { api } from "../api/client";
import { formatDate, formatNumber } from "../lib/format";
import { Board, BoardCard, BoardColumn, BoardSkeleton, ErrorState, Kpi, PageHeader } from "../components/ui";
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

function EquipementCard({ eq, index }: { eq: EquipementParc; index: number }) {
  const { t } = useTranslation();
  return (
    <BoardCard delay={Math.min(index * 0.03, 0.3)}>
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
    </BoardCard>
  );
}

function LocationCard({ loc, index }: { loc: LocationGR; index: number }) {
  const { t } = useTranslation();
  const masked = loc.montant_estime === null;
  return (
    <Kpi
      label={`${loc.code} · ${loc.statut_label}${loc.imputation_618 ? ` · 618` : ""}`}
      value={masked ? t("logistique.masked") : formatNumber(Number(loc.montant_estime))}
      hint={`${loc.equipement_code} — ${loc.partenaire_name} · ${loc.periodicite_label} · ${
        loc.consommation === null ? "—" : `${formatNumber(Number(loc.consommation))}`
      }`}
      icon={MapPin}
      tone="warn"
      delay={index * 0.05}
    />
  );
}

function DemandeCard({ demande, index }: { demande: DemandeMobilisation; index: number }) {
  const { t } = useTranslation();
  return (
    <Kpi
      label={`${demande.code} · ${demande.statut_label}`}
      value={demande.label}
      hint={`${demande.departement}${demande.date_debut ? ` · ${t("logistique.debut")} ${formatDate(demande.date_debut, "fr")}` : ""}${
        demande.affaire_code ? ` · ${demande.affaire_code}` : ""
      }`}
      icon={ClipboardList}
      tone="brand"
      delay={index * 0.05}
    />
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

  if (byStatus.isLoading || parc.isLoading) return <BoardSkeleton cols={5} rows={3} />;
  if (byStatus.isError || parc.isError || !byStatus.data)
    return (
      <ErrorState
        message={t("common.error")}
        onRetry={() => {
          void byStatus.refetch();
          void parc.refetch();
          void locations.refetch();
          void demandes.refetch();
        }}
        retryLabel={t("common.retry")}
      />
    );

  const groups = byStatus.data;
  const stats = parc.data;

  const statutLabel = (key: EquipementStatut) => t(`logistique.${key}`);

  return (
    <>
      <PageHeader title={t("logistique.title")} />

      <div className="kpi-grid">
        <Kpi
          label={`${t("logistique.parc")} · ${stats?.parc.total ?? groups.disponible.length}`}
          value={`${stats ? formatNumber(stats.parc.global_rental) : 0} GR · ${stats ? formatNumber(stats.parc.propre) : 0} ${t("logistique.propre")}`}
          hint={`${t("logistique.equipements")} · ${stats ? formatNumber(stats.parc.total) : 0}`}
          icon={Truck}
          tone="brand"
          delay={0}
        />
        <Kpi
          label={t("logistique.locationsActives")}
          value={stats ? stats.locations.actives : "—"}
          hint={
            stats?.locations.total_montant_estime !== undefined
              ? `${formatNumber(stats.locations.total_montant_estime)} FCFA`
              : t("logistique.masked")
          }
          icon={MapPin}
          tone="accent"
          delay={0.05}
        />
        <Kpi label={t("logistique.demandes")} value={demandes.data?.length ?? "—"} icon={ClipboardList} tone="warn" delay={0.1} />
      </div>

      <div style={{ overflowX: "auto" }}>
        <Board>
          {BOARD_ORDER.map((st, ci) => (
            <BoardColumn
              key={st}
              title={statutLabel(st)}
              count={groups[st].length}
              tone={STATUS_BADGE[st]}
              delay={ci * 0.05}
              minWidth={260}
            >
              {groups[st].length === 0 ? (
                <p className="muted" style={{ padding: "0.5rem 0.25rem" }}>
                  {t("common.empty")}
                </p>
              ) : (
                groups[st].map((eq, i) => <EquipementCard key={eq.id} eq={eq} index={i} />)
              )}
            </BoardColumn>
          ))}
        </Board>
      </div>

      {(locations.data ?? []).length > 0 ? (
        <h3 className="muted" style={{ marginTop: "2rem" }}>
          {t("logistique.locationsActives")} — GLOBAL RENTAL
        </h3>
      ) : null}
      <div className="kpi-grid">
        {(locations.data ?? []).map((loc, i) => (
          <LocationCard key={loc.id} loc={loc} index={i} />
        ))}
      </div>

      {(demandes.data ?? []).length > 0 ? (
        <>
          <h3 className="muted" style={{ marginTop: "2rem" }}>
            {t("logistique.demandes")}
          </h3>
          <div className="kpi-grid">
            {(demandes.data ?? []).map((demande, i) => (
              <DemandeCard key={demande.id} demande={demande} index={i} />
            ))}
          </div>
        </>
      ) : null}
    </>
  );
}