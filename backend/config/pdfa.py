"""PDF/A par post-traitement Ghostscript (EX-G-08).

ReportLab (exports) et les PDF versés en GED ne sont pas, en général, au profil PDF/A. Ce module les convertit en
PDF/A (2b par défaut — norme paramétrable : 1b, 2b, 3b) avec Ghostscript (`-dPDFA=N`, profil ICC sRGB en
OutputIntent, `-dPDFACompatibilityPolicy=1`).

Dégradation propre : Ghostscript absent, fichier non PDF, PDF signé numériquement (une conversion détruirait la
signature PAdES), échec ou délai dépassé ⇒ le contenu d'origine est conservé tel quel et le statut renvoyé le dit
(jamais d'exception vers l'appelant).

Réglages (env) : `GHOSTSCRIPT_BIN` (défaut `gs`), `PDFA_ICC_PROFILE` (profil sRGB ; défaut : recherche dans les
emplacements usuels), `PDFA_ACTIF` (interrupteur global, faux en tests), `PDFA_TIMEOUT_S`.
"""

import logging
import os
import shutil
import subprocess
import tempfile

from django.conf import settings

logger = logging.getLogger(__name__)

NORMES = ("1b", "2b", "3b")
NORME_DEFAUT = "2b"

# Statuts de conversion (stockés sur la version GED, renvoyés aux appelants).
CONVERTI = "converti"
DESACTIVE = "desactive"
NON_PDF = "non_pdf"
PDF_SIGNE = "pdf_signe"
GS_ABSENT = "gs_absent"
ECHEC = "echec"

ICC_CANDIDATS = (
    "/usr/share/color/icc/ghostscript/srgb.icc",
    "/usr/share/color/icc/ghostscript/default_rgb.icc",
    "/usr/share/color/icc/sRGB.icc",
    "/usr/share/color/icc/colord/sRGB.icc",
)


def ghostscript():
    """Chemin de l'exécutable Ghostscript, ou None s'il n'est pas installé."""
    return shutil.which(getattr(settings, "GHOSTSCRIPT_BIN", "gs") or "gs")


def profil_icc():
    chemin = getattr(settings, "PDFA_ICC_PROFILE", "") or ""
    if chemin and os.path.isfile(chemin):
        return chemin
    for candidat in ICC_CANDIDATS:
        if os.path.isfile(candidat):
            return candidat
    return None


def est_pdf(contenu):
    return contenu[:1024].lstrip().startswith(b"%PDF-")


def est_signe(contenu):
    """PDF portant une signature numérique (dictionnaire /Sig avec /ByteRange)."""
    return b"/ByteRange" in contenu


def _echapper_ps(texte):
    return texte.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def _definition_pdfa(icc):
    """Fichier PostScript posant l'OutputIntent sRGB exigé par PDF/A (adapté de `PDFA_def.ps` de Ghostscript)."""
    return (
        "%!\n"
        f"/ICCProfile ({_echapper_ps(icc)}) def\n"
        "[/_objdef {icc_PDFA} /type /stream /OBJ pdfmark\n"
        "[{icc_PDFA} << /N 3 >> /PUT pdfmark\n"
        "[{icc_PDFA} ICCProfile (r) file /PUT pdfmark\n"
        "[/_objdef {OutputIntent_PDFA} /type /dict /OBJ pdfmark\n"
        "[{OutputIntent_PDFA} << /Type /OutputIntent /S /GTS_PDFA1 /DestOutputProfile {icc_PDFA}"
        " /OutputConditionIdentifier (sRGB) /Info (sRGB IEC61966-2.1) >> /PUT pdfmark\n"
        "[{Catalog} << /OutputIntents [ {OutputIntent_PDFA} ] >> /PUT pdfmark\n"
    )


def convertir_pdfa(contenu, norme=NORME_DEFAUT):
    """Convertit `contenu` (bytes) en PDF/A-`norme`. Renvoie `(octets, statut)` ; en cas d'impossibilité, les
    octets d'origine sont renvoyés inchangés avec le statut correspondant."""
    if not getattr(settings, "PDFA_ACTIF", True) or norme not in NORMES:
        return contenu, DESACTIVE
    if not est_pdf(contenu):
        return contenu, NON_PDF
    if est_signe(contenu):
        return contenu, PDF_SIGNE
    gs = ghostscript()
    if not gs:
        logger.warning("PDF/A : Ghostscript introuvable, PDF conservé tel quel.")
        return contenu, GS_ABSENT
    with tempfile.TemporaryDirectory(prefix="pdfa_") as dossier:
        entree = os.path.join(dossier, "entree.pdf")
        sortie = os.path.join(dossier, "sortie.pdf")
        with open(entree, "wb") as f:
            f.write(contenu)
        commande = [
            gs, "-q", "-dBATCH", "-dNOPAUSE", "-dNOOUTERSAVE", "-dSAFER",
            f"-dPDFA={norme[0]}", "-dPDFACompatibilityPolicy=1", "-sDEVICE=pdfwrite",
            "-sColorConversionStrategy=RGB", "-sProcessColorModel=DeviceRGB",
            f"-sOutputFile={sortie}",
        ]
        icc = profil_icc()
        if icc:
            definition = os.path.join(dossier, "pdfa_def.ps")
            with open(definition, "w", encoding="ascii", errors="replace") as f:
                f.write(_definition_pdfa(icc))
            commande[1:1] = [f"--permit-file-read={icc}"]
            commande += [definition]
        commande.append(entree)
        try:
            subprocess.run(
                commande, check=True, capture_output=True,
                timeout=int(getattr(settings, "PDFA_TIMEOUT_S", 120)),
            )
            with open(sortie, "rb") as f:
                resultat = f.read()
        except (OSError, subprocess.SubprocessError) as exc:
            logger.warning("PDF/A : conversion Ghostscript en échec (%s), PDF conservé tel quel.", exc)
            return contenu, ECHEC
    if not est_pdf(resultat):
        return contenu, ECHEC
    return resultat, CONVERTI


def est_pdfa(contenu):
    """Contrôle sommaire : métadonnées XMP `pdfaid:part` présentes (déclaration du profil PDF/A)."""
    return b"pdfaid:part" in contenu or b"pdfaid:part=" in contenu
