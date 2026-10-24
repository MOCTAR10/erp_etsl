"""Référentiel FICTIF du jeu vitrine : clients, fournisseurs, affaires, pipeline, salariés, articles.

Noms inventés à consonance locale / pétrolière (aucune société réelle). Montants en FCFA (XAF), HT.
`debut` = nombre de mois avant le mois courant ; `duree` en mois.
"""

# (code, raison sociale, segment, scoring, origine, ville)
CLIENTS = [
    ("CLT-101", "Ogooué Petroleum Services", "petrole_gaz", 92, "appel_offres", "Port-Gentil"),
    ("CLT-102", "Mandji Offshore Exploration", "petrole_gaz", 88, "appel_offres", "Port-Gentil"),
    ("CLT-103", "Komo Gas Gabon", "petrole_gaz", 81, "relation", "Libreville"),
    ("CLT-104", "Nyanga Energy SA", "petrole_gaz", 76, "appel_offres", "Port-Gentil"),
    ("CLT-105", "Banio Upstream Gabon", "petrole_gaz", 70, "prospection", "Port-Gentil"),
    ("CLT-106", "Littoral Raffinage SA", "industrie", 84, "marche", "Port-Gentil"),
    ("CLT-107", "Terminal Pétrolier d'Akanda", "petrole_gaz", 79, "marche", "Libreville"),
    ("CLT-108", "Estuaire Gaz Industrie", "industrie", 68, "relation", "Libreville"),
    ("CLT-109", "Moanda Mining Services", "mines", 61, "prospection", "Moanda"),
    ("CLT-110", "Owendo Logistique Portuaire", "industrie", 66, "relation", "Libreville"),
    ("CLT-111", "Énergie Électrique de la Ngounié", "industrie", 58, "appel_offres", "Mouila"),
    ("CLT-112", "Rembo Oil & Gas Services", "petrole_gaz", 73, "relation", "Port-Gentil"),
]

# (code, raison sociale, ville)
FOURNISSEURS = [
    ("FRN-201", "Aciers & Tubes de l'Estuaire", "Libreville"),
    ("FRN-202", "Gabon Soudure Consommables", "Port-Gentil"),
    ("FRN-203", "Robinetterie Industrielle Atlantique", "Port-Gentil"),
    ("FRN-204", "Équipements de Protection Ogooué", "Libreville"),
    ("FRN-205", "Transports Nkoghe & Fils", "Port-Gentil"),
    ("FRN-206", "Lubrifiants et Carburants du Komo", "Libreville"),
    ("FRN-207", "CND Afrique Centrale", "Port-Gentil"),
    ("FRN-208", "Gaz Industriels de Port-Gentil", "Port-Gentil"),
    ("FRN-209", "Peintures & Revêtements Mbigou", "Libreville"),
    ("FRN-210", "Levage Services Gabon", "Port-Gentil"),
    ("FRN-211", "Électricité Industrielle Akanda", "Libreville"),
    ("FRN-212", "Brides & Raccords Bitam", "Libreville"),
    ("FRN-213", "Informatique & Réseaux Libreville", "Libreville"),
    ("FRN-214", "Échafaudages Ntoum", "Libreville"),
    ("FRN-215", "Restauration Base Vie Mayumba", "Port-Gentil"),
    ("FRN-216", "Intérim Industriel du Gabon", "Port-Gentil"),
]

