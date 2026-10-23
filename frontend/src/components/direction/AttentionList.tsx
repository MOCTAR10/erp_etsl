import { CheckCircle2, ChevronDown, ChevronRight } from "lucide-react";
import type { LucideIcon } from "lucide-react";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";

import { formatNumber } from "../../lib/format";

export interface AttentionItem {
  key: string;
  label: string;
  count: number;
  /** `err` = critique, `warn` = à surveiller. */
  tone: "err" | "warn";
  /** Route du module ou ancre de la page (« #echeances »). */
  to: string;
  Icon: LucideIcon;
}

const VISIBLE = 5;

/**
 * « À traiter maintenant » : liste compacte, une ligne par point ouvert (critiques d'abord, puis par volume),
 * 5 lignes puis « Voir tout ». Sur mobile, la liste est repliée derrière un bouton « n points à traiter ».
 */
export function AttentionList({ items }: { items: AttentionItem[] }) {
  const { t } = useTranslation();
  const [all, setAll] = useState(false);
  const [open, setOpen] = useState(false);
  const sorted = [...items].sort((a, b) => (a.tone === b.tone ? b.count - a.count : a.tone === "err" ? -1 : 1));
  const shown = all ? sorted : sorted.slice(0, VISIBLE);
  const critiques = sorted.filter((i) => i.tone === "err").length;

  return (
    <aside className="card dir-attn" data-open={open} aria-labelledby="dir-attn-title">
      <header className="dir-attn-head">
        <h3 id="dir-attn-title" className="card-title">
          {t("direction.urgent")}
        </h3>
        {sorted.length ? (
          <span className="dir-attn-total">{t("direction2.attention.points", { count: sorted.length })}</span>
        ) : null}
      </header>

      {sorted.length === 0 ? (
        <p className="dir-attn-none">
          <CheckCircle2 size={16} aria-hidden /> {t("direction.urgentNone")}
        </p>
      ) : (
        <>
          {critiques ? <p className="dir-attn-sub">{t("direction2.attention.critiques", { count: critiques })}</p> : null}
          <button type="button" className="btn dir-attn-toggle" aria-expanded={open} onClick={() => setOpen((o) => !o)}>
            {t("direction2.attention.points", { count: sorted.length })}
            <ChevronDown size={16} aria-hidden className="dir-attn-chevron" />
          </button>
          <ul className="dir-attn-list">
            {shown.map(({ key, label, count, tone, to, Icon }) => {
              const body = (
                <>
                  <span className={`dir-attn-icon ${tone}`} aria-hidden>
                    <Icon size={15} strokeWidth={1.9} />
                  </span>
                  <span className="dir-attn-label">{label}</span>
                  <span className={`dir-attn-count ${tone}`}>{formatNumber(count)}</span>
                  <ChevronRight size={15} className="dir-attn-go" aria-hidden />
                </>
              );
              return (
                <li key={key}>
                  {to.startsWith("#") ? (
                    <a href={to} className="dir-attn-item">
                      {body}
                    </a>
                  ) : (
                    <Link to={to} className="dir-attn-item">
                      {body}
                    </Link>
                  )}
                </li>
              );
            })}
          </ul>
          {sorted.length > VISIBLE ? (
            <button type="button" className="btn ghost sm dir-attn-more" onClick={() => setAll((v) => !v)} aria-expanded={all}>
              {all ? t("direction2.attention.moins") : t("direction2.attention.toutVoir", { count: sorted.length })}
            </button>
          ) : null}
        </>
      )}
    </aside>
  );
}
