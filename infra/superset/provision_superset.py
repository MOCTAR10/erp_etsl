"""Provisionnement idempotent de Superset (Couche D, CL-OM-12) — lancé par le service `superset-init` du compose de prod.

1. Déclare la base « ETSL — datamarts » : le RÉPLICA PostgreSQL (jamais le primaire), schéma `marts` écrit par dbt.
2. Crée un jeu de données par mart dbt (`dbt/models/marts/dm_*.sql`, monté en lecture seule) et en relit les colonnes.

Rejouable : une base ou un jeu de données existant est mis à jour, jamais dupliqué. Un mart pas encore construit
(premier démarrage avant le premier `dbt build`) est déclaré et sera relu au démarrage suivant.
"""

import os
import sys
from pathlib import Path

from superset.app import create_app

NOM_BASE = "ETSL — datamarts (réplica)"
SCHEMA = os.environ.get("ETSL_MARTS_SCHEMA", "marts")
DOSSIER_MARTS = Path(os.environ.get("ETSL_DBT_MARTS", "/app/etsl_dbt/marts"))


def marts():
    return sorted(p.stem for p in DOSSIER_MARTS.glob("dm_*.sql"))


def main():
    uri = os.environ.get("ETSL_MARTS_URI")
    if not uri:
        print("ETSL_MARTS_URI absent : provisionnement Superset ignoré", file=sys.stderr)
        return 1
    app = create_app()
    with app.app_context():
        from superset import db
        from superset.connectors.sqla.models import SqlaTable
        from superset.models.core import Database

        base = db.session.query(Database).filter_by(database_name=NOM_BASE).one_or_none()
        if base is None:
            base = Database(database_name=NOM_BASE)
            db.session.add(base)
        base.set_sqlalchemy_uri(uri)
        base.expose_in_sqllab = True
        base.allow_dml = False  # lecture seule : la Couche D ne réécrit jamais l'ERP
        db.session.flush()
        for nom in marts():
            ds = db.session.query(SqlaTable).filter_by(database_id=base.id, schema=SCHEMA, table_name=nom).one_or_none()
            if ds is None:
                ds = SqlaTable(table_name=nom, schema=SCHEMA, database=base)
                db.session.add(ds)
                db.session.flush()
            try:
                ds.fetch_metadata()
                etat = "ok"
            except Exception as exc:  # mart pas encore construit par dbt : relu au prochain démarrage
                etat = f"en attente ({str(exc).splitlines()[0][:120]})"
            print(f"  jeu de données {SCHEMA}.{nom} : {etat}")
        db.session.commit()
    print(f"Superset provisionné : base « {NOM_BASE} », {len(marts())} jeux de données")
    return 0


if __name__ == "__main__":
    sys.exit(main())