# (code, désignation, type, unité, prix d'achat HT, stockable)
ARTICLES = [
    ("TUB-API5L-6", "Tube acier API 5L X52 6 pouces SCH40", "matiere", "M", 38_000, True),
    ("TUB-INOX-4", "Tube inox 316L 4 pouces SCH10S", "matiere", "M", 95_000, True),
    ("COU-6-90", "Coude 90° 6 pouces SCH40", "produit", "U", 42_000, True),
    ("BRI-6-300", "Bride WN 6 pouces classe 300", "produit", "U", 145_000, True),
    ("VAN-BS-4", "Vanne à boisseau sphérique 4 pouces classe 600", "produit", "U", 1_850_000, True),
    ("ELE-E7018", "Électrodes E7018 3,2 mm (carton 20 kg)", "consommable", "U", 95_000, True),
    ("FIL-ER70S", "Fil TIG ER70S-6 2,4 mm (boîte 5 kg)", "consommable", "U", 42_000, True),
    ("GAZ-ARGON", "Bouteille argon 50 L", "consommable", "U", 65_000, True),
    ("PEI-EPOXY", "Peinture époxy bi-composant (kit 20 L)", "consommable", "U", 180_000, True),
    ("EPI-SOUD", "Kit EPI soudeur (cagoule, gants, tablier)", "consommable", "U", 85_000, True),
    ("SRV-TRANSP", "Transport et manutention (forfait)", "service", "FF", 450_000, False),
    ("SRV-CND-RT", "Contrôle radiographique sous-traité (journée)", "service", "J", 650_000, False),
    ("SRV-ECHAF", "Location échafaudage (semaine)", "service", "FF", 380_000, False),
    ("SRV-BASEVIE", "Restauration et hébergement base vie (mois)", "service", "FF", 2_400_000, False),
    ("SRV-LOC-GR", "Location de matériel GLOBAL RENTAL (mois)", "service", "FF", 9_500_000, False),
    ("SRV-INTERIM", "Main-d'œuvre intérimaire qualifiée (homme-mois)", "service", "FF", 1_450_000, False),
    ("SRV-SOUSTR", "Sous-traitance montage et génie civil (forfait)", "service", "FF", 2_500_000, False),
]

# Approvisionnements d'affaire (un BC par affaire et par mois, fournisseur en rotation) : (fournisseur, [(article, part)])
PAQUETS_AFFAIRE = [
    ("FRN-201", [("TUB-API5L-6", "0.7"), ("TUB-INOX-4", "0.3")]),
    ("FRN-216", [("SRV-INTERIM", "1")]),
    ("FRN-212", [("BRI-6-300", "0.5"), ("COU-6-90", "0.5")]),
    ("FRN-214", [("SRV-SOUSTR", "0.7"), ("SRV-ECHAF", "0.3")]),
    ("FRN-207", [("SRV-CND-RT", "1")]),
    ("FRN-203", [("VAN-BS-4", "1")]),
    ("FRN-215", [("SRV-BASEVIE", "1")]),
    ("FRN-202", [("ELE-E7018", "0.6"), ("FIL-ER70S", "0.4")]),
]

# Petits achats de fonctionnement (2 par mois) : (fournisseur, article, quantité de base)
ACHATS_TYPES = [
    ("FRN-201", "TUB-API5L-6", 180),
    ("FRN-201", "TUB-INOX-4", 40),
    ("FRN-212", "BRI-6-300", 24),
    ("FRN-212", "COU-6-90", 30),
    ("FRN-203", "VAN-BS-4", 3),
    ("FRN-202", "ELE-E7018", 12),
    ("FRN-202", "FIL-ER70S", 15),
    ("FRN-208", "GAZ-ARGON", 20),
    ("FRN-209", "PEI-EPOXY", 6),
    ("FRN-204", "EPI-SOUD", 10),
    ("FRN-205", "SRV-TRANSP", 2),
    ("FRN-207", "SRV-CND-RT", 3),
    ("FRN-214", "SRV-ECHAF", 4),
    ("FRN-215", "SRV-BASEVIE", 1),
]

