import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { useTranslation } from "react-i18next";

import { api } from "../../api/client";
import { formatDate } from "../../lib/format";
import { Badge, QuickForm, SectionCard } from "../ui";

interface Organisme {
  id: string;
  nom: string;
  numero_agrement: string;
  autorite: string;
  methodes: string;
  date_fin_validite: string;
  actif: boolean;
  valide: boolean;
  nb_controles: number;
}
interface Wps {
  id: string;
  code: string;
  type: string;
  statut: string;
  procede: string;
}
interface WpsRequis {
  id: string;
  contract: string | null;
  contract_code: string | null;
  profile: string;
  wps: string;
  wps_code: string;
  wps_statut: string;
  libelle: string;
}
interface Ordre {
  id: string;
  code: string;
  label: string;
  affaire: string | null;
  affaire_code: string | null;
}
interface Contrat {
  id: string;
  code: string;
}
interface Conformite {
  affaire_code: string;
  conforme: boolean;
  requis: { wps: string; wps_code: string; statut: string; valide: boolean; origine: string; libelle: string }[];
}

const METHODES = ["RT", "UT", "PT", "MT"];
const PROFILS = ["marche_travaux", "maintenance"];

const useListe = <T,>(key: string, path: string) =>
  useQuery({ queryKey: ["ecarts-m6m7", key], queryFn: () => api.listAll<T>(path), retry: 0 }).data ?? [];

