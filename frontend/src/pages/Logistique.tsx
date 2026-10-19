import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { ClipboardList, MapPin, Truck } from "lucide-react";
import { useTranslation } from "react-i18next";

import { api } from "../api/client";
import { GrAffairesSection, ParametresLogistiqueSection } from "../components/workflow/GrAffairesSection";
import { TarifsGrSection } from "../components/workflow/TarifsGrSection";
import { formatDate, formatNumber } from "../lib/format";
import { pagedQuery, usePagedList } from "../lib/usePagedList";
import { ActionBar, Badge, Board, BoardCard, BoardColumn, BoardSkeleton, ErrorState, Kpi, PageHeader, PagedDataTable, SearchField, SectionCard } from "../components/ui";
import type { Column } from "../components/ui";
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

type T = (key: string) => string;

function locationColumns(t: T): Column<LocationGR>[] {
  return [
    { key: "code", header: t("logistique.col.code"), render: (l) => l.code },
    { key: "equip", header: t("logistique.col.equipement"), render: (l) => l.equipement_code },
    { key: "partner", header: t("logistique.col.partenaire"), render: (l) => l.partenaire_name },
    { key: "period", header: t("logistique.col.periodicite"), render: (l) => l.periodicite_label },
    {
      key: "conso",
      header: t("logistique.col.consommation"),
      num: true,
      render: (l) => (l.consommation === null ? "—" : formatNumber(Number(l.consommation))),
    },
    {
      key: "montant",
      header: t("logistique.col.montant"),
      num: true,
      render: (l) => (l.montant_estime === null ? t("logistique.masked") : `${formatNumber(Number(l.montant_estime))} F`),
    },
    {
      key: "statut",
      header: t("logistique.col.statut"),
      render: (l) => (
        <>
          <Badge tone="brand">{l.statut_label}</Badge> {l.imputation_618 && <Badge tone="warn">618</Badge>}
          <ActionBar
            actions={[
              ...(l.statut === "brouillon" && !l.emis_le
                ? [{ label: t("logistique.act.emettre"), path: `/api/logistique/locations/${l.id}/emettre/`, tone: "ghost" as const }]
                : []),
              ...(l.statut === "brouillon"
                ? [{ label: t("actions.demarrer"), path: `/api/logistique/locations/${l.id}/demarrer/`, prompt: { name: "lecture_initiale", label: t("logistique.act.compteurDepart") } }]
                : []),
              ...(l.statut === "active"
                ? [{ label: t("actions.cloturer"), path: `/api/logistique/locations/${l.id}/cloturer/`, prompt: { name: "lecture_finale", label: t("logistique.act.compteurFin") } }]
                : []),
            ]}
          />
        </>
      ),
    },
  ];
}

function demandeColumns(t: T): Column<DemandeMobilisation>[] {
  return [
    { key: "code", header: t("logistique.col.code"), render: (d) => d.code },
    { key: "label", header: t("logistique.col.besoin"), render: (d) => d.label },
    { key: "dept", header: t("logistique.col.departement"), render: (d) => d.departement || "—" },
    { key: "debut", header: t("logistique.debut"), render: (d) => (d.date_debut ? formatDate(d.date_debut) : "—") },
    { key: "affaire", header: t("logistique.col.affaire"), render: (d) => d.affaire_code ?? "—" },
    {
      key: "statut",
      header: t("logistique.col.statut"),
      render: (d) => (
        <>
          <Badge tone="brand">{d.statut_label}</Badge>
          <ActionBar
            actions={[
              ...(d.statut === "brouillon"
                ? [{ label: t("logistique.act.soumettre"), path: `/api/logistique/demandes/${d.id}/soumettre/`, tone: "ghost" as const }]
                : []),
              ...(d.statut === "soumise" ? [{ label: t("logistique.act.traiter"), path: `/api/logistique/demandes/${d.id}/traiter/` }] : []),
            ]}
          />
        </>
      ),
    },
  ];
}

export function LogistiquePage() {
  const { t } = useTranslation();

  const [eqSearch, setEqSearch] = useState("");
  const byStatus = useQuery({
    queryKey: ["equipements", eqSearch],
    queryFn: () => api.equipements(pagedQuery(1, 500, eqSearch)),
    placeholderData: keepPreviousData,
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

  const locations = usePagedList<LocationGR>("locations", (q) => api.locationsGR(q));
  const demandes = usePagedList<DemandeMobilisation>("demandes", (q) => api.demandesLog(q));

  if (byStatus.isLoading || parc.isLoading) return <BoardSkeleton cols={5} rows={3} />;
  if (byStatus.isError || parc.isError || !byStatus.data)
    return (
      <ErrorState
        message={t("common.error")}
        onRetry={() => {
          void byStatus.refetch();
          void parc.refetch();
          void locations.query.refetch();
          void demandes.query.refetch();
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
        <Kpi label={t("logistique.demandes")} value={demandes.count} icon={ClipboardList} tone="warn" delay={0.1} />
      </div>

      <SearchField value={eqSearch} onChange={setEqSearch} placeholder={t("logistique.searchEquipements")} />

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
              limit={20}
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

      {(locations.count > 0 || locations.search) && (
        <SectionCard title={`${t("logistique.locationsActives")} — GLOBAL RENTAL`}>
          <PagedDataTable list={locations} columns={locationColumns(t)} caption={t("logistique.locationsActives")} searchPlaceholder={t("logistique.searchLocations")} />
        </SectionCard>
      )}
      <GrAffairesSection />
      <TarifsGrSection />
      <ParametresLogistiqueSection />
      {(demandes.count > 0 || demandes.search) && (
        <SectionCard title={`${t("logistique.demandes")} · ${demandes.count}`}>
          <PagedDataTable list={demandes} columns={demandeColumns(t)} caption={t("logistique.demandes")} searchPlaceholder={t("logistique.searchDemandes")} />
        </SectionCard>
      )}
    </>
  );
}