# Affaires : (clé, intitulé, client, type, montant HT, début (mois avant), durée (mois), site, GLOBAL RENTAL, clôturée)
AFFAIRES = [
    ("A01", "Remplacement manifold de production - champ Banio", "CLT-105", "chantier", 420_000_000, 11, 7, "Port-Gentil", False, True),
    ("A02", "Fabrication spools inox 316L - terminal de Port-Gentil", "CLT-106", "atelier", 180_000_000, 10, 5, "Port-Gentil", False, True),
    ("A03", "Maintenance annuelle tuyauteries - raffinerie du Littoral", "CLT-106", "maintenance", 264_000_000, 11, 12, "Port-Gentil", False, False),
    ("A04", "Location grues et engins - campagne de forage Mandji", "CLT-102", "fourniture", 243_000_000, 9, 9, "Port-Gentil", True, False),
    ("A05", "Réhabilitation pipeline 8 pouces - réseau Ogooué", "CLT-101", "chantier", 520_000_000, 8, 10, "Port-Gentil", False, False),
    ("A06", "Skids de comptage - plateforme offshore Nyanga", "CLT-104", "atelier", 312_000_000, 7, 6, "Port-Gentil", False, True),
    ("A07", "Mise à niveau réseau incendie - dépôt pétrolier d'Akanda", "CLT-107", "chantier", 198_000_000, 6, 6, "Libreville", False, False),
    ("A08", "Charpente et supports métalliques - station de pompage Komo", "CLT-103", "atelier", 96_000_000, 5, 3, "Libreville", False, True),
    ("A09", "Tie-in et raccordements - unité de traitement de gaz", "CLT-108", "chantier", 384_000_000, 4, 8, "Libreville", False, False),
    ("A10", "Contrat cadre soudure et inspection - Rembo", "CLT-112", "maintenance", 156_000_000, 3, 12, "Port-Gentil", False, False),
    ("A11", "Location compresseurs et groupes - arrêt technique", "CLT-101", "fourniture", 124_000_000, 2, 4, "Port-Gentil", True, False),
    ("A12", "Préfabrication racks tuyauterie - extension terminal Owendo", "CLT-110", "atelier", 230_000_000, 1, 5, "Libreville", False, False),
]

# Pipeline ouvert / perdu : (objet, client, étape, montant, probabilité, mois avant création, origine, motif de perte)
PIPELINE = [
    ("Extension réseau gaz combustible - Komo phase 2", "CLT-103", "prospection", 310_000_000, 15, 1, "relation", ""),
    ("Inspection et réparation bacs de stockage", "CLT-107", "prospection", 145_000_000, 20, 0, "prospection", ""),
    ("Tuyauterie process - usine de traitement Moanda", "CLT-109", "prospection", 260_000_000, 10, 2, "prospection", ""),
    ("Maintenance lignes d'injection d'eau - Nyanga", "CLT-104", "qualification", 420_000_000, 35, 2, "appel_offres", ""),
    ("Remplacement collecteurs vapeur - centrale de Mouila", "CLT-111", "qualification", 175_000_000, 30, 1, "appel_offres", ""),
    ("Location nacelles et chariots - campagne 2027", "CLT-102", "qualification", 96_000_000, 40, 0, "marche", ""),
    ("Préfabrication spools duplex - Ogooué", "CLT-101", "offre", 540_000_000, 55, 3, "appel_offres", ""),
    ("Contrat de maintenance pluriannuel - terminal Owendo", "CLT-110", "offre", 360_000_000, 60, 2, "appel_offres", ""),
    ("Raccordement nouveau puits - Banio Sud", "CLT-105", "negociation", 680_000_000, 75, 3, "appel_offres", ""),
    ("Réfection pomperie - raffinerie du Littoral", "CLT-106", "negociation", 215_000_000, 80, 1, "marche", ""),
    ("Fourniture et pose de pipe-racks - Estuaire", "CLT-108", "perdu", 190_000_000, 0, 8, "appel_offres", "Prix supérieur de 12 % au moins-disant"),
    ("Arrêt technique unité de dessalage", "CLT-112", "perdu", 140_000_000, 0, 6, "appel_offres", "Délai d'exécution jugé trop long par le client"),
    ("Habillage calorifuge - Mandji", "CLT-102", "perdu", 85_000_000, 0, 4, "relation", "Projet reporté sine die par le client"),
    ("Réseau air instrument - Komo", "CLT-103", "perdu", 62_000_000, 0, 9, "prospection", "Offre technique non retenue"),
]

