from rest_framework.pagination import PageNumberPagination


class StageProgressEntryPagination(PageNumberPagination):
    page_size = 25
    page_size_query_param = None
