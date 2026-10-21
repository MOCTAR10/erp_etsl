"""Écarts M6-C (CDC M6.2, ISO 9001) : documents maîtrisés, audits, agrément fournisseur, compétences, revue de direction."""

from datetime import timedelta

from django.db.models import Avg
from django.utils import timezone

from users.models import User

from .ecarts import RETENTION_QUALITE_ANS, TYPE_GED_QUALITE, get_param_qualite, indicateurs

#: L'approbation de la politique qualité engage la direction (ISO 9001 §5.1-5.2).
ROLES_DIRECTION = (User.Role.ADMIN, User.Role.PDG, User.Role.DGA, User.Role.DIRECTION)


def engage_direction(user):
    return user.is_authenticated and (user.is_superuser or user.role in ROLES_DIRECTION)


def _ajouter_mois(jour, mois):
    annee, m = divmod(jour.month - 1 + int(mois), 12)
    import calendar

    a, m = jour.year + annee, m + 1
    return jour.replace(year=a, month=m, day=min(jour.day, calendar.monthrange(a, m)[1]))


def archiver(contenu, nom, titre, reference, objet_type, objet_id, user, mots, note):
    from hse.services import archiver_ged

    return archiver_ged(
        contenu, nom, titre, TYPE_GED_QUALITE, "Documents qualité / ISO", reference, objet_type, objet_id, user=user,
        mots=mots, module="M6", note=note, retention=RETENTION_QUALITE_ANS,
    )


def approuver_document(doc, user):
    """Approuve une version : précédente version en vigueur rendue obsolète, fichier scellé en GED (10 ans)."""
    from hse.services import _pdf

    from .models import DocumentQualite

    jour = timezone.localdate()
    DocumentQualite.objects.filter(reference=doc.reference, statut=DocumentQualite.Statut.APPROUVE).exclude(pk=doc.pk).update(
        statut=DocumentQualite.Statut.OBSOLETE
    )
    doc.statut = DocumentQualite.Statut.APPROUVE
    doc.approuve_par, doc.approuve_le = user, timezone.now()
    doc.date_revue = _ajouter_mois(jour, doc.periodicite_revue_mois)
    if doc.fichier:
        doc.fichier.open("rb")
        contenu, nom = doc.fichier.read(), doc.fichier.name.rsplit("/", 1)[-1]
        doc.fichier.close()
    else:
        contenu = _pdf(f"{doc.reference} v{doc.version} — {doc.titre}", [
            ("Type", doc.get_type_doc_display()), ("Version", str(doc.version)),
            ("Approuvé par", user.get_full_name() or user.email), ("Approuvé le", f"{jour:%d/%m/%Y}"),
            ("Objet de la révision", doc.motif_revision or "Création"),
        ])
        nom = f"{doc.reference}-v{doc.version}.pdf"
    doc.document = archiver(contenu, nom, f"{doc.reference} v{doc.version} — {doc.titre}", doc.reference,
                            "qualite.documentqualite", doc.pk, user, ("liste maîtresse", doc.get_type_doc_display()),
                            "Document qualité approuvé (version en vigueur)")
    doc.save()
    return doc


def reviser_document(doc, user, motif):
    from .models import DocumentQualite

    return DocumentQualite.objects.create(
        reference=doc.reference, version=doc.version + 1, type_doc=doc.type_doc, titre=doc.titre, processus=doc.processus,
        affaire=doc.affaire, periodicite_revue_mois=doc.periodicite_revue_mois, motif_revision=motif, redige_par=user,
    )


def nc_constat(constat, user=None):
    from .models import ConstatAuditQualite, NonConformite

    if constat.type_constat not in ConstatAuditQualite.ECARTS or constat.nc_id:
        return None
    audit = constat.audit
    constat.nc = NonConformite.objects.create(
        source=NonConformite.Source.AUDIT,
        gravite=NonConformite.Gravite.MAJEURE if constat.type_constat == ConstatAuditQualite.TypeConstat.ECART_MAJEUR else NonConformite.Gravite.MINEURE,
        description=f"Audit {audit.code} ({audit.get_type_audit_display()}) — {constat.exigence + ' : ' if constat.exigence else ''}{constat.description}"[:2000],
    )
    constat.save(update_fields=["nc"])
    return constat.nc