/** Écarts M6 : référentiel des organismes agréés (M6.1-09) et WPS requis par profil contractuel M1.3. */
export function EcartsM6m7Section() {
  const { t } = useTranslation();
  const organismes = useListe<Organisme>("organismes", "/api/qualite/organismes-agrees/");
  const wps = useListe<Wps>("wps", "/api/qualite/wps/");
  const requis = useListe<WpsRequis>("wps-requis", "/api/qualite/wps-requis/");
  const ordres = useListe<Ordre>("ordres", "/api/operations/ordres/");
  // Les contrats (module commercial) ne sont lisibles que par certains rôles : liste vide sinon.
  const contrats = useListe<Contrat>("contrats", "/api/commercial/contracts/");
  const [ordre, setOrdre] = useState("");
  const conformite = useQuery({
    queryKey: ["ecarts-m6m7", "conformite", ordre],
    queryFn: () => api.get<Conformite>(`/api/qualite/wps-requis/conformite/?ordre=${ordre}`),
    enabled: ordre !== "",
    retry: 0,
  });

  const wpsValides = wps.filter((w) => w.type === "wps" && w.statut === "valide").map((w) => ({ value: w.id, label: `${w.code} · ${w.procede.toUpperCase()}` }));
  const orgValides = organismes.filter((o) => o.valide).map((o) => ({ value: o.id, label: `${o.nom} · ${o.methodes || METHODES.join(",")}` }));
  const ordresAffaire = ordres.filter((o) => o.affaire);
  const m = "ecarts_m6m7";

  return (
    <>
      <SectionCard title={`${t(`${m}.org.title`)} · ${organismes.length}`}>
        <div data-testid="organismes-agrees">
          <div className="action-bar-buttons">
            <QuickForm
              title={t(`${m}.org.ajouter`)}
              endpoint="/api/qualite/organismes-agrees/"
              fields={[
                { name: "nom", label: t(`${m}.org.nom`), required: true },
                { name: "numero_agrement", label: t(`${m}.org.numero`), required: true },
                { name: "autorite", label: t(`${m}.org.autorite`) },
                { name: "methodes", label: t(`${m}.org.methodes`) },
                { name: "date_fin_validite", label: t(`${m}.org.validite`), type: "date", required: true },
              ]}
            />
            <QuickForm
              title={t(`${m}.org.cnd`)}
              endpoint="/api/qualite/controles/"
              transform={(v) => ({ ...v, type_controle: "cnd", organisme: "agrege" })}
              fields={[
                { name: "organisme_agree", label: t(`${m}.org.nom`), type: "select", required: true, options: orgValides },
                { name: "methode_cnd", label: t(`${m}.org.methode`), type: "select", required: true, defaultValue: "UT", options: METHODES.map((v) => ({ value: v, label: v })) },
                { name: "ordre", label: t(`${m}.org.of`), type: "select", options: ordres.map((o) => ({ value: o.id, label: `${o.code} · ${o.label}` })) },
                { name: "wps", label: "WPS", type: "select", options: wpsValides },
                { name: "point_controle", label: t(`${m}.org.point`) },
                { name: "date_controle", label: t(`${m}.org.date`), type: "date" },
              ]}
            />
          </div>
          <p className="muted">{t(`${m}.org.aide`)}</p>
          {organismes.length === 0 ? (
            <p className="muted">{t(`${m}.aucun`)}</p>
          ) : (
            <table className="table">
              <caption className="sr-only">{t(`${m}.org.title`)}</caption>
              <thead>
                <tr>
                  <th>{t(`${m}.org.nom`)}</th>
                  <th>{t(`${m}.org.numero`)}</th>
                  <th>{t(`${m}.org.methodes`)}</th>
                  <th>{t(`${m}.org.validite`)}</th>
                  <th>{t(`${m}.org.controles`)}</th>
                </tr>
              </thead>
              <tbody>
                {organismes.map((o) => (
                  <tr key={o.id}>
                    <td>
                      {o.nom}
                      {o.autorite ? <span className="muted"> · {o.autorite}</span> : null}
                    </td>
                    <td>{o.numero_agrement}</td>
                    <td>{o.methodes || METHODES.join(", ")}</td>
                    <td>
                      {formatDate(o.date_fin_validite)}{" "}
                      <Badge tone={o.valide ? "ok" : "err"}>{t(o.valide ? `${m}.org.valide` : `${m}.org.expire`)}</Badge>
                    </td>
                    <td className="num">{o.nb_controles}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      </SectionCard>

      <SectionCard title={`${t(`${m}.wps.title`)} · ${requis.length}`}>
        <div data-testid="wps-requis">
          <QuickForm
            title={t(`${m}.wps.ajouter`)}
            endpoint="/api/qualite/wps-requis/"
            fields={[
              { name: "profile", label: t(`${m}.wps.profil`), type: "select", options: PROFILS.map((p) => ({ value: p, label: t(`${m}.wps.profils.${p}`) })) },
              ...(contrats.length > 0 ? [{ name: "contract", label: t(`${m}.wps.contrat`), type: "select" as const, options: contrats.map((c) => ({ value: c.id, label: c.code })) }] : []),
              { name: "wps", label: "WPS", type: "select", required: true, options: wpsValides },
              { name: "libelle", label: t(`${m}.wps.libelle`) },
            ]}
          />
          <p className="muted">{t(`${m}.wps.aide`)}</p>
          {requis.length > 0 && (
            <table className="table">
              <caption className="sr-only">{t(`${m}.wps.title`)}</caption>
              <thead>
                <tr>
                  <th>{t(`${m}.wps.origine`)}</th>
                  <th>WPS</th>
                  <th>{t(`${m}.wps.statut`)}</th>
                  <th>{t(`${m}.wps.libelle`)}</th>
                </tr>
              </thead>
              <tbody>
                {requis.map((r) => (
                  <tr key={r.id}>
                    <td>{r.contract_code ?? t(`${m}.wps.profils.${r.profile}`)}</td>
                    <td>{r.wps_code}</td>
                    <td><Badge tone={r.wps_statut === "valide" ? "ok" : "err"}>{r.wps_statut}</Badge></td>
                    <td>{r.libelle || "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
          <label>
            {t(`${m}.wps.conformite`)}{" "}
            <select value={ordre} onChange={(e) => setOrdre(e.target.value)} aria-label={t(`${m}.wps.conformite`)}>
              <option value="">—</option>
              {ordresAffaire.map((o) => (
                <option key={o.id} value={o.id}>{`${o.code} · ${o.affaire_code ?? ""}`}</option>
              ))}
            </select>
          </label>
          {conformite.data && (
            <div role="status">
              {conformite.data.requis.length === 0 ? (
                <p className="muted">{t(`${m}.wps.libre`, { affaire: conformite.data.affaire_code })}</p>
              ) : (
                <p>
                  {conformite.data.affaire_code} :{" "}
                  <Badge tone={conformite.data.conforme ? "ok" : "err"}>{t(conformite.data.conforme ? `${m}.wps.conforme` : `${m}.wps.nonConforme`)}</Badge>{" "}
                  {conformite.data.requis.map((r) => r.wps_code).join(", ")}
                </p>
              )}
            </div>
          )}
        </div>
      </SectionCard>
    </>
  );
}
