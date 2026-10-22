import { useQuery } from "@tanstack/react-query";
import { CloudOff, RefreshCw, Trash2, Wifi } from "lucide-react";
import { useState } from "react";
import { useTranslation } from "react-i18next";

import { api } from "../api/client";
import { Badge, PageHeader, SectionCard } from "../components/ui";
import { FichesSecuriteTerrain } from "../components/hse/FichesSecuriteTerrain";
import { offlineQueue, submitOffline, syncNow, useOnline, useQueueItems } from "../lib/offline";
import { useAuth } from "../store/auth";

type Tab = "pointage" | "gaz" | "reception" | "controle" | "anomalie";

interface Ref {
  id: string | number;
  code?: string;
  label?: string;
  [k: string]: unknown;
}

/** Listes de référence : le service worker en garde une copie pour la saisie hors-ligne (URLs fixes). */
const useRef_ = (key: string, path: string) =>
  useQuery({ queryKey: ["terrain", key], queryFn: () => api.listAll<Ref>(path), retry: 0 });

const today = () => new Date().toISOString().slice(0, 10);

export function TerrainPage() {
  const { t } = useTranslation();
  const online = useOnline();
  const items = useQueueItems();
  const user = useAuth((s) => s.user);
  const [tab, setTab] = useState<Tab>("pointage");
  const [toast, setToast] = useState<string | null>(null);
  const [syncing, setSyncing] = useState(false);

  const ordres = useRef_("ordres", "/api/operations/ordres/");
  const permis = useRef_("permis", "/api/hse/permis/");
  const receipts = useRef_("receipts", "/api/achats/receipts/");
  const orderLines = useRef_("order-lines", "/api/achats/order-lines/");

  const pending = items.filter((i) => i.status === "pending").length;
  const failed = items.filter((i) => i.status === "failed").length;

  const enqueue = async (path: string, body: unknown, label: string) => {
    await submitOffline({ path, body, label });
    setToast(online ? t("terrain.sent") : t("terrain.saved"));
  };
  const sync = async () => {
    setSyncing(true);
    try {
      await syncNow();
    } finally {
      setSyncing(false);
    }
  };

  const gazPermis = (permis.data ?? []).filter(
    (p) => ["valide", "actif"].includes(String(p.statut)) && p.gaz_obligatoire,
  );

  return (
    <>
      <PageHeader title={t("terrain.title")} subtitle={t("terrain.subtitle")} />

      <div className={`terrain-status ${online ? "on" : "off"}`} role="status">
        {online ? <Wifi size={18} /> : <CloudOff size={18} />}
        <strong>{online ? t("terrain.online") : t("terrain.offline")}</strong>
        <span>
          {pending > 0 ? t("terrain.pending", { count: pending }) : t("terrain.allSynced")}
          {failed > 0 ? ` · ${t("terrain.failed", { count: failed })}` : ""}
        </span>
        <button className="btn ghost" onClick={() => void sync()} disabled={!online || syncing || pending === 0}>
          <RefreshCw size={15} /> {t("terrain.sync")}
        </button>
      </div>

      {items.length > 0 && (
        <SectionCard title={t("terrain.queue")}>
          <ul className="terrain-queue">
            {items.map((i) => (
              <li key={i.id}>
                <div>
                  <strong>{i.label}</strong>
                  <div className="muted" style={{ fontSize: 12 }}>
                    {new Date(i.createdAt).toLocaleString()}
                    {i.error ? ` · ${i.error}` : ""}
                  </div>
                </div>
                <Badge tone={i.status === "failed" ? "err" : "warn"}>
                  {i.status === "failed" ? t("terrain.statusFailed") : t("terrain.statusPending")}
                </Badge>
                {i.status === "failed" && (
                  <button className="btn ghost" onClick={() => void offlineQueue.retry(i.id).then(syncNow)}>
                    <RefreshCw size={14} />
                  </button>
                )}
                <button
                  className="icon-btn"
                  aria-label={t("terrain.discard")}
                  onClick={() => void offlineQueue.discard(i.id)}
                >
                  <Trash2 size={15} />
                </button>
              </li>
            ))}
          </ul>
        </SectionCard>
      )}

      <div className="terrain-tabs" role="tablist">
        {(["pointage", "gaz", "reception", "controle", "anomalie"] as Tab[]).map((k) => (
          <button
            key={k}
            role="tab"
            aria-selected={tab === k}
            className={tab === k ? "active" : ""}
            onClick={() => {
              setTab(k);
              setToast(null);
            }}
          >
            {t(`terrain.tabs.${k}`)}
          </button>
        ))}
      </div>

      {toast && (
        <p className="terrain-toast" role="status">
          {toast}
        </p>
      )}

      {tab === "pointage" && (
        <Form
          submitLabel={t("terrain.save")}
          onSubmit={async (f) => {
            await enqueue(
              "/api/operations/pointages/",
              { ordre: f.ordre, worker_name: f.worker_name, date: f.date, hours: f.hours },
              `${t("terrain.tabs.pointage")} · ${f.worker_name} · ${f.hours} h`,
            );
          }}
          fields={[
            { name: "ordre", label: t("terrain.fields.ordre"), kind: "select", required: true,
              options: (ordres.data ?? []).map((o) => ({ value: String(o.id), label: `${o.code} · ${o.label}` })) },
            { name: "worker_name", label: t("terrain.fields.operateur"), kind: "text", required: true },
            { name: "date", label: t("terrain.fields.date"), kind: "date", required: true, initial: today() },
            { name: "hours", label: t("terrain.fields.heures"), kind: "number", required: true, initial: "8", step: "0.5" },
          ]}
        />
      )}

      {tab === "gaz" && (
        <Form
          submitLabel={t("terrain.save")}
          onSubmit={async (f) => {
            await enqueue(
              `/api/hse/permis/${f.permis}/test-gaz/`,
              { resultat: f.resultat, valeur: f.valeur },
              `${t("terrain.tabs.gaz")} · ${f.resultat === "conforme" ? "OK" : "NON CONFORME"} · ${f.valeur || "—"}`,
            );
          }}
          fields={[
            { name: "permis", label: t("terrain.fields.permis"), kind: "select", required: true,
              options: gazPermis.map((p) => ({ value: String(p.id), label: `${p.code} · ${p.emplacement}` })) },
            { name: "resultat", label: t("terrain.fields.resultat"), kind: "select", required: true, initial: "conforme",
              options: [
                { value: "conforme", label: t("terrain.conforme") },
                { value: "non_conforme", label: t("terrain.nonConforme") },
              ] },
            { name: "valeur", label: t("terrain.fields.mesures"), kind: "text", placeholder: "LIE 0 %, O2 20,9 %, H2S 0 ppm" },
          ]}
        />
      )}

      {tab === "reception" && (
        <Form
          submitLabel={t("terrain.save")}
          onSubmit={async (f) => {
            await enqueue(
              "/api/achats/receipt-lines/",
              { receipt: f.receipt, purchase_order_line: f.line, quantity: f.quantity, comment: f.comment },
              `${t("terrain.tabs.reception")} · ${f.quantity}`,
            );
          }}
          fields={[
            { name: "receipt", label: t("terrain.fields.bl"), kind: "select", required: true,
              options: (receipts.data ?? []).map((r) => ({ value: String(r.id), label: String(r.code ?? r.id) })) },
            { name: "line", label: t("terrain.fields.ligneBc"), kind: "select", required: true,
              options: (orderLines.data ?? []).map((l) => ({ value: String(l.id), label: String(l.label ?? l.id) })) },
            { name: "quantity", label: t("terrain.fields.quantite"), kind: "number", required: true, step: "0.01" },
            { name: "comment", label: t("terrain.fields.commentaire"), kind: "text" },
          ]}
        />
      )}

      {tab === "controle" && (
        <Form
          submitLabel={t("terrain.save")}
          onSubmit={async (f) => {
            await enqueue(
              "/api/qualite/controles/",
              { type_controle: f.type_controle, point_controle: f.point_controle, resultat: f.resultat,
                date_controle: f.date, statut: "en_cours" },
              `${t("terrain.tabs.controle")} · ${f.type_controle} · ${f.point_controle}`,
            );
          }}
          fields={[
            { name: "type_controle", label: t("terrain.fields.typeControle"), kind: "select", required: true, initial: "cnd",
              options: ["visuel", "dimensionnel", "cnd", "peinture"].map((v) => ({ value: v, label: v.toUpperCase() })) },
            { name: "point_controle", label: t("terrain.fields.pointControle"), kind: "text", required: true },
            { name: "resultat", label: t("terrain.fields.resultat"), kind: "select", required: true, initial: "conforme",
              options: [
                { value: "conforme", label: t("terrain.conforme") },
                { value: "reserve", label: t("terrain.reserve") },
                { value: "non_conforme", label: t("terrain.nonConforme") },
              ] },
            { name: "date", label: t("terrain.fields.date"), kind: "date", required: true, initial: today() },
          ]}
        />
      )}

      {tab === "anomalie" && (
        <Form
          submitLabel={t("terrain.save")}
          onSubmit={async (f) => {
            // Signalement d'anomalie HSE (CDC M7-08) : situation dangereuse, déclarée hors ligne si besoin.
            await enqueue(
              "/api/hse/incidents/",
              { type_incident: "situation_dangereuse", gravite: f.gravite, date_evenement: new Date().toISOString(),
                lieu: f.lieu, zone: f.zone, description: f.description },
              `${t("terrain.tabs.anomalie")} · ${f.lieu}`,
            );
          }}
          fields={[
            { name: "lieu", label: t("terrain.anomalie.lieu"), kind: "text", required: true },
            { name: "zone", label: t("terrain.anomalie.zone"), kind: "select", required: true, initial: "chantier",
              options: ["atelier", "chantier", "bureau", "site_client", "site_gr"].map((v) => ({ value: v, label: t(`m7e.zones.${v}`) })) },
            { name: "gravite", label: t("terrain.anomalie.gravite"), kind: "select", required: true, initial: "mineure",
              options: ["mineure", "majeure", "critique"].map((v) => ({ value: v, label: t(`terrain.anomalie.gravites.${v}`) })) },
            { name: "description", label: t("terrain.anomalie.description"), kind: "text", required: true },
          ]}
        />
      )}

      <FichesSecuriteTerrain />
      {user ? null : null}
    </>
  );
}