# Salariés : (nom, prénom, sexe, fonction, catégorie, département, site, salaire de base, embauche (année) ou
# embauche récente en mois avant, terrain (compte opérateur + pointages))
EMPLOYES = [
    ("MBA", "Serge", "masculin", "Soudeur 6G", "ouvrier", "Atelier", "Port-Gentil", 620_000, 2016, True),
    ("NZE", "Hervé", "masculin", "Soudeur TIG", "ouvrier", "Atelier", "Port-Gentil", 580_000, 2018, True),
    ("OBAME", "Landry", "masculin", "Soudeur SMAW", "ouvrier", "Chantiers", "Port-Gentil", 540_000, 2019, True),
    ("ONDO", "Fabrice", "masculin", "Soudeur 6G", "ouvrier", "Chantiers", "Port-Gentil", 600_000, 2017, True),
    ("ESSONO", "Ghislain", "masculin", "Soudeur TIG", "ouvrier", "Atelier", "Libreville", 520_000, 2021, True),
    ("MOUELE", "Brice", "masculin", "Soudeur SMAW", "ouvrier", "Chantiers", "Libreville", 480_000, -9, True),
    ("KOUMBA", "Davy", "masculin", "Soudeur 6G", "ouvrier", "Chantiers", "Port-Gentil", 560_000, -6, True),
    ("MABIKA", "Ulrich", "masculin", "Soudeur TIG", "ouvrier", "Atelier", "Port-Gentil", 500_000, -3, True),
    ("NGUEMA", "Patrick", "masculin", "Tuyauteur", "ouvrier", "Chantiers", "Port-Gentil", 520_000, 2015, True),
    ("ELLA", "Rodrigue", "masculin", "Tuyauteur", "ouvrier", "Chantiers", "Port-Gentil", 490_000, 2018, True),
    ("MINTSA", "Arsène", "masculin", "Tuyauteur", "ouvrier", "Atelier", "Port-Gentil", 470_000, 2020, True),
    ("BEKALE", "Cédric", "masculin", "Tuyauteur", "ouvrier", "Chantiers", "Libreville", 450_000, 2022, True),
    ("EDZANG", "Thierry", "masculin", "Tuyauteur", "ouvrier", "Chantiers", "Libreville", 440_000, -7, True),
    ("MAPANGOU", "Wilfried", "masculin", "Tuyauteur", "ouvrier", "Atelier", "Libreville", 430_000, -4, True),
    ("BOUSSOUGOU", "Aimé", "masculin", "Tuyauteur", "ouvrier", "Chantiers", "Port-Gentil", 460_000, 2019, True),
    ("NZIENGUI", "Christian", "masculin", "Chef de chantier", "agent_maitrise", "Chantiers", "Port-Gentil", 1_150_000, 2012, True),
    ("MIHINDOU", "Roger", "masculin", "Chef de chantier", "agent_maitrise", "Chantiers", "Libreville", 1_050_000, 2014, True),
    ("MAKAYA", "Eric", "masculin", "Chef d'équipe atelier", "agent_maitrise", "Atelier", "Port-Gentil", 950_000, 2016, True),
    ("NGOMA", "Steve", "masculin", "Monteur ajusteur", "ouvrier", "Chantiers", "Port-Gentil", 400_000, 2021, True),
    ("BOUANGA", "Jordan", "masculin", "Monteur ajusteur", "ouvrier", "Chantiers", "Libreville", 380_000, 2023, True),
    ("IBINGA", "Marcel", "masculin", "Monteur ajusteur", "ouvrier", "Atelier", "Port-Gentil", 390_000, -1, True),
    ("MAVOUNGOU", "Guy", "masculin", "Chaudronnier", "ouvrier", "Atelier", "Port-Gentil", 500_000, 2017, True),
    ("NDJAVE", "Rufin", "masculin", "Chaudronnier", "ouvrier", "Atelier", "Libreville", 480_000, 2020, True),
    ("OYANE", "Prisca", "feminin", "Contrôleuse QA/QC", "technicien", "QA/QC", "Port-Gentil", 780_000, 2019, False),
    ("ASSOUMOU", "Bertrand", "masculin", "Inspecteur CND niveau 2", "technicien", "QA/QC", "Port-Gentil", 820_000, 2018, False),
    ("ENGONE", "Nadège", "feminin", "Animatrice HSE", "technicien", "HSE", "Port-Gentil", 720_000, 2020, False),
    ("ABESSOLO", "Franck", "masculin", "Superviseur HSE chantier", "agent_maitrise", "HSE", "Libreville", 880_000, 2017, False),
    ("OVONO", "Didier", "masculin", "Grutier", "ouvrier", "Logistique", "Port-Gentil", 560_000, 2016, False),
    ("MENGUE", "Alain", "masculin", "Conducteur d'engins", "ouvrier", "Logistique", "Port-Gentil", 500_000, 2019, False),
    ("NTOUTOUME", "Joël", "masculin", "Magasinier", "ouvrier", "Logistique", "Port-Gentil", 340_000, 2021, False),
    ("OWONO", "Martial", "masculin", "Mécanicien maintenance", "technicien", "Maintenance", "Port-Gentil", 560_000, 2015, False),
    ("ANGO", "Yannick", "masculin", "Électromécanicien", "technicien", "Maintenance", "Libreville", 540_000, 2022, False),
    ("NDONG ESSONO", "Clarisse", "feminin", "Comptable", "cadre", "Finance", "Libreville", 850_000, 2016, False),
    ("MOUNDOUNGA", "Sandrine", "feminin", "Assistante RH", "technicien", "Ressources humaines", "Libreville", 620_000, 2020, False),
    ("IVANGA", "Laurent", "masculin", "Acheteur", "technicien", "Achats", "Libreville", 700_000, 2018, False),
]

