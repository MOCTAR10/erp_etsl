import { useQuery } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";

import { api } from "../api/client";

export function CircuitsPage() {
  const { t } = useTranslation();
  const { data, isLoading, isError, refetch } = useQuery({
    queryKey: ["circuits"],
    queryFn: api.circuits,
  });

  if (isLoading) return <p className="muted">{t("common.loading")}</p>;
  if (isError || !data)
    return (
      <p>
        {t("common.error")}{" "}
        <button className="btn ghost" onClick={() => void refetch()}>
          {t("common.retry")}
        </button>
      </p>
    );

  return (
    <>
      <h2>{t("circuits.title")}</h2>
      {data.map((circuit) => (
        <div className="card" key={circuit.id} style={{ marginBottom: "1rem" }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
            <h3 style={{ fontSize: 16, margin: 0 }}>
              {circuit.label} <span className="muted" style={{ fontWeight: 500 }}>({circuit.code})</span>
            </h3>
            <span className={`badge ${circuit.is_active ? "ok" : "muted"}`}>
              {circuit.is_active ? t("circuits.active") : t("circuits.inactive")}
            </span>
          </div>
          <table className="table mt-1">
            <thead>
              <tr>
                <th>#</th>
                <th>{t("circuits.steps")}</th>
                <th>{t("circuits.actor")}</th>
                <th>{t("circuits.days")}</th>
              </tr>
            </thead>
            <tbody>
              {circuit.steps.map((step) => (
                <tr key={step.id}>
                  <td className="muted">{step.order}</td>
                  <td>{step.name}</td>
                  <td>
                    <span className="badge brand">{step.actor_role_label}</span>
                  </td>
                  <td className="muted">{step.max_days} j</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ))}
    </>
  );
}