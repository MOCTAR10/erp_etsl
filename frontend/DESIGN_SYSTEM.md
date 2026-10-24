# Système de design — ERP ETSL

Référence de l'interface : jetons, composants du kit `src/components/ui/`, règles « ERP premium », contraintes de non-régression et outillage (catalogue Ladle, tests visuels, Lighthouse).
Principe : **calme, dense, chiffré**. Le bleu structure (navigation, action principale), le gris porte l'information, le rouge n'apparaît que pour la marque (filet) ou l'alerte.

---

## 1. Jetons

**Source de vérité : `src/theme/tokens.ts`.** `src/styles/global.css` en dérive (`:root` et `:root[data-theme="dark"]`) et doit rester identique — vérifié par `src/theme/tokens.test.ts` (et les contrastes par `contrast.test.ts`). Toute couleur se modifie dans les DEUX fichiers. En CSS, toujours `var(--…)`, jamais un hex en dur ; en JS (Recharts, styles en ligne), `paletteFor(mode)` / `palette`.

### Couleurs (clair → sombre)

| Rôle | Variable CSS | Clair | Sombre | Usage |
|---|---|---|---|---|
| Fond d'application | `--bg` | `#f6f7fb` | `#0b1020` | derrière les cartes |
| Surface | `--surface` / `--surface-2` | `#ffffff` / `#f1f3f8` | `#151c33` / `#1c2541` | cartes ; colonnes kanban, en-têtes de tableau, survol de ligne |
| Bordures | `--border` / `--border-strong` | `#e3e7ef` / `#cfd6e3` | `#2a3557` / `#3a4770` | séparateurs ; champs |
| Texte | `--text` / `--text-muted` / `--text-subtle` | `#0f172a` / `#5b6578` / `#8a93a6` | `#e8edf7` / `#9aa7c6` / `#7684a8` | principal ; secondaire ; placeholders et axes (≥ 14 px uniquement) |
| Marque | `--brand` (`--brand-deep`, `--brand-soft`, `--brand-tint`) | `#12308f` | `#7f9cf5` | action principale, navigation active, liens |
| Accent du logo | `--accent` | `#d4142a` | `#f0475a` | filet sous le titre de page et de la navigation — **rien d'autre** |
| Acier | `--steel` | `#4f5f86` | `#a3b2d6` | tonalité « accent » des KPI / badges (métrique neutre) |
| Sémantiques | `--ok`, `--warn`, `--err`, `--info` (+ `-soft`, `-text`) | | | états ; le texte coloré utilise `-text` (contraste AA) |

### Typographie

Inter (données) + Plus Jakarta Sans (titres), auto-hébergées (`@fontsource-variable`). Les chiffres tabulaires (`tabular-nums`) sont **réservés** aux nombres : `.num`, `td.num`, `.amount`, `.kpi-value`, colonne `kind: "date"`, compteurs — jamais sur un conteneur de texte (`.table`, `.badge`, méta de carte…), où Inter élargit les traits d'union (« Port ‑ Gentil »). Séparateur de milliers unique (espace insécable U+00A0) pour `formatNumber` et `formatMoney`.

| Jeton | Taille / interligne | Usage |
|---|---|---|
| `--fs-display` | 40 / 44 | chiffre héros (Direction) |
| `--fs-h1` | 24 / 32 | titre de page (`.page-header h2`) |
| `--fs-h2` | 18 / 26 | titre de section / carte |
| `--fs-h3` | 15 / 22 | sous-section, titre de carte kanban |
| `--fs-kpi` | 28 / 32 | valeur KPI ; un montant (`kind="money"`) reste à 28 px tant qu'il tient dans la carte, puis se réduit juste assez (unité « FCFA » à 14 px) |
| `--fs-body` | 14 / 20 | texte courant, cellules |
| `--fs-sm` | 13 / 18 | méta, sous-titres, boutons |
| `--fs-xs` | 12 / 16 | libellés KPI, en-têtes de tableau, badges |

Graisses `--fw-regular` 400 → `--fw-bold` 700 (jamais 800). Titres : `--tracking-title`, `--word-spacing-title`. Majuscules réservées aux en-têtes de groupe de navigation.

### Espaces, rayons, ombres, contrôles, mouvement

