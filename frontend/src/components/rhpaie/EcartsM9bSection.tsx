import { useQuery } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";

import { api } from "../../api/client";
import { formatDate, formatNumber } from "../../lib/format";
import { Badge, QuickForm, SectionCard } from "../ui";

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
const fcfa = (v: string) => `${formatNumber(Number(v))} F`;

/** Coût de main-d'œuvre chargé des pointages transférés en paie, par OF (aval M3 / M11). Masqué hors cercle des montants. */
export function CoutMainOeuvreSection() {
  const { t } = useTranslation();
  const lignes =
    useQuery({ queryKey: ["m9b", "cout-mo"], queryFn: () => api.get<CoutOf[]>("/api/rh-paie/cout-main-oeuvre/"), retry: 0 }).data ?? null;
  if (lignes === null) return null;
  return (
    <SectionCard title={t("m9b.cout.title")}>
      <table className="table" data-testid="cout-main-oeuvre">
        <thead>
          <tr>
            <th>{t("m9b.cout.of")}</th>
            <th>{t("m9b.cout.affaire")}</th>
            <th>{t("m9b.cout.heures")}</th>
            <th>{t("m9b.cout.cout")}</th>
          </tr>
        </thead>
        <tbody>
          {lignes.map((l) => (
            <tr key={l.ordre}>
              <td>{l.ordre_code}</td>
              <td>{l.affaire ?? "—"}</td>
              <td>
                {formatNumber(Number(l.heures))} h{l.heures_prevues ? ` / ${formatNumber(Number(l.heures_prevues))} h` : ""}
                {Number(l.heures_non_valorisees) > 0 && <Badge tone="warn">{t("m9b.cout.nonValorisees", { n: l.heures_non_valorisees })}</Badge>}
                {l.depassement && <Badge tone="err">{t("m9b.cout.depassement")}</Badge>}
              </td>
              <td>{fcfa(l.cout)}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <p className="muted">{t("m9b.cout.note")}</p>
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

  return (
    <>
      <SectionCard title={t("m9b.comptes.title")}>
        <div className="action-bar-buttons">
          <QuickForm
            title={t("m9b.comptes.ajouter")}
            endpoint="/api/rh-paie/comptes-paie/"
            fields={[
              { name: "role", label: t("m9b.comptes.role"), type: "select", required: true, defaultValue: "organismes", options: ROLES.map((r) => ({ value: r, label: t(`m9b.roles.${r}`) })) },
              { name: "organisme", label: t("m9b.comptes.organisme") },
              { name: "compte", label: t("m9b.comptes.compte"), type: "select", required: true, options: planOpts },
            ]}
          />
          <QuickForm
            title={t("m9b.provision.passer")}
            endpoint="/api/rh-paie/provisions-conges/"
            fields={[{ name: "periode", label: t("m9b.provision.periode"), type: "date", required: true }]}
          />
        </div>
        <table className="table" data-testid="comptes-paie">
          <thead>
            <tr>
              <th>{t("m9b.comptes.role")}</th>
              <th>{t("m9b.comptes.organisme")}</th>
              <th>{t("m9b.comptes.compte")}</th>
            </tr>
          </thead>
          <tbody>
            {comptes.map((c) => (
              <tr key={c.id}>
                <td>{c.role_label}</td>
                <td>{c.organisme || "—"}</td>
                <td>
                  {c.compte_code} · {c.compte_label}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        <p className="muted">{t("m9b.comptes.note")}</p>
      </SectionCard>

      <SectionCard title={t("m9b.provision.title")}>
        <table className="table" data-testid="provisions-conges">
          <thead>
            <tr>
              <th>{t("m9b.provision.periode")}</th>
              <th>{t("m9b.provision.base")}</th>
              <th>{t("m9b.provision.taux")}</th>
              <th>{t("m9b.provision.montant")}</th>
              <th>{t("m9b.provision.ecriture")}</th>
            </tr>
          </thead>
          <tbody>
            {provisions.map((p) => (
              <tr key={p.id}>
                <td>{formatDate(p.periode)}</td>
                <td>{fcfa(p.base_brut)}</td>
                <td>
                  {formatNumber(Number(p.taux))} % {p.taux_provisoire && <Badge tone="warn">{t("m9a.provisoire")}</Badge>}
                </td>
                <td>{fcfa(p.montant)}</td>
                <td>{p.move_number ?? "—"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </SectionCard>

      <CoutMainOeuvreSection />
    </>
  );
}
