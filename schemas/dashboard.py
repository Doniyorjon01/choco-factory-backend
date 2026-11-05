from datetime import date

from .common import ORMModel
from .documents import DocumentOut
from .products import ProductShort
from .stock import CapacityOut, StockItemOut


class ProducedItem(ORMModel):
    product: ProductShort
    qty: int


class TodayOut(ORMModel):
    produced: list[ProducedItem]
    produced_total: int
    documents_count: int


class SeriesOut(ORMModel):
    product: ProductShort
    # One value per day in `days`, same order
    values: list[int]
    total: int


class Production7dOut(ORMModel):
    days: list[date]
    series: list[SeriesOut]
    total: int


class DashboardOut(ORMModel):
    today: TodayOut
    low_stock: list[StockItemOut]
    capacity: list[CapacityOut]
    production_7d: Production7dOut
    recent_documents: list[DocumentOut]