# Équipements (maintenance M8) : (désignation, catégorie, fabricant, modèle, site, mise en service (années), compteur)
ACTIFS = [
    ("Poste de soudage inverter 500 A n°1", "machine", "Miller", "XMT 500", "Atelier Port-Gentil", 4, "heures"),
    ("Poste de soudage inverter 500 A n°2", "machine", "Miller", "XMT 500", "Atelier Port-Gentil", 3, "heures"),
    ("Motosoudeuse diesel 400 A", "machine", "Lincoln", "Ranger 405", "Chantiers clients", 5, "heures"),
    ("Compresseur d'air mobile 10 bar", "machine", "Atlas Copco", "XAS 98", "Chantiers clients", 6, "heures"),
    ("Groupe électrogène 150 kVA", "machine", "SDMO", "J150K", "Base logistique Libreville", 7, "heures"),
    ("Cintreuse hydraulique 8 pouces", "machine", "Ercolina", "TB80", "Atelier Port-Gentil", 8, "aucun"),
    ("Grue mobile 50 t", "levage", "Liebherr", "LTM 1050", "Chantiers clients", 9, "heures"),
    ("Camion plateau grue 10 t", "engin", "Mercedes", "Actros 2641", "Base logistique Libreville", 6, "km"),
    ("Chariot télescopique 4 t", "engin", "Manitou", "MT 1440", "Dépôt Port-Gentil", 5, "heures"),
    ("Nacelle articulée 16 m", "levage", "Haulotte", "HA16", "Chantiers clients", 4, "heures"),
    ("Tour conventionnel 2 m", "machine", "Cazeneuve", "HB 725", "Atelier Port-Gentil", 12, "aucun"),
    ("Groupe de découpe plasma 125 A", "machine", "Hypertherm", "Powermax 125", "Atelier Port-Gentil", 3, "heures"),
]
