import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { ClipboardList, MapPin, Truck } from "lucide-react";
import { useTranslation } from "react-i18next";

import { api } from "../api/client";
import { SiteFilter, siteQuery } from "../components/sites/SiteFilter";
import { GrAffairesSection, ParametresLogistiqueSection } from "../components/workflow/GrAffairesSection";
import { TarifsGrSection } from "../components/workflow/TarifsGrSection";
import { EcartsM4Section } from "../components/logistique/EcartsM4Section";
import { formatDate, formatMoney, formatNumber } from "../lib/format";
import { pagedQuery, usePagedList } from "../lib/usePagedList";
import { Badge, Board, BoardCard, BoardColumn, BoardSkeleton, ErrorState, Kpi, PageHeader, PagedDataTable, SearchField, SectionCard, SectionNav } from "../components/ui";
import { actionsColumn } from "../components/ui/DataTable";
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

/** Libellé traduit d'un code de l'API, avec le libellé serveur en repli (jamais de code brut à l'écran). */
type Lbl = (key: string, fallback: string) => string;
function useLbl(): Lbl {
  const { t } = useTranslation();
  return (key, fallback) => String(t(key, { defaultValue: fallback }));
}

/** Compteur lisible : « 68 500 km », « 4 200 h moteur » ; « Sans compteur » pour un forfait. */
function compteurTexte(lbl: Lbl, type: string, value: string | null, typeLabel: string): string {
  const unite = lbl(`revueR2.logistique.unite.${type}`, typeLabel);
  if (type === "forfait") return unite;
  return `${formatNumber(Number(value ?? 0))} ${unite}`;
}

function EquipementCard({ eq, index }: { eq: EquipementParc; index: number }) {
  const { t } = useTranslation();
  const lbl = useLbl();
  // Statut porté par la colonne ; la carte montre l'identité, la catégorie, le compteur et la localisation.
  return (
    <BoardCard delay={Math.min(index * 0.03, 0.3)}>
      <div className="card-top">
        <span className="card-code">{eq.code}</span>
        {eq.is_global_rental ? (
          <span className="card-tags">
            <Badge tone="brand" title={t("logistique.globalRental")}>
              GR
            </Badge>
          </span>
        ) : null}
      </div>
      <div className="title">{eq.label}</div>
      <div className="meta">
        {[lbl(`revueR2.logistique.categorie.${eq.categorie}`, eq.categorie_label), eq.registration].filter(Boolean).join(" · ")}
      </div>
      <div className="card-foot">
        <span>{[eq.site, eq.proprietaire_code].filter(Boolean).join(" · ")}</span>
        <span className="amount">{compteurTexte(lbl, eq.compteur_type, eq.compteur_value, eq.compteur_type_label)}</span>
      </div>
    </BoardCard>
  );
}

type T = (key: string) => string;

function locationColumns(t: T, lbl: Lbl): Column<LocationGR>[] {
  return [
    { key: "code", header: t("logistique.col.code"), sortValue: (l) => l.code, render: (l) => <span className="cell-nowrap">{l.code}</span> },
    {
      key: "equip",
      header: t("logistique.col.equipement"),
      render: (l) => (
        <>
          <span className="cell-nowrap">{l.equipement_code}</span>
          {l.equipement_label ? <span className="cell-sub">{l.equipement_label}</span> : null}
        </>
      ),
    },
    { key: "partner", header: t("logistique.col.partenaire"), render: (l) => l.partenaire_name ?? "—" },
    { key: "period", header: t("logistique.col.periodicite"), render: (l) => <span className="cell-nowrap">{lbl(`revueR2.logistique.periodicite.${l.periodicite}`, l.periodicite_label)}</span> },
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
      sortValue: (l) => (l.montant_estime === null ? null : Number(l.montant_estime)),
      render: (l) => (
        <>
          {l.montant_estime === null ? t("logistique.masked") : formatMoney(l.montant_estime)}
          {l.imputation_618 && (
            <span className="cell-sub" title={t("tableaux.logistique.compte618")}>
              {t("premiumModules.compte618")}
            </span>
          )}
        </>
      ),
    },
    {
      key: "statut",
      header: t("logistique.col.statut"),
      render: (l) => (
        <Badge tone={l.statut === "active" ? "warn" : l.statut === "terminee" ? "ok" : "neutral"}>
          {lbl(`revueR2.logistique.statutLocation.${l.statut}`, l.statut_label)}
        </Badge>
      ),
    },
    actionsColumn<LocationGR>(t("listes.col.actions"), (l) => [
      ...(l.statut === "brouillon"
        ? [{ label: t("actions.demarrer"), path: `/api/logistique/locations/${l.id}/demarrer/`, prompt: { name: "lecture_initiale", label: t("logistique.act.compteurDepart") } }]
        : []),
      ...(l.statut === "brouillon" && !l.emis_le
        ? [{ label: t("logistique.act.emettre"), path: `/api/logistique/locations/${l.id}/emettre/`, tone: "ghost" as const }]
        : []),
      ...(l.statut === "active"
        ? [{ label: t("actions.cloturer"), path: `/api/logistique/locations/${l.id}/cloturer/`, prompt: { name: "lecture_finale", label: t("logistique.act.compteurFin") } }]
        : []),
    ]),
  ];
}

