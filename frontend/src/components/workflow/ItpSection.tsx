import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useTranslation } from "react-i18next";

import { api } from "../../api/client";
import { formatDateTime } from "../../lib/format";
import { describeError } from "../../lib/offlineQueue";
import type { ControleQualite, Paginated, PointInspection } from "../../types";
import { ActionBar, Badge, ProgressBar, SectionCard } from "../ui";

const TONE: Record<PointInspection["statut"], "ok" | "warn" | "err"> = {
  leve: "ok",
  en_attente: "warn",
  non_conforme: "err",
};

function AddPoint({ itp, next }: { itp: ControleQualite; next: number }) {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const [description, setDescription] = useState("");
  const [type, setType] = useState<"arret" | "observation">("arret");
  const [error, setError] = useState<string | null>(null);
  const add = useMutation({
    mutationFn: () =>
      api.post("/api/qualite/points-inspection/", { controle: itp.id, ordre: next, description, type_point: type }),
    onSuccess: () => {
      setDescription("");
      setError(null);
      void qc.invalidateQueries();
    },
    onError: (e) => setError(describeError(e)),
  });
  if (itp.statut === "valide" || itp.statut === "annule") return null;
  return (
    <form
      className="itp-add"
      onSubmit={(e) => {
        e.preventDefault();
        add.mutate();
      }}
    >
      <input required aria-label={t("itp.pointPlaceholder")} value={description} onChange={(e) => setDescription(e.target.value)} placeholder={t("itp.pointPlaceholder")} />
      <select aria-label={t("itp.type")} value={type} onChange={(e) => setType(e.target.value as typeof type)}>
        <option value="arret">{t("itp.arret")}</option>
        <option value="observation">{t("itp.observation")}</option>
      </select>
      <button className="btn ghost" type="submit" disabled={add.isPending}>
        {t("itp.add")}
      </button>
      {error && (
        <p className="action-error" role="alert">
          {error}
        </p>
      )}
    </form>
  );
}

/** Plans d'inspection et d'essais : points d'arrêt / d'observation, levée tracée et ordonnée (CL-OM-07). */
export function ItpSection() {
  const { t, i18n } = useTranslation();
  const itps = useQuery({
    queryKey: ["itps"],
    queryFn: () => api.get<Paginated<ControleQualite>>("/api/qualite/controles/?type=itp").then((p) => p.results),
  });
  const rows = itps.data ?? [];
  if (itps.isError || rows.length === 0) return null;

  return (
    <SectionCard title={t("itp.title")}>
      <div className="itp-list">
        {rows.map((itp) => {
          const points = itp.points ?? [];
          const levés = points.filter((p) => p.statut === "leve").length;
          return (
            <article className="card itp" key={itp.id}>
              <header className="itp-head">
                <strong>
                  {itp.code} · {itp.point_controle}
                </strong>
                <Badge tone={itp.statut === "valide" ? "ok" : "warn"}>{itp.statut_label}</Badge>
              </header>
              <ProgressBar value={levés} max={Math.max(points.length, 1)} tone={levés === points.length && points.length > 0 ? "ok" : "brand"} />
              <span className="muted">
                {t("itp.progress", { done: levés, total: points.length, restants: itp.points_arret_restants ?? 0 })}
              </span>
              <ol className="itp-points">
                {points.map((p) => (
                  <li key={p.id} className={`itp-point ${p.statut}`}>
                    <span className="itp-num">{p.ordre}</span>
                    <span className="itp-desc">
                      {p.description}
                      <span className="muted">
                        {" "}
                        · {p.type_label}
                        {p.leve_le ? ` · ${p.leve_par_name ?? ""} ${formatDateTime(p.leve_le, i18n.language)}` : ""}
                        {p.commentaire ? ` · ${p.commentaire}` : ""}
                      </span>
                    </span>
                    <Badge tone={TONE[p.statut]}>{p.statut_label}</Badge>
                    {p.statut === "en_attente" && (
                      <ActionBar
                        actions={[
                          { label: t("itp.lever"), path: `/api/qualite/points-inspection/${p.id}/lever/`, body: { resultat: "conforme" } },
                          {
                            label: t("itp.nonConforme"),
                            path: `/api/qualite/points-inspection/${p.id}/lever/`,
                            body: { resultat: "non_conforme" },
                            tone: "danger",
                            confirm: t("itp.confirmNc"),
                          },
                        ]}
                      />
                    )}
                  </li>
                ))}
              </ol>
              <AddPoint itp={itp} next={points.length + 1} />
            </article>
          );
        })}
      </div>
    </SectionCard>
  );
}
