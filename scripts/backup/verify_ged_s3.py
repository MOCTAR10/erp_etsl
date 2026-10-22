"""Vérifie que les fichiers GED référencés en base existent dans un bucket S3 et gardent leur SHA-256 (CL-OM-11).

Lecture seule (SELECT + GET S3). Utilisé par restore_test_pgbackrest.sh sur la base RESTAURÉE et le bucket de
sauvegarde ; utilisable seul pour un test à blanc sur l'environnement de dev.

Variables : DATABASE_URL (postgresql://…), S3_ENDPOINT, S3_BUCKET, S3_ACCESS_KEY, S3_SECRET_KEY, S3_REGION (option).
Usage : python verify_ged_s3.py [--sample 50] [--json]
"""

import argparse
import hashlib
import json
import os
import sys
import time


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sample", type=int, default=50, help="nombre de versions tirées au hasard")
    parser.add_argument("--json", action="store_true", help="sortie JSON seule (pour le rapport)")
    args = parser.parse_args()

    import boto3
    import psycopg
    from botocore.config import Config

    t0 = time.time()
    with psycopg.connect(os.environ["DATABASE_URL"]) as conn:
        total = conn.execute("select count(*) from documents_version").fetchone()[0]
        lignes = conn.execute(
            "select file, sha256, size from documents_version where file <> '' order by random() limit %s",
            (args.sample,),
        ).fetchall()

    s3 = boto3.client(
        "s3",
        endpoint_url=os.environ.get("S3_ENDPOINT") or None,
        aws_access_key_id=os.environ.get("S3_ACCESS_KEY"),
        aws_secret_access_key=os.environ.get("S3_SECRET_KEY"),
        region_name=os.environ.get("S3_REGION", "us-east-1"),
        config=Config(signature_version="s3v4"),
    )
    bucket = os.environ["S3_BUCKET"]
    absents, alteres = [], []
    for cle, sha, _taille in lignes:
        try:
            corps = s3.get_object(Bucket=bucket, Key=cle)["Body"].read()
        except Exception:  # noqa: BLE001 — absent ou inaccessible : compté comme absent
            absents.append(cle)
            continue
        if hashlib.sha256(corps).hexdigest() != sha:
            alteres.append(cle)

    rapport = {
        "versions_en_base": total,
        "echantillon": len(lignes),
        "absents": len(absents),
        "alteres": len(alteres),
        "exemples_absents": absents[:10],
        "exemples_alteres": alteres[:10],
        "duree_s": round(time.time() - t0, 2),
        "resultat": "OK" if not absents and not alteres else "ECHEC",
    }
    if args.json:
        print(json.dumps(rapport, ensure_ascii=False))
    else:
        for k, v in rapport.items():
            print(f"{k:18} {v}")
    return 0 if rapport["resultat"] == "OK" else 1


if __name__ == "__main__":
    sys.exit(main())
