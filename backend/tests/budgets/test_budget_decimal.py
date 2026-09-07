from decimal import Decimal

import pytest

from apps.budgets.api.serializers import BudgetItemSerializer
from tests.factories.budgets import BudgetItemFactory


@pytest.mark.parametrize(
    "quantity,price,exact,money",
    [
        ("2.5000", "10.00", "25.000000", "25.00"),
        ("0.3333", "3.00", "0.999900", "1.00"),
        ("25.0000", "520.00", "13000.000000", "13000.00"),
        ("1.0050", "1.00", "1.005000", "1.01"),
        ("0.0001", "0.01", "0.000001", "0.00"),
        ("1.0000", "0.00", "0.000000", "0.00"),
        (
            "9999999999.9999",
            "999999999999.99",
            "9999999999999800000000.000001",
            "9999999999999800000000.00",
        ),
    ],
)
def test_total_preserves_decimal_precision_and_rounds_only_for_api(
    quantity, price, exact, money
):
    item = BudgetItemFactory.build(
        quantity=Decimal(quantity), unit_price=Decimal(price)
    )
    assert isinstance(item.total, Decimal)
    assert item.total == Decimal(exact)
    data = BudgetItemSerializer(item).data
    assert data["quantity"] == quantity
    assert data["unit_price"] == price
    assert data["total"] == money
    assert Decimal(data["total"]) == Decimal(money)
    assert item.total == Decimal(
        exact
    )  # Representation never changes the stored inputs.
