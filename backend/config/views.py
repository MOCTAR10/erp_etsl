from django.http import JsonResponse
from django.db import connection


def health(request):
    """Simple liveness probe — also reports the DB connectivity status."""
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
        db_status = "ok"
    except Exception:
        db_status = "error"
    return JsonResponse({"status": "ok", "database": db_status})
