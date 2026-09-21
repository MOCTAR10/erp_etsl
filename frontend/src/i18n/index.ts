import i18n from "i18next";
import { initReactI18next } from "react-i18next";

import messages from "./messages";

const stored = localStorage.getItem("etls.lang");

i18n.use(initReactI18next).init({
  resources: {
    fr: { translation: messages.fr },
    en: { translation: messages.en },
  },
  lng: stored === "en" || stored === "fr" ? stored : "fr",
  fallbackLng: "fr",
  interpolation: { escapeValue: false },
});

export default i18n;