interface Field {
  name: string;
  label: string;
  kind: "text" | "number" | "date" | "select";
  required?: boolean;
  initial?: string;
  step?: string;
  placeholder?: string;
  options?: { value: string; label: string }[];
}

function Form({
  fields,
  onSubmit,
  submitLabel,
}: {
  fields: Field[];
  onSubmit: (values: Record<string, string>) => Promise<void>;
  submitLabel: string;
}) {
  const init = () => Object.fromEntries(fields.map((f) => [f.name, f.initial ?? ""]));
  const [values, setValues] = useState<Record<string, string>>(init);
  const [busy, setBusy] = useState(false);

  return (
    <form
      className="terrain-form"
      onSubmit={async (e) => {
        e.preventDefault();
        setBusy(true);
        try {
          await onSubmit(values);
          setValues(init());
        } finally {
          setBusy(false);
        }
      }}
    >
      {fields.map((f) => (
        <label className="field" key={f.name}>
          <span>{f.label}</span>
          {f.kind === "select" ? (
            <select required={f.required} value={values[f.name]} onChange={(e) => setValues({ ...values, [f.name]: e.target.value })}>
              <option value="">—</option>
              {(f.options ?? []).map((o) => (
                <option key={o.value} value={o.value}>
                  {o.label}
                </option>
              ))}
            </select>
          ) : (
            <input
              type={f.kind}
              required={f.required}
              step={f.step}
              placeholder={f.placeholder}
              inputMode={f.kind === "number" ? "decimal" : undefined}
              value={values[f.name]}
              onChange={(e) => setValues({ ...values, [f.name]: e.target.value })}
            />
          )}
        </label>
      ))}
      <button className="btn terrain-submit" type="submit" disabled={busy}>
        {submitLabel}
      </button>
    </form>
  );
}
