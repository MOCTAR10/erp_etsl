from rest_framework.pagination import PageNumberPagination


class StandardPagination(PageNumberPagination):
    """Pagination par défaut : 20 lignes, `?page_size=N` accepté jusqu'à 500.

    Le front envoie `?page_size=` depuis l'origine ; sans `page_size_query_param`
    DRF l'ignorait et toute liste restait tronquée à 20 lignes.
    """

    page_size = 20
    page_size_query_param = "page_size"
    max_page_size = 500
