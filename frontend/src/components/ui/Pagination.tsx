import { ChevronLeft, ChevronRight } from "lucide-react";
import { useTranslation } from "react-i18next";

export const PAGE_SIZES = [20, 50, 100] as const;

/** Pagination d'une liste serveur (DRF `count`/`page`/`page_size`) : précédent / suivant, page courante, taille de page. */
export function Pagination({
  page,
  pageSize,
  count,
  onPageChange,
  onPageSizeChange,
}: {
  page: number;
  pageSize: number;
  count: number;
  onPageChange: (page: number) => void;
  onPageSizeChange?: (size: number) => void;
}) {
  const { t } = useTranslation();
  const pages = Math.max(1, Math.ceil(count / pageSize));
  if (count <= PAGE_SIZES[0] && page === 1) return null;

  return (
    <nav className="pagination" aria-label={t("common.pagination")}>
      <span className="muted" aria-live="polite">
        {t("common.results", { count })}
      </span>
      <div className="pagination-controls">
        {onPageSizeChange ? (
          <label className="pagination-size">
            <span className="sr-only">{t("common.pageSize")}</span>
            <select
              value={pageSize}
              onChange={(e) => onPageSizeChange(Number(e.target.value))}
              aria-label={t("common.pageSize")}
            >
              {PAGE_SIZES.map((s) => (
                <option key={s} value={s}>
                  {s}
                </option>
              ))}
            </select>
          </label>
        ) : null}
        <button
          type="button"
          className="btn"
          onClick={() => onPageChange(page - 1)}
          disabled={page <= 1}
          aria-label={t("common.previous")}
        >
          <ChevronLeft size={14} aria-hidden />
        </button>
        <span aria-current="page">{t("common.pageOf", { page, pages })}</span>
        <button
          type="button"
          className="btn"
          onClick={() => onPageChange(page + 1)}
          disabled={page >= pages}
          aria-label={t("common.next")}
        >
          <ChevronRight size={14} aria-hidden />
        </button>
      </div>
    </nav>
  );
}
