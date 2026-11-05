from typing import TypeVar

from fastapi import Query
from fastapi_pagination import Page
from fastapi_pagination.customization import CustomizedPage, UseParamsFields

T = TypeVar("T")

# Har bir roʻyxat sahifalanadi: sukut 20, ko'pi bilan 100 qator.
CustomPage = CustomizedPage[
    Page[T],
    UseParamsFields(size=Query(20, ge=1, le=100)),
]
