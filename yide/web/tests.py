import json
from decimal import Decimal

from django.test import TestCase

from .models import CartItem, Order, OrderItem, Product, SaleHistory


class CashierApiTests(TestCase):
    def setUp(self):
        self.product = Product.objects.create(
            barcode="690000000001",
            name="测试铅笔",
            price=Decimal("2.50"),
            stock=2,
        )

    def test_get_product_by_barcode_returns_error_when_missing(self):
        response = self.client.get("/get_product_by_barcode/", {"barcode": "missing"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "error")
        self.assertEqual(response.json()["message"], "未找到商品")

    def test_add_item_allows_exact_stock_and_does_not_mutate_on_shortage(self):
        first = self.client.get("/add_item/", {"barcode": self.product.barcode})
        second = self.client.get("/add_item/", {"barcode": self.product.barcode})
        third = self.client.get("/add_item/", {"barcode": self.product.barcode})

        self.assertEqual(first.json()["status"], "success")
        self.assertEqual(second.json()["status"], "success")
        self.assertEqual(third.json()["status"], "error")
        self.assertEqual(CartItem.objects.get(product=self.product).quantity, 2)

    def test_checkout_rejects_insufficient_stock_without_negative_inventory(self):
        CartItem.objects.create(product=self.product, quantity=3)

        response = self.client.get("/checkout_cart/")

        self.product.refresh_from_db()
        self.assertEqual(response.json()["status"], "error")
        self.assertIn("库存不足", response.json()["message"])
        self.assertEqual(self.product.stock, 2)
        self.assertEqual(SaleHistory.objects.count(), 0)
        self.assertEqual(CartItem.objects.count(), 1)

    def test_today_stats_sums_line_totals_not_unit_prices(self):
        SaleHistory.objects.create(product_name="测试铅笔", price=Decimal("2.50"), quantity=3)
        SaleHistory.objects.create(product_name="测试橡皮", price=Decimal("1.20"), quantity=2)

        response = self.client.get("/get_today_stats/")

        self.assertEqual(response.json()["status"], "success")
        self.assertEqual(response.json()["total_amount"], 9.9)
        self.assertEqual(response.json()["today_count"], 5)

    def test_search_order_returns_fail_when_no_match(self):
        response = self.client.get("/api/search_order/", {"key": "不存在"})

        self.assertEqual(response.json()["status"], "fail")
        self.assertEqual(response.json()["msg"], "未找到匹配订单")

    def test_verify_order_rejects_insufficient_stock_without_completing_order(self):
        self.product.stock = 1
        self.product.save(update_fields=["stock"])
        order = Order.objects.create(customer_name="张三", total_price=Decimal("5.00"), status=0)
        OrderItem.objects.create(order=order, product=self.product, count=2)

        response = self.client.post(
            "/api/verify_order/",
            data=json.dumps({"id": order.id}),
            content_type="application/json",
        )

        self.product.refresh_from_db()
        order.refresh_from_db()
        self.assertEqual(response.json()["status"], "fail")
        self.assertIn("库存不足", response.json()["msg"])
        self.assertEqual(self.product.stock, 1)
        self.assertEqual(order.status, 0)
        self.assertEqual(SaleHistory.objects.count(), 0)


class InventoryApiTests(TestCase):
    def test_quick_add_product_url_creates_stocked_product(self):
        response = self.client.get(
            "/quick_add_product/",
            {"barcode": "690000000002", "name": "测试本", "price": "3.80", "stock": "4"},
        )

        product = Product.objects.get(barcode="690000000002")
        self.assertEqual(response.json()["status"], "success")
        self.assertEqual(product.stock, 4)
        self.assertEqual(product.price, Decimal("3.80"))

    def test_submit_order_recalculates_total_and_validates_stock(self):
        response = self.client.post(
            "/api/submit_order/",
            data=json.dumps({
                "name": "李四",
                "total": "0.01",
                "cart": [{"id": Product.objects.create(
                    barcode="690000000003",
                    name="测试钢笔",
                    price=Decimal("8.00"),
                    stock=5,
                ).id, "num": 2}],
            }),
            content_type="application/json",
        )

        order = Order.objects.get(customer_name="李四")
        self.assertEqual(response.json()["status"], "success")
        self.assertEqual(order.total_price, Decimal("16.00"))
        self.assertEqual(order.items.get().count, 2)
