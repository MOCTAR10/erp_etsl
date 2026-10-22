import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useTranslation } from "react-i18next";

import { api } from "../../api/client";
import { formatNumber } from "../../lib/format";
import { describeError } from "../../lib/offlineQueue";
import { Badge, SectionCard } from "../ui";

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

const fcfa = (v: string | null) => (v === null ? "—" : formatNumber(Number(v)));
const MOIS = Array.from({ length: 12 }, (_, i) => i);

/** Écarts M8 (lot m5m8) : centre analytique par machine, écriture du coût à la clôture d'OT, coûts annuels → M11. */
export function CoutsMaintenanceSection() {
  const { t } = useTranslation();
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
              <button type="button" className="btn ghost" onClick={() => void exporter("xlsx")}>{t("ecarts_m5m8.exportXlsx")}</button>
              <button type="button" className="btn ghost" onClick={() => void exporter("pdf")}>{t("ecarts_m5m8.exportPdf")}</button>
            </>
          )}
        </div>
        {couts.isError && <p className="muted">{t("ecarts_m5m8.maint.reserve")}</p>}
        {c && (
          <>
            <p>
              {t("ecarts_m5m8.maint.total")} : <strong>{fcfa(c.total)} {c.devise}</strong> · 618 GR : {fcfa(c.totaux.gr_618)} · {t("ecarts_m5m8.maint.horsGr")} : {fcfa(c.totaux.hors_gr)}{" "}
              {c.provisoire && <Badge tone="warn">{t("ecarts_m5m8.provisoire")}</Badge>}
            </p>
            <div className="table-wrap">
              <table className="table" data-testid="couts-centres">
                <thead>
                  <tr>
                    <th>{t("ecarts_m5m8.maint.centre")}</th>
                    {MOIS.map((m) => (
                      <th key={m} className="num">{m + 1}</th>
                    ))}
                    <th className="num">{t("ecarts_m5m8.maint.totalCol")}</th>
                  </tr>
                </thead>
                <tbody>
                  {c.centres.map((r) => (
                    <tr key={r.centre}>
                      <td title={r.libelle}>{r.centre} ({r.nb_ot} OT)</td>
                      {MOIS.map((m) => (
                        <td key={m} className="num">{fcfa(r.mois[m])}</td>
                      ))}
                      <td className="num">{fcfa(r.total)}</td>
                    </tr>
                  ))}
                  <tr>
                    <th>{t("ecarts_m5m8.maint.cumul")}</th>
                    {MOIS.map((m) => (
                      <td key={m} className="num">{fcfa(c.cumul[m])}</td>
                    ))}
                    <td className="num">{fcfa(c.total)}</td>
                  </tr>
                </tbody>
              </table>
            </div>
            <table className="table" data-testid="couts-machines">
              <thead>
                <tr>
                  <th>{t("ecarts_m5m8.maint.machine")}</th>
                  <th>{t("ecarts_m5m8.maint.centre")}</th>
                  <th>{t("ecarts_m5m8.maint.compte")}</th>
                  <th className="num">OT</th>
                  <th className="num">{t("ecarts_m5m8.maint.mo")}</th>
                  <th className="num">{t("ecarts_m5m8.maint.pieces")}</th>
                  <th className="num">{t("ecarts_m5m8.maint.totalCol")}</th>
                </tr>
              </thead>
              <tbody>
                {c.machines.map((r) => (
                  <tr key={r.actif}>
                    <td>{r.actif} · {r.designation}</td>
                    <td>{r.centre}</td>
                    <td>{r.compte}</td>
                    <td className="num">{r.nb_ot}</td>
                    <td className="num">{fcfa(r.main_oeuvre)}</td>
                    <td className="num">{fcfa(r.pieces)}</td>
                    <td className="num">{fcfa(r.total)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </>
        )}

        <h4>{t("ecarts_m5m8.maint.ecritures")}</h4>
        {clotures.length === 0 ? (
          <p className="muted">{t("ecarts_m5m8.maint.aucuneCloture")}</p>
        ) : (
          <table className="table" data-testid="ecritures-ot">
            <thead>
              <tr>
                <th>OT</th>
                <th>{t("ecarts_m5m8.maint.machine")}</th>
                <th>{t("ecarts_m5m8.maint.centre")}</th>
                <th className="num">{t("ecarts_m5m8.maint.totalCol")}</th>
                <th>{t("ecarts_m5m8.maint.ecriture")}</th>
              </tr>
            </thead>
            <tbody>
              {clotures.map((o) => (
                <tr key={o.id}>
                  <td>{o.code}</td>
                  <td>{o.actif_code}</td>
                  <td>{o.centre_code}</td>
                  <td className="num">{fcfa(o.cout_total)}</td>
                  <td>{o.ecriture_numero ? <Badge tone="ok">{o.ecriture_numero}</Badge> : <span className="muted">{o.motif_ecriture || "—"}</span>}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}

        <h4>{t("ecarts_m5m8.maint.affectation")}</h4>
        <table className="table" data-testid="centres-machines">
          <tbody>
            {actifs.map((a) => (
              <tr key={a.id}>
                <td>{a.code} · {a.designation}</td>
                <td>
                  <select
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
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </SectionCard>
  );
}
