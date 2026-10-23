import { Download, FileSpreadsheet, FileText } from "lucide-react";
import { useTranslation } from "react-i18next";

import { api } from "../../api/client";
import { describeError } from "../../lib/offlineQueue";
import { Menu, notify } from "../ui";
import type { MenuEntry } from "../ui";

interface ExportDef {
  id: string;
  label: string;
  path: string;
  nom: string;
}

/**
 * Exports Excel / PDF de la page Direction, rangés dans un seul menu « Exporter » (téléchargement authentifié,
 * journalisé côté serveur). Les exports financiers n'apparaissent que si le pilotage financier est lisible.
 */
export function DirectionExports({ financier }: { financier: boolean }) {
  const { t } = useTranslation();
  const exports: ExportDef[] = [
    { id: "direction", label: t("ecarts_cd.exports.direction"), path: "/api/analytics/dashboard/", nom: "tableau_direction" },
    { id: "petrolier", label: t("ecarts_cd.exports.petrolier"), path: "/api/analytics/petrolier/", nom: "reporting_petrolier" },
    ...(financier
      ? [
          { id: "pilotage", label: t("ecarts_cd.exports.pilotage"), path: "/api/analytics/pilotage/", nom: "pilotage_direction" },
          { id: "cube", label: t("ecarts_cd.exports.cube"), path: "/api/analytics/cubes/?axes=periode,affaire", nom: "cube_bi" },
        ]
      : []),
  ];
  const dl = (e: ExportDef, fmt: "xlsx" | "pdf") => {
    const sep = e.path.includes("?") ? "&" : "?";
    api.download(`${e.path}${sep}export=${fmt}`, `${e.nom}.${fmt}`).then(
      () => notify.success(t("direction2.exports.ok", { nom: e.label })),
      (err) => notify.error(t("direction2.exports.ko"), { description: describeError(err) }),
    );
  };
  const items: MenuEntry[] = exports.flatMap((e, i) => [
    i > 0 ? ("separator" as const) : false,
    { type: "label" as const, label: e.label },
    { id: `${e.id}-xlsx`, label: t("direction2.exports.excel"), icon: FileSpreadsheet, onSelect: () => dl(e, "xlsx") },
    { id: `${e.id}-pdf`, label: t("direction2.exports.pdf"), icon: FileText, onSelect: () => dl(e, "pdf") },
  ]);
  return (
    <span data-testid="exports-direction">
      <Menu
        items={items}
        trigger={
          <button type="button" className="btn ghost">
            <Download size={16} aria-hidden />
            {t("direction2.exports.bouton")}
          </button>
        }
      />
    </span>
  );
}