def decision_agrement(audit):
    """Agrément d'un fournisseur audité : score ≥ seuil et aucun écart majeur (seuil provisoire paramétrable)."""
    from .models import ConstatAuditQualite

    if audit.score is None:
        return False
    majeur = audit.constats.filter(type_constat=ConstatAuditQualite.TypeConstat.ECART_MAJEUR).exists()
    return audit.score >= get_param_qualite("AGREMENT_SCORE_MIN") and not majeur


def rapport_audit_pdf(audit):
    from hse.services import _pdf

    blocs = [
        ("Audit", f"{audit.code} — {audit.get_type_audit_display()}"), ("Référentiel", audit.referentiel),
        ("Périmètre", audit.perimetre), ("Fournisseur", audit.fournisseur.name if audit.fournisseur_id else "—"),
        ("Organisme / auditeurs", f"{audit.organisme or 'ETSL'} · {audit.auditeur or '—'}"),
        ("Réalisé le", f"{audit.date_realisation:%d/%m/%Y}" if audit.date_realisation else "—"),
        ("Score", f"{audit.score} %" if audit.score is not None else "—"), ("Conclusion", audit.conclusion or "—"),
    ]
    if audit.agrement_accorde is not None:
        blocs.append(("Agrément qualité", "Accordé" if audit.agrement_accorde else "Refusé"))
    tableau = [["Constat", "Exigence", "Description", "NC"]] + [
        [c.get_type_constat_display(), c.exigence or "—", c.description[:90], c.nc.code if c.nc_id else "—"]
        for c in audit.constats.select_related("nc")
    ]
    return _pdf(f"Rapport d'audit {audit.code}", blocs, tableau if len(tableau) > 1 else None)


def cloturer_audit(audit, user):
    from .models import AuditQualite

    if audit.type_audit == AuditQualite.TypeAudit.FOURNISSEUR:
        audit.agrement_accorde = decision_agrement(audit)
        partenaire = audit.fournisseur
        if audit.agrement_accorde:
            partenaire.agree_qualite_jusqu = _ajouter_mois(audit.date_realisation or timezone.localdate(),
                                                           get_param_qualite("AGREMENT_DUREE_MOIS"))
        else:
            partenaire.agree_qualite_jusqu = None
        partenaire.save(update_fields=["agree_qualite_jusqu"])
    audit.statut = AuditQualite.Statut.CLOTURE
    audit.cloture_par, audit.cloture_le = user, timezone.now()
    audit.rapport = archiver(rapport_audit_pdf(audit), f"rapport-{audit.code}.pdf", f"Rapport d'audit {audit.code}", audit.code,
                             "qualite.auditqualite", audit.pk, user, ("audit", audit.referentiel), "Rapport d'audit clôturé")
    audit.save()
    return audit


def competences():
    """Matrice des compétences : qualifications soudage (M6) et habilitations RH (M9) par salarié."""
    from rh_paie.models import Employe, Qualification

    from .models import QualificationSoudeur

    jour = timezone.localdate()
    lignes = {}

    def ligne(e):
        return lignes.setdefault(e.pk, {"employe": str(e.pk), "code": e.code, "nom": e.nom_complet, "items": []})

    for q in QualificationSoudeur.objects.select_related("soudeur__employe").filter(soudeur__employe__isnull=False):
        ligne(q.soudeur.employe)["items"].append({
            "origine": "soudage", "code": q.code, "intitule": f"{q.get_norme_display()} {q.get_procede_display()} {q.position}".strip(),
            "date_validite": q.date_validite, "valide": bool(q.date_validite and q.date_validite >= jour),
        })
    for q in Qualification.objects.select_related("employe").exclude(employe__statut=Employe.Statut.SORTI):
        ligne(q.employe)["items"].append({
            "origine": "rh", "code": q.code, "intitule": q.intitule, "date_validite": q.date_validite, "valide": not q.expiree,
        })
    rows = sorted(lignes.values(), key=lambda r: r["code"])
    for r in rows:
        r["a_renouveler"] = sum(1 for i in r["items"] if not i["valide"])
    return rows


