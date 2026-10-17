---
name: livrer
description: Livre un changement ETSL — contrôles qualité complets, commit avec attribution, push, puis suivi de la CI GitHub Actions jusqu'au résultat (logs des échecs). À utiliser quand l'utilisateur dit « commit », « push », « livre », « on pousse ».
---

# Livrer un changement ETSL

## 1. Contrôles (tous verts avant de commiter)
```bash
cd backend
python manage.py check
python -m ruff check . --select E9,F63,F7,F82,F811 --exclude migrations
python manage.py makemigrations --check --dry-run
python -m pytest                      # suite complète, parallèle
cd ../frontend && npm run typecheck && npm run build && npm run test:unit   # si frontend touché
```
Un échec = corriger avant de continuer ; ne jamais commiter avec un contrôle rouge.

## 2. Commit
- `git status` : relire la liste ; ne pas embarquer de fichiers sans rapport (secrets `.env`, artefacts).
- Message en français : titre court (lot / sujet), puis puces des défauts corrigés et des règles CDC citées.
- Terminer par la ligne d'attribution demandée par le système (Co-Authored-By).

## 3. Push et CI
```bash
git push etsl_erp <branche>
gh run watch --exit-status $(gh run list --branch <branche> --limit 1 --json databaseId -q '.[0].databaseId')
```
- En cas d'échec : `gh run view <id> --log-failed` (logs complets) — corriger, recommencer au point 1.
- La CI se déclenche sur `master` et les pull requests : pour une branche, ouvrir une PR (`gh pr create`).

## 4. Rendre compte
Résultat CI (vert / rouge + cause), commit, et ce qui reste à faire.
