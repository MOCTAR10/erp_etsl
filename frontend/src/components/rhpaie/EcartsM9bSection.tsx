import { useQuery } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";

import { api } from "../../api/client";
import { formatDate, formatMoney, formatNumber, formatPercent } from "../../lib/format";
import { SectionActions } from "../sections/SectionActions";
import { Badge, DataTable, QuickForm, SectionCard } from "../ui";
import type { Column } from "../ui";

interface Account {
  id: string;
  code: string;
  label: string;
}
interface ComptePaie {
  id: string;
  role: string;
  role_label: string;
  organisme: string;
  compte_code: string;
  compte_label: string;
}
interface Provision {
  id: string;
  periode: string;
  base_brut: string;
  taux: string;
  taux_provisoire: boolean;
  montant: string;
  move_number: string | null;
}
interface CoutOf {
  ordre: string;
  ordre_code: string;
  affaire: string | null;
  heures: string;
  cout: string;
  heures_non_valorisees: string;
  heures_prevues: string | null;
  depassement: boolean;
}

const ROLES = ["brut", "patronal", "net", "organismes", "impot", "autres_retenues", "provision_charge", "provision_dette"];
type LigneCoutOf = CoutOf & { id: string };

/** Heures exactes (décimales significatives conservées). */
const heures = (v: string) => {
  const dec = (String(Number(v)).split(".")[1] ?? "").length;
  return formatNumber(v, { decimals: Math.min(dec, 2) });
};

/** Coût de main-d'œuvre chargé des pointages transférés en paie, par OF (aval opérations / contrôle de gestion). Masqué hors cercle des montants. */
export function CoutMainOeuvreSection() {
  const { t } = useTranslation();
  const lignes =
    useQuery({ queryKey: ["m9b", "cout-mo"], queryFn: () => api.get<CoutOf[]>("/api/rh-paie/cout-main-oeuvre/"), retry: 0 }).data ?? null;
  if (lignes === null) return null;
  const rows: LigneCoutOf[] = lignes.map((l) => ({ ...l, id: l.ordre }));
  const columns: Column<LigneCoutOf>[] = [
    // Largeurs en % : l'affaire prend la place, heures et coût restent groupés à droite (plus de colonnes étirées).
    { key: "of", header: t("m9b.cout.of"), width: "18%", sortValue: (l) => l.ordre_code, render: (l) => <span className="cell-nowrap">{l.ordre_code}</span> },
    { key: "affaire", header: t("m9b.cout.affaire"), width: "42%", render: (l) => l.affaire ?? "—" },
    {
      key: "heures",
      header: t("m9b.cout.heures"),
      num: true,
      width: "22%",
      sortValue: (l) => Number(l.heures),
      render: (l) => (
        <>
          <span className="cell-nowrap">
            {heures(l.heures)} h{l.heures_prevues ? ` / ${heures(l.heures_prevues)} h` : ""}
          </span>{" "}
          {Number(l.heures_non_valorisees) > 0 && <Badge tone="warn">{t("m9b.cout.nonValorisees", { n: heures(l.heures_non_valorisees) })}</Badge>}
          {l.depassement && <Badge tone="err">{t("m9b.cout.depassement")}</Badge>}
        </>
      ),
    },
    { key: "cout", header: t("m9b.cout.cout"), num: true, width: "18%", sortValue: (l) => Number(l.cout), render: (l) => <span className="cell-nowrap">{formatMoney(l.cout)}</span> },
  ];
  return (
    <SectionCard title={t("m9b.cout.title")}>
      <div data-testid="cout-main-oeuvre">
        <DataTable columns={columns} rows={rows} caption={t("m9b.cout.title")} density="compact" />
      </div>
      <p className="card-sub">{t("m9b.cout.note")}</p>
    </SectionCard>
  );
}

/** Écarts M9-B : comptes de paie par organisme, provision des congés payés, coût de main-d'œuvre chargé. */
export function EcartsM9bSection() {
  const { t } = useTranslation();
  const comptes = useQuery({ queryKey: ["m9b", "comptes"], queryFn: () => api.listAll<ComptePaie>("/api/rh-paie/comptes-paie/"), retry: 0 }).data ?? [];
  const provisions = useQuery({ queryKey: ["m9b", "provisions"], queryFn: () => api.listAll<Provision>("/api/rh-paie/provisions-conges/"), retry: 0 }).data ?? [];
  const plan = useQuery({ queryKey: ["m9b", "plan"], queryFn: () => api.listAll<Account>("/api/referentiels/accounts/"), retry: 0 }).data ?? [];
  const planOpts = plan.map((a) => ({ value: a.id, label: `${a.code} · ${a.label}` }));
  const colComptes: Column<ComptePaie>[] = [
    { key: "role", header: t("m9b.comptes.role"), sortValue: (c) => c.role_label, render: (c) => c.role_label },
    { key: "organisme", header: t("m9b.comptes.organisme"), render: (c) => c.organisme || "—" },
    { key: "compte", header: t("m9b.comptes.compte"), sortValue: (c) => c.compte_code, render: (c) => `${c.compte_code} · ${c.compte_label}` },
  ];
  const colProvisions: Column<Provision>[] = [
    { key: "periode", header: t("m9b.provision.periode"), sortValue: (p) => p.periode, render: (p) => formatDate(p.periode) },
    { key: "base", header: t("m9b.provision.base"), num: true, render: (p) => formatMoney(p.base_brut) },
    {
      key: "taux",
      header: t("m9b.provision.taux"),
      num: true,
      render: (p) => (
        <>
          {p.taux_provisoire && <Badge tone="warn">{t("m9a.provisoire")}</Badge>} {formatPercent(p.taux, { decimals: 2 })}
        </>
      ),
    },
    { key: "montant", header: t("m9b.provision.montant"), num: true, sortValue: (p) => Number(p.montant), render: (p) => formatMoney(p.montant) },
    { key: "ecriture", header: t("m9b.provision.ecriture"), render: (p) => p.move_number ?? "—" },
  ];

  return (
    <>
      <SectionCard
        title={t("m9b.comptes.title")}
        actions={
          <SectionActions>
            <QuickForm
              title={t("m9b.comptes.ajouter")}
              endpoint="/api/rh-paie/comptes-paie/"
              fields={[
                { name: "role", label: t("m9b.comptes.role"), type: "select", required: true, defaultValue: "organismes", options: ROLES.map((r) => ({ value: r, label: t(`m9b.roles.${r}`) })) },
                { name: "organisme", label: t("m9b.comptes.organisme") },
                { name: "compte", label: t("m9b.comptes.compte"), type: "select", required: true, options: planOpts },
              ]}
            />
          </SectionActions>
        }
      >
        <div data-testid="comptes-paie">
          <DataTable columns={colComptes} rows={comptes} caption={t("m9b.comptes.title")} />
        </div>
        <p className="muted">{t("m9b.comptes.note")}</p>
      </SectionCard>

      <SectionCard
        title={t("m9b.provision.title")}
        actions={
          <SectionActions>
            <QuickForm
              title={t("m9b.provision.passer")}
              endpoint="/api/rh-paie/provisions-conges/"
              fields={[{ name: "periode", label: t("m9b.provision.periode"), type: "date", required: true }]}
            />
          </SectionActions>
        }
      >
        <div data-testid="provisions-conges">
          <DataTable columns={colProvisions} rows={provisions} caption={t("m9b.provision.title")} />
        </div>
      </SectionCard>

      <CoutMainOeuvreSection />
    </>
  );
}