function demandeColumns(t: T, lbl: Lbl): Column<DemandeMobilisation>[] {
  return [
    { key: "code", header: t("logistique.col.code"), render: (d) => <span className="cell-nowrap">{d.code}</span> },
    { key: "label", header: t("logistique.col.besoin"), render: (d) => d.label },
    { key: "dept", header: t("logistique.col.departement"), render: (d) => d.departement || "—" },
    { key: "debut", header: t("logistique.debut"), sortValue: (d) => d.date_debut, render: (d) => formatDate(d.date_debut) },
    { key: "affaire", header: t("logistique.col.affaire"), render: (d) => d.affaire_code ?? "—" },
    {
      key: "statut",
      header: t("logistique.col.statut"),
      render: (d) => (
        <Badge tone={d.statut === "soumise" ? "warn" : d.statut === "brouillon" || d.statut === "annulee" ? "neutral" : "ok"}>
          {lbl(`revueR2.logistique.statutDemande.${d.statut}`, d.statut_label)}
        </Badge>
      ),
    },
    actionsColumn<DemandeMobilisation>(t("listes.col.actions"), (d) => [
      ...(d.statut === "brouillon"
        ? [{ label: t("logistique.act.soumettre"), path: `/api/logistique/demandes/${d.id}/soumettre/`, tone: "ghost" as const }]
        : []),
      ...(d.statut === "soumise" ? [{ label: t("logistique.act.traiter"), path: `/api/logistique/demandes/${d.id}/traiter/` }] : []),
    ]),
  ];
}

export function LogistiquePage() {
  const { t } = useTranslation();
  const lbl = useLbl();

  const [eqSearch, setEqSearch] = useState("");
  const [eqSite, setEqSite] = useState("");
  const byStatus = useQuery({
    queryKey: ["equipements", eqSearch, eqSite],
    queryFn: () => api.equipements(pagedQuery(1, 500, eqSearch, siteQuery(eqSite))),
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

  const statutLabel = (key: EquipementStatut) => t(`listes.logistique.statut.${key}`);

  return (
    <div className="listes-page">
      <PageHeader title={t("logistique.title")} subtitle={t("listes.sub.logistique")} />
      <SectionNav
        items={[
          { id: "log-parc", label: t("premiumVague2.sections.logistique.parc") },
          { id: "log-locations", label: t("premiumVague2.sections.logistique.locations") },
          { id: "log-suivi", label: t("premiumVague2.sections.logistique.suivi") },
          ...(demandes.count > 0 || demandes.search ? [{ id: "log-demandes", label: t("premiumVague2.sections.logistique.demandes") }] : []),
          { id: "log-parametres", label: t("premiumVague2.sections.logistique.parametres") },
        ]}
      />

      <div className="kpi-grid">
        <Kpi
          label={t("logistique.parc")}
          value={stats?.parc.total ?? Object.values(groups).reduce((n, g) => n + g.length, 0)}
          hint={stats ? t("listes.logistique.parcValue", { gr: formatNumber(stats.parc.global_rental), propre: formatNumber(stats.parc.propre) }) : undefined}
          icon={Truck}
          tone="brand"
          delay={0}
        />
        <Kpi
          label={t("listes.logistique.actifs")}
          value={stats ? stats.locations.actives : "—"}
          hint={stats?.locations.total_montant_estime !== undefined ? formatMoney(stats.locations.total_montant_estime) : t("logistique.masked")}
          icon={MapPin}
          tone="accent"
          delay={0.05}
        />
        <Kpi label={t("logistique.demandes")} value={demandes.count} icon={ClipboardList} tone="warn" delay={0.1} />
      </div>

      <section id="log-parc" className="listes-block">
        <div className="list-toolbar">
          <SearchField value={eqSearch} onChange={setEqSearch} placeholder={t("logistique.searchEquipements")} />
          <SiteFilter value={eqSite} onChange={setEqSite} />
        </div>
        <Board label={t("listes.boardLabel.logistique")}>
          {BOARD_ORDER.map((st, ci) => (
            <BoardColumn key={st} title={statutLabel(st)} count={groups[st].length} tone={STATUS_BADGE[st]} delay={ci * 0.04} limit={20}>
              {groups[st].map((eq, i) => (
                <EquipementCard key={eq.id} eq={eq} index={i} />
              ))}
            </BoardColumn>
          ))}
        </Board>
      </section>

      <div id="log-locations" className="page-section">
      {(locations.count > 0 || locations.search) && (
        <SectionCard title={`${t("listes.logistique.locationsTitle")} · ${locations.count}`}>
          <PagedDataTable list={locations} columns={locationColumns(t, lbl)} caption={t("listes.logistique.locationsTitle")} searchPlaceholder={t("logistique.searchLocations")} />
        </SectionCard>
      )}
      <GrAffairesSection />
      <TarifsGrSection />
      </div>
      <div id="log-suivi" className="page-section">
        <EcartsM4Section />
      </div>
      {(demandes.count > 0 || demandes.search) && (
        <SectionCard id="log-demandes" title={`${t("logistique.demandes")} · ${demandes.count}`}>
          <PagedDataTable list={demandes} columns={demandeColumns(t, lbl)} caption={t("logistique.demandes")} searchPlaceholder={t("logistique.searchDemandes")} />
        </SectionCard>
      )}
      <div id="log-parametres" className="page-section">
        <ParametresLogistiqueSection />
      </div>
    </div>
  );
}
