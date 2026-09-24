import { useTranslation } from "react-i18next";

interface BrandLogoProps {
  size?: "sm" | "lg";
  showTag?: boolean;
}

export function BrandLogo({ size = "sm", showTag = true }: BrandLogoProps) {
  const { t } = useTranslation();
  const chip = size === "lg" ? "8px 12px" : "6px 9px";

  return (
    <div className="brand-lockup" data-testid="brand-logo">
      <span className="brand-chip" style={{ padding: chip }}>
        <img src="/etsl-logo.jpg" alt={t("app.logoAlt")} />
      </span>
      <div className="brand-text">
        <span className="brand-word">ETSL ERP</span>
        {showTag && <span className="brand-tag">{t("brand.tagline")}</span>}
      </div>
    </div>
  );
}