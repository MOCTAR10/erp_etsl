import { useTranslation } from "react-i18next";

interface BrandLogoProps {
  size?: "sm" | "lg";
  showTag?: boolean;
}

export function BrandLogo({ size = "sm", showTag = true }: BrandLogoProps) {
  const { t } = useTranslation();

  return (
    <div className="brand-lockup" data-testid="brand-logo">
      <span className={size === "lg" ? "brand-chip lg" : "brand-chip"}>
        <img src={`${import.meta.env.BASE_URL}etsl-logo.jpg`} alt={t("app.logoAlt")} />
      </span>
      <div className="brand-text">
        <span className="brand-word">ETSL ERP</span>
        {showTag && <span className="brand-tag">{t("app.tagline")}</span>}
      </div>
    </div>
  );
}