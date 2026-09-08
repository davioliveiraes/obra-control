from rest_framework.pagination import PageNumberPagination


class ExpensePagination(PageNumberPagination):
    page_size = 25
    page_size_query_param = None


class RevenuePagination(PageNumberPagination):
    page_size = 25
    page_size_query_param = None
