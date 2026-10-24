import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useTranslation } from "react-i18next";

import { api } from "../../api/client";
import { formatDate, formatNumber } from "../../lib/format";
import { describeError } from "../../lib/offlineQueue";
import type { ReleveBancaire, RapprochementAuto } from "../../types";
import { Badge, FileField, SectionCard } from "../ui";

interface Banque {
  id: string;
  label: string;
}

/**
 * Import d'un relevé MT940 / CFONB 120 (gabarits standard, à valider sur les fichiers réels d'ETSL) et
 * rapprochement automatique avec les paiements validés. Les écarts sont listés, jamais masqués.
 */
export function BanqueSection() {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const [banque, setBanque] = useState("");
  const [format, setFormat] = useState("auto");
  const [contenu, setContenu] = useState("");
  // Clé du sélecteur de fichier : changée après un import réussi pour le vider.
  const [fileKey, setFileKey] = useState(0);
  const [dernier, setDernier] = useState<ReleveBancaire | null>(null);
  const [rapp, setRapp] = useState<RapprochementAuto | null>(null);
  const [error, setError] = useState<string | null>(null);

  const banques = useQuery({
    queryKey: ["banque-comptes"],
    queryFn: () => api.listAll<Banque>("/api/comptabilite/comptes-bancaires/"),
    retry: 0,
  });

  const importer = useMutation({
    mutationFn: () => api.post<ReleveBancaire>("/api/comptabilite/releves/importer/", { compte_bancaire: banque, format, contenu }),
    onSuccess: (r) => {
      setError(null);
      setDernier(r);
      setContenu("");
      setFileKey((k) => k + 1);
      void qc.invalidateQueries({ queryKey: ["compta-releves"] });
    },
    onError: (e) => setError(describeError(e)),
  });
  const rapprocher = useMutation({
    mutationFn: () => api.post<RapprochementAuto>("/api/comptabilite/rapprochements/rapprocher-auto/", { compte_bancaire: banque }),
    onSuccess: (r) => {
      setError(null);
      setRapp(r);
      void qc.invalidateQueries({ queryKey: ["compta-releves"] });
    },
    onError: (e) => setError(describeError(e)),
  });

  if (banques.isError) return null;

  const choisirFichier = async (f: File | null) => {
    if (!f) {
      setContenu("");
      return;
    }
    setContenu(await f.text());
  };

  return (
    <SectionCard title={t("banque.title")}>
      <p className="muted">{t("banque.hint")}</p>
      {error && <p className="action-error" role="alert">{error}</p>}
      <div className="row-actions">
        <select aria-label={t("banque.compte")} value={banque} onChange={(e) => { setBanque(e.target.value); setRapp(null); }}>
          <option value="">{t("banque.choisir")}</option>
          {(banques.data ?? []).map((b) => <option key={b.id} value={b.id}>{b.label}</option>)}
        </select>
        <select aria-label={t("banque.format")} value={format} onChange={(e) => setFormat(e.target.value)}>
          <option value="auto">{t("banque.auto")}</option>
          <option value="mt940">MT940</option>
          <option value="cfonb120">CFONB 120</option>
        </select>
        <FileField key={fileKey} aria-label={t("banque.fichier")} accept=".txt,.sta,.mt940,.cfonb,.dat" onChange={(f) => void choisirFichier(f)} />
        <button type="button" className="btn" disabled={!banque || !contenu || importer.isPending} onClick={() => importer.mutate()}>
          {t("banque.importer")}
        </button>
        <button type="button" className="btn ghost" disabled={!banque || rapprocher.isPending} onClick={() => rapprocher.mutate()}>
          {t("banque.rapprocher")}
        </button>
      </div>

      {dernier && (
        <div role="status" data-testid="import-resultat">
          <p>
            {t("banque.importe", { n: dernier.lignes.length, debut: formatDate(dernier.date_debut), fin: formatDate(dernier.date_fin) })}{" "}
            <Badge tone={dernier.anomalies.length ? "warn" : "ok"}>
              {dernier.anomalies.length ? t("banque.nbAnomalies", { count: dernier.anomalies.length }) : t("banque.aucuneAnomalie")}
            </Badge>
          </p>
          {dernier.anomalies.length > 0 && (
            <ul>
              {dernier.anomalies.map((a, i) => <li key={i}>{a.message}</li>)}
            </ul>
          )}
        </div>
      )}

      {rapp && (
        <div role="status" data-testid="rapprochement-resultat">
          <p>
            {t("banque.rapprochees", { n: rapp.rapprochees })}{" "}
            {rapp.parametres_provisoires && <Badge tone="warn">{t("banque.tolerancesProvisoires")}</Badge>}
          </p>
          {rapp.ambigues.length > 0 && <p className="muted">{t("banque.ambigues", { count: rapp.ambigues.length })}</p>}
          {rapp.lignes_sans_paiement.length > 0 && (
            <>
              <h4 className="section-heading">{t("banque.lignesSansPaiement", { count: rapp.lignes_sans_paiement.length })}</h4>
              <table className="table">
                <tbody>
                  {rapp.lignes_sans_paiement.map((l) => (
                    <tr key={l.id}>
                      <td>{formatDate(l.date)}</td>
                      <td>{l.libelle}</td>
                      <td className="num">{l.credit === null || l.debit === null ? "••••••" : formatNumber(Number(l.credit) - Number(l.debit))}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </>
          )}
          {rapp.paiements_sans_ligne.length > 0 && (
            <>
              <h4 className="section-heading">{t("banque.paiementsSansLigne", { count: rapp.paiements_sans_ligne.length })}</h4>
              <table className="table">
                <tbody>
                  {rapp.paiements_sans_ligne.map((p) => (
                    <tr key={p.id}>
                      <td>{p.code}</td>
                      <td>{formatDate(p.date)}</td>
                      <td className="num">{p.montant === null ? "••••••" : formatNumber(Number(p.montant))}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </>
          )}
        </div>
      )}
    </SectionCard>
  );
}
