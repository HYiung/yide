from django.core.exceptions import ValidationError
from django.db import transaction

from .models import Order, Product, SaleHistory


def complete_order(order):
    """Atomically complete a pending order, deduct stock, and write sales history."""
    if order.status == 1:
        return

    with transaction.atomic():
        locked_order = Order.objects.select_for_update().get(pk=order.pk)
        if locked_order.status == 1:
            return

        locked_items = []
        for item in locked_order.items.select_related('product').all():
            product = Product.objects.select_for_update().get(pk=item.product_id)
            if product.stock < item.count:
                raise ValidationError(
                    f'{product.name} 库存不足，当前库存 {product.stock}，需要 {item.count}'
                )
            locked_items.append((item, product))

        for item, product in locked_items:
            product.stock -= item.count
            product.save(update_fields=['stock'])
            SaleHistory.objects.create(
                product_name=product.name,
                price=product.price,
                quantity=item.count,
            )

        locked_order.status = 1
        locked_order.save(update_fields=['status'])
