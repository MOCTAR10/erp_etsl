---
name: regle-cdc
description: Implémente une règle de contrôle du cahier des charges ETSL (blocage, seuil, validation, alerte) de bout en bout — test rouge, correctif, garde-fous transverses, UI, documentation. À utiliser pour toute exigence RG-Mx / §x.y du CDC ou écart de la matrice ANALYSE_CDC_ETSL.md §8.
---

# Règle CDC ETSL — workflow complet

Sources qui font foi : `../DOSSIER DE CONSULTATION ETSL/` (CDC + cahier détaillé des modules), réponses CL-OM
(`Reponses_Clarifications_SOUMISSIONNAIRES.xlsx`, prévalent sur le CDC), matrice `../ANALYSE_CDC_ETSL.md` §8.

## 1. Cadrer
- Citer la référence exacte (ex. « M2 RG-M2.08 », « M12 §14.8 ») et le texte de la règle.
- Vérifier dans le code si elle existe déjà (grep du modèle, des actions, des permissions). Ne pas réimplémenter.

## 2. Test rouge d'abord (obligatoire)
- Nouveau fichier `<app>/test_<sujet>.py`, docstring = référence CDC + règle + défaut constaté.
- Lancer : `cd backend && python -m pytest <app>/test_<sujet>.py -p no:randomly` → **constater l'échec** et sa raison
  (une faille prouvée = statut HTTP 200 là où 403/400 est attendu).

## 3. Correctif — conventions du projet
- Transition d'état = **action dédiée** `@action(detail=True, methods=["post"])`, `@transaction.atomic`,
  `select_for_update(of=("self",))` ; vérifier l'**état de départ** ; jamais de PATCH de `statut`.
- Saisies d'action : `config/inputs.py` (`date_input`, `choice_input`, `fk_input`, `positive_decimal`) → 400, jamais 500.
- Champ « qui a créé / validé / visé » : `read_only_fields` + posé côté serveur ; l'ajouter à
  `ATTESTATION_FIELDS` (`users/test_authorship_sweep.py`).
- Règle de modèle (`clean()`) : sérialiseur hérite de `config.serializers.ModelCleanMixin`.
- Permission d'action : si la vue redéfinit `get_permissions`, y déclarer la permission (DRF ignore alors
  `permission_classes=` sur `@action`).
- Nouveaux champs → `python manage.py makemigrations <app>`.
- Adapter les tests existants qui entérinaient l'ancien comportement (le dire explicitement dans le commit).

## 4. Interface (si la règle a un geste utilisateur)
- Formulaire : `components/ui/QuickForm` ; bouton de workflow : `components/ui/ActionBar`
  (`confirm`, `prompt`, `prompt.options` pour un choix). Libellés i18n FR + EN (`src/i18n/fr.ts`, `en.ts`).

## 5. Vérifier
- `python -m pytest <apps touchées>` puis `python -m pytest` (suite complète, ~1-2 min sur le serveur).
- Frontend si modifié : `npm run typecheck && npm run test:unit`.

## 6. Documenter
- `../AUDIT_METIER_ETSL.md` : section du lot (défaut prouvé → correctif).
- `../ANALYSE_CDC_ETSL.md` §8 : passer la ligne de ❌/◐ à ✅.
- `../AGENTS.md` : uniquement les conventions nouvelles réutilisables.
