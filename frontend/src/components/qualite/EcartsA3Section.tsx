import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { useTranslation } from "react-i18next";

import { api } from "../../api/client";
import { formatDate, formatMoney, formatNumber } from "../../lib/format";
import { ActionBar, Badge, QuickForm, SectionCard } from "../ui";

interface Ref {
  id: string;
  code: string;
  label?: string;
  reference?: string;
  type?: string;
  statut?: string;
  nom?: string;
  display_name?: string;
  numero_coulee?: string;
  article_code?: string;
  description?: string;
}
interface Certificat {
  id: string;
  code: string;
  type_label: string;
  numero_certificat: string;
  conforme: boolean;
  valide: boolean;
}
interface Joint {
  id: string;
  code: string;
  ordre_code: string;
  repere: string;
  soudeur_nom: string;
  wps_code: string | null;
  numero_coulee: string;
  lot_code: string | null;
  certificats: Certificat[];
  date_soudage: string;
}
interface Trace {
  lot: { code: string; numero_lot: string; numero_coulee: string; article: string } | null;
  certificats: Certificat[];
  mouvements: { code: string; date: string; type_label: string; quantite: string; reference: string; ordre: string | null }[];
}
interface Cnq {
  id: string;
  code: string;
  nc_code: string;
  nature: string;
  nature_label: string;
  date: string;
  heures: string;
  quantite: string;
  montant: string | null;
  statut: string;
  statut_label: string;
  ecriture_numero: string | null;
  description: string;
}
interface Synthese {
  par_nature: { nature: string; label: string; montant: string | null }[];
  total: string | null;
  has_amount_access: boolean;
}

const fcfa = (v: string | null) => (v === null ? "—" : formatMoney(Number(v)));
function useListe<T>(key: string, path: string): T[] {
  return useQuery({ queryKey: ["a3", key], queryFn: () => api.listAll<T>(path), retry: 0 }).data ?? [];
}

const NATURES = ["reprise", "reparation", "rebut", "autre"];

