"""Intégration réelle du stockage objet S3 (SeaweedFS ; MinIO historiquement) : aller-retour, URL signée, accès refusé.

Les tests utilisent un stockage en mémoire (config/settings_test.py) pour la vitesse ; ce test vérifie que la
configuration S3 de production fonctionne vraiment. Activé par MINIO_INTEGRATION=1 (CI : MinIO démarré par le job).
"""

import os
import unittest
import urllib.error
import urllib.request
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
            # La GED sert les fichiers par URL présignée (SigV4) ; sans signature, l'accès doit être refusé.
            url = storage.url(saved)
            self.assertIn("X-Amz-Signature", url)
            self.assertEqual(urllib.request.urlopen(url).read(), b"etsl-minio-ok")
            with self.assertRaises(urllib.error.HTTPError) as ctx:
                urllib.request.urlopen(url.split("?")[0])
            self.assertEqual(ctx.exception.code, 403)
        finally:
            storage.delete(saved)
        self.assertFalse(storage.exists(saved))