- Espaces (base 4, rythme 8) : `--space-1` 4 · `-2` 8 · `-3` 12 · `-4` 16 · `-5` 20 · `-6` 24 · `-8` 32 · `-10` 40. Entre blocs de page 24 px ; dans une carte padding 20 px, gap 12 px ; grilles KPI / boards gap 16 px.
- Rayons : `--radius-xs` 6 (badges, kbd) · `-sm` 8 (boutons, champs) · `-md` 10 (cartes kanban, menus) · `-lg` 12 (cartes, sections) · `-xl` 16 (surfaces flottantes uniquement) · `-full`.
- Ombres (3 niveaux, jamais colorées) : `--shadow-xs` (cartes, champs) · `--shadow-md` (survol d'une carte cliquable) · `--shadow-pop` (menus, dialogues, palette, notifications).
- Contrôles : `--control-h-sm` 32 (tableaux, cartes) · `--control-h` 36 (défaut) · `--control-h-lg` 44 (terrain, mobile).
- Mouvement : `motionTokens` (`fast` 160 ms, `base` 300 ms), presets dans `src/lib/motion.ts`, `motion` est le SEUL moteur d'animation ; `MotionProvider` (`reducedMotion="user"`) + coupe-circuit CSS pour `prefers-reduced-motion`.
- CSS en couches : `@layer reset, tokens, base, components, layout, pages, utilities` ; les styles d'écran vont dans `src/styles/pages/*.css` (`@layer pages`).

---

## 2. Composants (`src/components/ui/`, barrel `index.ts`)

Catalogue vivant de tous les états : `npm run ladle` (§5). Props exactes : lire le fichier du composant.

| Composant | API essentielle | Quand l'utiliser |
|---|---|---|
| `PageHeader` | `title`, `subtitle`, `actions`, `eyebrow` | En tête de CHAQUE page : un titre, une phrase, l'action principale à droite. |
| `SectionNav` | `items` (`id`, `label`, `count`), `label`, `offset`, `onNavigate` | Écran long (≥ 4 sections) : barre collante posée **juste sous** le `PageHeader`, une ancre par section (`id` de la cible dans la page). La section lue est surlignée au défilement (IntersectionObserver, `aria-current="location"`) ; saut fluide (instantané si mouvement réduit), focus déplacé sur la section ; sous 900 px, barre défilante horizontale qui garde l'ancre active visible. `<nav>` nommé « Sections de la page ». |
| `Card`, `SectionCard` | `title`, `subtitle`, `actions`, `children` | Regrouper un bloc ; `SectionCard` dès qu'il a un titre. |
| `ChartCard` | `title`, `subtitle`, `height`, `children` | Graphique Recharts (Direction, répartition du tableau de bord seulement). |
| `Kpi` | `label`, `value`, `kind="number\|money\|percent"`, `hint`, `icon`, `tone` | Indicateur chiffré ; `kind="money"` → montant exact en FCFA, 28 px tant qu'il tient (sinon ajusté à la carte), « — » si masqué. Donner un `hint` (« 34 710 000 FCFA engagés ») ; sans `hint`, la valeur se cale en bas de la carte (hauteurs homogènes). |
| `AnimatedNumber`, `Sparkline`, `ProgressBar` | `value` / `values`, `label`, `tone` | Chiffre animé, tendance miniature, avancement (avec libellé accessible). |
| `Badge` | `tone="ok\|warn\|err\|brand\|accent\|neutral\|info"`, `icon`, `title` | Statut d'un objet (une couleur = un sens). |
| `Board`, `BoardColumn`, `BoardCard`, `CardActions` | `label` ; `title`, `count`, `tone`, `summary`, `limit`, `emptyLabel` ; `actions`, `primary` | Kanban horizontal par statut ; une action principale par carte, le reste dans `⋯`. Chaque colonne fait défiler sa liste (en-tête fixe, fondu bas) ; colonne vide réduite à 184 px ; sous 640 px colonnes empilées, colonne vide = en-tête + « 0 ». Titre de carte : 3 lignes au plus. |
| `DataGrid` / `DataTable` / `PagedDataGrid` | `columns` (`key`, `header`, `render`, `num`, `kind="date"`, `label`, `sortValue`, `width`), `rows`, `caption`, `loading`, `density`, `rowActions`, `onRowClick`, `pagination`, `emptyLabel`, `emptyHint`, `mobile="cards\|scroll"` | Toute liste d'entités ; `PagedDataGrid` pour une liste serveur (`usePagedList`). `actionsColumn(label, actions)` = colonne d'actions de ligne. Débordement en largeur : 1re colonne collante + fondu à droite. Hauteur bornée qui coupe des lignes : fondu bas + « Afficher les N lignes ». Sous 640 px (≥ 3 colonnes) : une carte par ligne (1re colonne en titre, puis libellé / valeur ; `label` si `header` n'est pas un texte) ; `mobile="scroll"` pour garder le tableau. |
| `FileField` | `accept`, `name`, `id` ou `aria-label`, `onChange(file)` / `onFiles(files)`, `buttonLabel`, `capture`, `multiple`, `disabled` | Tout choix de fichier (imports MT940 / SAGE, pièces jointes, photos) : bouton du kit et mention en français, thémés clair / sombre. Jamais d'`<input type="file">` visible (« Choose File »). |
| `Pagination`, `SearchField`, `FilterBar` | `page`, `pageSize`, `count` ; `value`, `onChange` ; `defs`, `value`, `primary`, `search`, `more` | Pagination serveur DRF, recherche différée, filtres multicritères (3 en ligne, le reste dans « Plus de filtres »). |
| `QuickForm` | `title`, `endpoint`, `fields`, `submitLabel`, `transform`, `variant` | Création rapide en panneau latéral (POST direct). Dans une carte, une barre d'actions de section ou une barre d'outils, le déclencheur est rendu secondaire (un seul primaire par écran). |
| `ActionBar` | `actions: ActionDef[]` (`label`, `path`, `tone`, `confirm`, `prompt`) | Actions de workflow d'un objet (le serveur décide des droits). |
| `DatePicker`, `DateRangePicker` | `id`, `name`, `value` (ISO), `onChange`, `min`, `max`, `disabled` | Toute date (saisie jj/mm/aaaa + calendrier) et toute période. Jamais d'`<input type="date">` natif (format de la langue du navigateur). |
| `MonthPicker` | `id`, `name`, `value` (« AAAA-MM »), `onChange`, `min`, `max`, `emptyLabel` | Tout choix de mois : liste du kit libellée dans la langue de l'interface (« Octobre 2026 »). Jamais d'`<input type="month">` natif. |
| `Menu` | `items` (`label`, `icon`, `onSelect`, `shortcut`, `danger`, `disabled` \| `"separator"` \| `{type:"label"}`), `label`, `trigger` | Actions secondaires `⋯` ; destructives en dernier, en rouge. |
| `Sheet`, `Modal`, `SheetClose` | `title`, `description`, `footer`, `trigger` ou `open`/`onOpenChange`, `width` | Panneau latéral (édition, détail) ; fenêtre centrée (confirmation). |
| `Tooltip`, `Popover` | `content` ; `trigger`, `label` | Aide courte au survol ; contenu riche au clic. |
| `notify`, `AppToaster` | `notify.success\|error\|info\|warning(message, {description})` | Retour d'action ; jamais d'`alert()`. |
| `CommandPalette` | `groups`, `search`, `open`, `onOpenChange`, `hotkey` | Palette Ctrl+K (pages, actions, entités serveur). |
| `EmptyState`, `ErrorState`, `Skeleton` (`KpiSkeleton`, `KpiGridSkeleton`, `BoardSkeleton`) | `label`, `hint`, `icon`, `action`, `compact` ; `message`, `onRetry` | Chaque liste dessine ses états vide / erreur / chargement. |

Formatage (`src/lib/format.ts`) : `formatMoney` (« 25 000 000 FCFA »), `formatNumber`, `formatPercent`, `formatParametre` (valeur + unité d'un paramètre servi par l'API : « 30 jours », « 15 000 FCFA/h », « Oui », compte « 411700 » — jamais « 30.00 jours »), `formatDate` (« 23 sept. 2026 »), `formatDateShort` (« 23/09/2026 »), `formatDateTime`, `EMPTY` (« — »). Les nombres suivent la langue de l'interface : FR « 3 337 000 000 FCFA », « 81,3 % » ; EN « 3,337,000,000 FCFA », « 81.3% » (la devise reste FCFA, le montant reste exact).

Utilitaires CSS partagés : `.page-section` (groupe de blocs ciblé par une ancre de `SectionNav` : `<div id="cpt-tresorerie" className="page-section">`, garde le rythme de 24 px ; une cible par entrée, ids préfixés par écran, paramètres provisoires en dernier groupe), `.cell-nowrap` (codes, dates d'une cellule), `.cell-sub` (ligne secondaire d'une cellule), `.kit-disclosure` (`<details>` avec chevron tokenisé), `.banner.warn` pour tout avertissement « provisoire » (le rouge est réservé aux alertes). `Column.width` impose aussi une largeur minimale ; sous 900 px, un tableau de 3 colonnes ou plus garde une largeur minimale et défile dans son cadre (fondu de bord quand il déborde). `PagedDataGrid` / `PagedDataTable` n'ont pas de hauteur maximale (la pagination la borne). Les blocs empilés directement dans la zone principale sont espacés de 24 px. Un seul point d'entrée API : l'objet `api` de `src/api/client.ts` (jamais de `fetch()` dans une page).

---

## 3. Règles « ERP premium »

1. **Montants exacts et complets**, toujours via `formatMoney` : « 25 000 000 FCFA » (espace insécable), jamais « 25 M » ni « 25 k », même dans un KPI. Si la place manque, réduire la police ou élargir la carte, pas le nombre. Chiffres en `tabular-nums`, alignés à droite dans les tableaux (`num: true`).
2. **Couleurs avec retenue** : bleu = action principale et navigation ; rouge `--accent` = filet de marque uniquement ; rouge `--err` = état critique. Au plus un élément rouge par carte. Pas d'aplat criard, pas d'ombre colorée, pas de bouton plein rouge hors confirmation destructive.
3. **Un point focal par écran** : une seule action primaire (`.btn.primary`) par en-tête ; les autres en boutons secondaires ou dans `⋯`. Au plus 3 tailles de texte visibles.
4. **Rédaction sans code technique** : aucun `RF-…`, `H-…`, `(Mx)`, `§`, `proc.`, code de rôle brut ni clé i18n visible. Libellés en casse de phrase, en français avec accents ; toute clé ajoutée existe dans `fr.ts` ET `en.ts`.
5. **États dessinés** : survol (éléments cliquables seulement), focus visible, actif, désactivé (bouton neutre : `--surface-2`, texte `--text-subtle`, jamais un primaire délavé), chargement (squelettes), vide (`EmptyState` avec aide), erreur (`ErrorState` avec « Réessayer »).
6. **Mode sombre aussi soigné que le clair** : uniquement des variables, aucun blanc ni noir pur ; vérifier chaque écran dans les deux thèmes (Ladle, tests visuels).
7. **Mobile (≤ 900 px)** : sidebar en tiroir, KPI en 2 colonnes, aucune barre de défilement horizontale de page (les tableaux défilent dans leur cadre).
8. **Accessibilité** : 0 violation axe WCAG A/AA, `aria-label` sur chaque `.icon-btn`, contrastes AA (`contrast.test.ts`), mouvement 120–200 ms et `prefers-reduced-motion` respecté.

---

## 4. Contraintes de non-régression (specs e2e = contrat)

- **Classes consommées par l'e2e** : `.card .kpi .badge .board* .task-card .table .field .btn .icon-btn .login* .sidebar .nav-toggle .page-header .sidebar-logout .nav-backdrop #app-sidebar` — on AJOUTE des classes, on ne les renomme jamais.
- **Libellés testés** : « ETSL ERP » exact (`auth.spec`) ; titres `h2` par regex (`navigation.spec` : « Tableau de bord », « Achats », « Opérations », « RH & Paie », « Direction / BI », « GED — Documents », « Paramètres ETSL »…) ; `theme.spec` : `button.icon-btn[aria-label="Sombre"]` et `[aria-label="Français"]` ; `Login.test.tsx` : ids `email` / `password`, « Se connecter », « Chargement… », « Identifiants incorrects. ».
- **Page d'arrivée** : `admin` atterrit sur `/` (`landing.ts` + `landing.test.ts`).
- **RBAC** : `canSeeApp()` / `ROUTE_APP` filtrent la navigation ; `.task-card` utilisée par `rbac.spec` ; montants masqués (`has_amount_access`) affichés « — ».
- `tsconfig.json` ne couvre que `src/` (les histoires `*.stories.tsx` y sont typées ; les specs e2e ne le sont que par Playwright).

---

## 5. Outillage

Le PC de développement manque de RAM : lancer ces commandes sur le serveur de dev (`ssh etsl-dev@79.143.177.127`, `. ~/.nvm/nvm.sh`), ou sur un poste suffisamment équipé.

### Catalogue Ladle (kit UI)

```bash
cd frontend
npm run ladle            # catalogue interactif : http://localhost:61000 (thème clair/sombre, largeurs mobile/tablette/bureau, axe)
npm run ladle:build      # catalogue statique dans build-ladle/ (puis : npx ladle preview)
```

- Configuration : `.ladle/config.mjs` (histoires `src/**/*.stories.tsx`), `.ladle/vite.config.ts` (Vite embarqué par Ladle, sans proxy ni dossier public), `.ladle/components.tsx` (fournisseur commun : styles, i18n, TanStack Query, routeur mémoire, `MotionProvider`, thème).
- Une histoire **importe** les composants, elle ne les modifie pas ; données fictives réalistes (FCFA, dates FR), aucun appel réseau.
- Variante sombre figée : `MonHistoire.meta = { theme: "dark" }`. Noms d'histoires (`storyName`) : lettres, accents, chiffres et espaces seulement (Ladle en fait des identifiants JavaScript : pas de `«`, `'`, `—`, parenthèses).
- Depuis le PC : `ssh -L 61000:localhost:61000 etsl-dev@79.143.177.127`, puis `npm run ladle` sur le serveur.

### Tests visuels (`npm run test:visual`)

10 écrans (connexion, tableau de bord, Direction, validations, achats, opérations, stocks, HSE, comptabilité, GED) × 3 projets (`clair` 1440×900, `sombre`, `mobile` 390×844), `toHaveScreenshot` avec `maxDiffPixelRatio: 0.01`, animations coupées, zones volatiles masquées (`time`, notifications, et tout élément marqué `data-visuel="volatil"`).

- Projet Playwright **séparé** (`playwright.visuel.config.ts`, fichiers `e2e/visuel/*.visuel.ts`) : jamais exécuté par `npm run test:e2e` ni par la CI, car le rendu des polices dépend du système.
- Prérequis : backend sur la base de démo seedée (`migrate` + `seed_all_demo`, base `etls_e2e`), comptes démo (`admin@etls.local`, mot de passe `Etls#Demo2026`). Le test construit le frontend (`vite build`) puis le sert avec `vite preview` sur le port 4173 (`VISUEL_PORT` pour en changer, `PW_WEB_CMD` pour une autre commande).
- Références : `e2e/visuel/references/<projet>/<écran>.png`, **non versionnées** (`.gitignore`) : elles dépendent des polices du conteneur ET des données de la base. Méthode : générer les références sur la branche de référence, puis rejouer sur la branche à contrôler, dans le même conteneur et contre la même base.
- Toujours dans le conteneur officiel (mêmes navigateurs et polices que `@playwright/test` 1.63) ; sur le serveur de dev (backend e2e sur 8100) :

```bash
cd ~/<worktree>/frontend            # node_modules installés (npm ci)
# 1. Générer (ou régénérer) les références — sur la branche de référence
docker run --rm --ipc=host --network host --user "$(id -u):$(id -g)" -e HOME=/tmp \
  -e VITE_API_TARGET=http://127.0.0.1:8100 -e PW_WORKERS=4 \
  -v "$PWD":/app -w /app mcr.microsoft.com/playwright:v1.63.0-noble \
  npm run test:visual -- --update-snapshots
# 2. Rejouer — sur la branche à contrôler (même commande sans --update-snapshots)
docker run --rm --ipc=host --network host --user "$(id -u):$(id -g)" -e HOME=/tmp \
  -e VITE_API_TARGET=http://127.0.0.1:8100 -e PW_WORKERS=4 \
  -v "$PWD":/app -w /app mcr.microsoft.com/playwright:v1.63.0-noble \
  npm run test:visual
# Écarts : playwright-report/visuel/index.html (attendu / obtenu / différence) et test-results/visuel/
```

- Un écran seul : ajouter `-- -g "direction"` ; un projet : `-- --project=sombre`. `--user` évite des fichiers appartenant à root dans le dépôt ; `--ipc=host` évite les plantages de Chromium.
- Ajouter un écran : une ligne dans `ECRANS` (`e2e/visuel/ecrans.visuel.ts`), puis régénérer ses références.

### Lighthouse (local, hors CI)

```bash
npm run build && VITE_API_TARGET=http://127.0.0.1:8100 npx vite preview --host 127.0.0.1 --port 4173 &
npm run lighthouse      # Chrome local requis ; rapports lighthouse-connexion.report.html / .json (ignorés par git)
```

Dans le conteneur Playwright (aucun Chrome installé sur le serveur) : `docker run --rm --ipc=host --network host --user "$(id -u):$(id -g)" -e HOME=/tmp -v "$PWD":/app -w /app mcr.microsoft.com/playwright:v1.63.0-noble bash -c 'export CHROME_PATH=$(ls -d /ms-playwright/chromium-*/chrome-linux*/chrome | head -1); npm run lighthouse -- --chrome-flags="--headless=new --no-sandbox"'`. Mesure de référence (écran de connexion, 2026-10-23) : performance 96, accessibilité 100, bonnes pratiques 100.