/** Lot a3 côté qualité : traçabilité lot / coulée / certificat 3.1 jusqu'au joint (M5 → M6) et coût de non-qualité (M6 → M10). */
export function EcartsA3Section() {
  const { t } = useTranslation();
  const joints = useListe<Joint>("joints", "/api/qualite/joints/");
  const ordres = useListe<Ref>("ordres", "/api/operations/ordres/");
  const soudeurs = useListe<Ref>("soudeurs", "/api/qualite/soudeurs/");
  const wps = useListe<Ref>("wps", "/api/qualite/wps/").filter((w) => w.type === "wps" && w.statut === "valide");
  const lots =
    useQuery({
      queryKey: ["a3", "lots-consommes"],
      queryFn: () => api.get<(Ref & { ordre_code: string })[]>("/api/qualite/joints/lots-consommes/"),
      retry: 0,
    }).data ?? [];
  const ncs = useListe<Ref>("ncs", "/api/qualite/non-conformites/");
  const couts = useListe<Cnq>("cnq", "/api/qualite/couts-non-qualite/");
  const synthese = useQuery({
    queryKey: ["a3", "cnq-synthese"],
    queryFn: () => api.get<Synthese>("/api/qualite/couts-non-qualite/synthese/"),
    retry: 0,
  }).data;
  const [ouvert, setOuvert] = useState<string | null>(null);
  const trace = useQuery({
    queryKey: ["a3", "trace", ouvert],
    queryFn: () => api.get<Trace>(`/api/qualite/joints/${ouvert}/tracabilite/`),
    enabled: Boolean(ouvert),
    retry: 0,
  }).data;

  return (
    <>
      <SectionCard title={t("ecarts_a3.joints.title")} subtitle={t("ecarts_a3.joints.hint")}>
        <div className="action-bar-buttons">
          <QuickForm
            title={t("ecarts_a3.joints.ajouter")}
            endpoint="/api/qualite/joints/"
            fields={[
              { name: "ordre", label: t("ecarts_a3.joints.ordre"), type: "select", required: true,
                options: ordres.map((o) => ({ value: o.id, label: `${o.code} · ${o.label ?? ""}` })) },
              { name: "repere", label: t("ecarts_a3.joints.repere"), required: true },
              { name: "soudeur", label: t("ecarts_a3.joints.soudeur"), type: "select", required: true,
                options: soudeurs.map((s) => ({ value: s.id, label: `${s.code} · ${s.display_name ?? s.nom ?? ""}` })) },
              { name: "wps", label: t("ecarts_a3.joints.wps"), type: "select", required: true,
                options: wps.map((w) => ({ value: w.id, label: `${w.code} · ${w.reference ?? ""}` })) },
              { name: "lot", label: t("ecarts_a3.joints.lot"), type: "select",
                options: lots.map((l) => ({
                  value: l.id,
                  label: `${l.ordre_code} · ${l.code} · ${l.article_code ?? ""} · ${l.numero_coulee || "—"}`,
                })) },
              { name: "numero_coulee", label: t("ecarts_a3.joints.coulee") },
            ]}
          />
        </div>
        <table className="table" data-testid="joints-tracabilite">
          <thead>
            <tr>
              <th>{t("ecarts_a3.joints.repere")}</th>
              <th>{t("ecarts_a3.joints.ordre")}</th>
              <th>{t("ecarts_a3.joints.soudeur")}</th>
              <th>{t("ecarts_a3.joints.lot")}</th>
              <th>{t("ecarts_a3.joints.coulee")}</th>
              <th>{t("ecarts_a3.joints.certificat")}</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {joints.map((j) => (
              <tr key={j.id}>
                <td>
                  {j.code} · {j.repere}
                </td>
                <td>{j.ordre_code}</td>
                <td>{j.soudeur_nom}</td>
                <td>{j.lot_code ?? "—"}</td>
                <td>{j.numero_coulee || "—"}</td>
                <td>
                  {j.certificats.length === 0
                    ? t("ecarts_a3.joints.aucunCert")
                    : j.certificats.map((c) => (
                        <Badge key={c.id} tone={c.valide && c.conforme ? "ok" : "warn"}>
                          {c.type_label} {c.numero_certificat}
                        </Badge>
                      ))}
                </td>
                <td>
                  <button type="button" className="btn ghost" onClick={() => setOuvert(ouvert === j.id ? null : j.id)}>
                    {t("ecarts_a3.joints.tracer")}
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {ouvert && trace && (
          <div className="card" data-testid="trace-joint">
            <strong>
              {trace.lot
                ? t("ecarts_a3.joints.chaine", { lot: trace.lot.code, coulee: trace.lot.numero_coulee || "—", article: trace.lot.article })
                : t("ecarts_a3.joints.sansLot")}
            </strong>
            <ul>
              {trace.mouvements.map((m) => (
                <li key={m.code}>
                  {formatDate(m.date)} · {m.type_label} · {formatNumber(Number(m.quantite))} · {m.reference || m.ordre || "—"}
                </li>
              ))}
            </ul>
          </div>
        )}
      </SectionCard>

      <SectionCard title={t("ecarts_a3.cnq.title")} subtitle={t("ecarts_a3.cnq.hint")}>
        <p>
          <Badge tone="warn">{t("ecarts_a3.provisoire")}</Badge>
        </p>
        <div className="action-bar-buttons">
          <QuickForm
            title={t("ecarts_a3.cnq.saisir")}
            endpoint="/api/qualite/couts-non-qualite/"
            fields={[
              { name: "non_conformite", label: t("ecarts_a3.cnq.nc"), type: "select", required: true,
                options: ncs.map((n) => ({ value: n.id, label: `${n.code} · ${(n.description ?? "").slice(0, 60)}` })) },
              { name: "nature", label: t("ecarts_a3.cnq.nature"), type: "select", required: true, defaultValue: "reprise",
                options: NATURES.map((v) => ({ value: v, label: t(`ecarts_a3.cnq.natures.${v}`) })) },
              { name: "heures", label: t("ecarts_a3.cnq.heures"), type: "number", min: 0, step: "0.5" },
              { name: "quantite", label: t("ecarts_a3.cnq.quantite"), type: "number", min: 0, step: "0.001" },
              { name: "frais_externes", label: t("ecarts_a3.cnq.frais"), type: "number", min: 0 },
              { name: "description", label: t("ecarts_a3.cnq.description") },
            ]}
          />
        </div>
        {synthese && (
          <p className="muted" data-testid="cnq-synthese">
            {synthese.par_nature.map((n) => `${n.label} : ${fcfa(n.montant)}`).join(" · ")} — {t("ecarts_a3.cnq.total")} :{" "}
            {fcfa(synthese.total)}
          </p>
        )}
        <table className="table" data-testid="couts-non-qualite">
          <thead>
            <tr>
              <th>{t("ecarts_a3.cnq.cols.code")}</th>
              <th>{t("ecarts_a3.cnq.nc")}</th>
              <th>{t("ecarts_a3.cnq.nature")}</th>
              <th>{t("ecarts_a3.cnq.cols.date")}</th>
              <th>{t("ecarts_a3.cnq.cols.montant")}</th>
              <th>{t("ecarts_a3.cnq.cols.statut")}</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {couts.map((c) => (
              <tr key={c.id}>
                <td>{c.code}</td>
                <td>{c.nc_code}</td>
                <td>{c.nature_label}</td>
                <td>{formatDate(c.date)}</td>
                <td>{fcfa(c.montant)}</td>
                <td>
                  <Badge tone={c.statut === "comptabilise" ? "ok" : "warn"}>{c.statut_label}</Badge>
                  {c.ecriture_numero ? ` ${c.ecriture_numero}` : ""}
                </td>
                <td>
                  {c.statut === "saisi" && (
                    <ActionBar
                      actions={[
                        {
                          label: t("ecarts_a3.cnq.comptabiliser"),
                          path: `/api/qualite/couts-non-qualite/${c.id}/comptabiliser/`,
                          tone: "primary",
                          confirm: t("ecarts_a3.cnq.confirm"),
                        },
                      ]}
                    />
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </SectionCard>
    </>
  );
}