def bilan_qualite(annee):
    from .models import AuditQualite, ConstatAuditQualite, DocumentQualite, ProcessusQualite

    ind = indicateurs(annee)
    audits = AuditQualite.objects.filter(date_prevue__year=annee)
    realises = audits.exclude(statut=AuditQualite.Statut.PLANIFIE)
    processus = list(ProcessusQualite.objects.filter(actif=True))
    mesures = [p for p in processus if p.cible_atteinte is not None]
    jour = timezone.localdate()
    return {
        "annee": annee,
        "indicateurs": {k: (float(v) if hasattr(v, "quantize") else v) for k, v in ind.items()},
        "audits_planifies": audits.count(),
        "audits_realises": realises.count(),
        "score_moyen_audits": round(float(realises.aggregate(m=Avg("score"))["m"] or 0), 1) if realises.exists() else None,
        "ecarts_audit": ConstatAuditQualite.objects.filter(audit__in=audits, type_constat__in=ConstatAuditQualite.ECARTS).count(),
        "fournisseurs_audites": audits.filter(type_audit=AuditQualite.TypeAudit.FOURNISSEUR).count(),
        "processus": len(processus),
        "processus_cible_atteinte": sum(1 for p in mesures if p.cible_atteinte),
        "processus_mesures": len(mesures),
        "documents_en_vigueur": DocumentQualite.objects.filter(statut=DocumentQualite.Statut.APPROUVE).count(),
        "documents_revue_echue": DocumentQualite.objects.filter(statut=DocumentQualite.Statut.APPROUVE, date_revue__lt=jour).count(),
        "politique_en_vigueur": DocumentQualite.objects.filter(
            type_doc=DocumentQualite.TypeDoc.POLITIQUE, statut=DocumentQualite.Statut.APPROUVE).exists(),
    }


LIBELLES_BILAN = (
    ("audits_planifies", "Audits planifiés"), ("audits_realises", "Audits réalisés"), ("score_moyen_audits", "Score moyen des audits (%)"),
    ("ecarts_audit", "Écarts d'audit"), ("fournisseurs_audites", "Fournisseurs audités"), ("processus", "Processus actifs"),
    ("processus_cible_atteinte", "Processus à la cible"), ("documents_en_vigueur", "Documents en vigueur"),
    ("documents_revue_echue", "Documents à revue échue"),
)


def bilan_pdf(bilan, titre, revue=None):
    from hse.services import _pdf

    from .ecarts import LIBELLES_INDICATEURS

    blocs = [("Année", str(bilan["annee"])), ("Politique qualité en vigueur", "Oui" if bilan.get("politique_en_vigueur") else "Non")]
    if revue:
        blocs += [("Date de la revue", f"{revue.date_revue:%d/%m/%Y}"), ("Participants", revue.participants or "—"),
                  ("Conclusions", revue.conclusions or "—"), ("Décisions", revue.decisions or "—")]
    ind = bilan.get("indicateurs", {})
    tableau = [["Donnée d'entrée", "Valeur"]]
    tableau += [[lib, "—" if ind.get(cle) is None else f"{ind[cle]}{(' ' + u) if u else ''}"] for cle, lib, u in LIBELLES_INDICATEURS]
    tableau += [[lib, "—" if bilan.get(cle) is None else str(bilan[cle])] for cle, lib in LIBELLES_BILAN]
    return _pdf(titre, blocs, tableau)


def alertes_documents_qualite(band):
    from .models import DocumentQualite

    jour = timezone.localdate()
    horizon = jour + timedelta(days=int(get_param_qualite("DOC_REVUE_ALERTE_JOURS")))
    items = []
    for d in DocumentQualite.objects.filter(statut=DocumentQualite.Statut.APPROUVE, date_revue__lte=horizon):
        jours = (d.date_revue - jour).days
        items.append({
            "type": "revue_document", "code": f"{d.reference} v{d.version}", "libelle": f"{d.get_type_doc_display()} — {d.titre}",
            "date_echeance": d.date_revue, "bande": band(jours), "jours": jours, "statut": "expiree" if jours < 0 else "active",
        })
    return items
