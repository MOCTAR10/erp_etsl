"""Intégration réelle MinIO / S3 (aller-retour d'un fichier).

Les tests utilisent un stockage en mémoire (config/settings_test.py) pour la vitesse ; ce test vérifie que la
configuration S3 de production fonctionne vraiment. Activé par MINIO_INTEGRATION=1 (CI : MinIO démarré par le job).
"""

import os
import unittest
import uuid

from django.core.files.base import ContentFile
from django.test import SimpleTestCase


@unittest.skipUnless(os.environ.get("MINIO_INTEGRATION") == "1", "MINIO_INTEGRATION=1 pour tester le vrai MinIO")
class MinioIntegrationTests(SimpleTestCase):
    def test_aller_retour_s3(self):
        from storages.backends.s3 import S3Storage

        storage = S3Storage()
        name = f"ci-integration/{uuid.uuid4().hex}.txt"
        saved = storage.save(name, ContentFile(b"etsl-minio-ok"))
        try:
            with storage.open(saved) as fh:
                self.assertEqual(fh.read(), b"etsl-minio-ok")
        finally:
            storage.delete(saved)
        self.assertFalse(storage.exists(saved))
