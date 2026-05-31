import json
from decimal import Decimal

from django.test import TestCase

from .models import CartItem, Order, OrderItem, Product, SaleHistory


class ProductLookupTests(TestCase):
    def test_missing_barcode_returns_json_error(self):
        response = self.client.get('/get_product_by_barcode/', {'barcode': 'missing'})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['status'], 'error')


class CartFlowTests(TestCase):
    def test_add_item_allows_last_stock_item_and_does_not_overfill_cart(self):
        Product.objects.create(barcode='6900001', name='铅笔', price=Decimal('2.00'), stock=1)

        first_response = self.client.get('/add_item/', {'barcode': '6900001'})
        self.assertEqual(first_response.json()['status'], 'success')
        self.assertEqual(first_response.json()['current_qty'], 1)

        second_response = self.client.get('/add_item/', {'barcode': '6900001'})
        self.assertEqual(second_response.json()['status'], 'error')
        self.assertEqual(CartItem.objects.get(product__barcode='6900001').quantity, 1)

    def test_checkout_refuses_to_create_negative_stock(self):
        product = Product.objects.create(barcode='6900002', name='橡皮', price=Decimal('1.50'), stock=1)
        CartItem.objects.create(product=product, quantity=2)

        response = self.client.get('/checkout_cart/')

        product.refresh_from_db()
        self.assertEqual(response.json()['status'], 'error')
        self.assertEqual(product.stock, 1)
        self.assertEqual(SaleHistory.objects.count(), 0)

    def test_checkout_short_later_item_does_not_partially_commit(self):
        in_stock = Product.objects.create(barcode='6900101', name='中性笔', price=Decimal('3.00'), stock=5)
        short_stock = Product.objects.create(barcode='6900102', name='便签', price=Decimal('2.00'), stock=1)
        CartItem.objects.create(product=in_stock, quantity=2)
        CartItem.objects.create(product=short_stock, quantity=2)

        response = self.client.get('/checkout_cart/')

        in_stock.refresh_from_db()
        short_stock.refresh_from_db()
        self.assertEqual(response.json()['status'], 'error')
        self.assertEqual(in_stock.stock, 5)
        self.assertEqual(short_stock.stock, 1)
        self.assertEqual(SaleHistory.objects.count(), 0)
        self.assertEqual(CartItem.objects.count(), 2)


class SalesStatsTests(TestCase):
    def test_today_stats_multiplies_price_by_quantity(self):
        SaleHistory.objects.create(product_name='笔记本', price=Decimal('3.50'), quantity=2)
        SaleHistory.objects.create(product_name='钢笔', price=Decimal('5.00'), quantity=3)

        response = self.client.get('/get_today_stats/')

        self.assertEqual(response.json()['total_amount'], 22.0)
        self.assertEqual(response.json()['today_count'], 5)


class OrderFlowTests(TestCase):
    def test_submit_order_recomputes_total_and_verify_checks_stock(self):
        product = Product.objects.create(barcode='6900003', name='尺子', price=Decimal('4.00'), stock=2)

        submit_response = self.client.post(
            '/api/submit_order/',
            data=json.dumps({
                'name': '张三',
                'cart': [{'id': product.id, 'num': 2}],
                'total': '0.01',
            }),
            content_type='application/json',
        )
        self.assertEqual(submit_response.json()['status'], 'success')
        self.assertEqual(submit_response.json()['total'], '8.00')

        product.stock = 1
        product.save(update_fields=['stock'])
        order = Order.objects.get()
        verify_response = self.client.post(
            '/api/verify_order/',
            data=json.dumps({'id': order.id}),
            content_type='application/json',
        )

        product.refresh_from_db()
        order.refresh_from_db()
        self.assertEqual(verify_response.json()['status'], 'fail')
        self.assertEqual(product.stock, 1)
        self.assertEqual(order.status, 0)

    def test_verify_order_short_later_item_does_not_partially_commit(self):
        in_stock = Product.objects.create(barcode='6900201', name='文件夹', price=Decimal('6.00'), stock=4)
        short_stock = Product.objects.create(barcode='6900202', name='胶带', price=Decimal('5.00'), stock=1)
        order = Order.objects.create(customer_name='李四', total_price=Decimal('17.00'), status=0)
        OrderItem.objects.create(order=order, product=in_stock, count=2)
        OrderItem.objects.create(order=order, product=short_stock, count=2)

        response = self.client.post(
            '/api/verify_order/',
            data=json.dumps({'id': order.id}),
            content_type='application/json',
        )

        in_stock.refresh_from_db()
        short_stock.refresh_from_db()
        order.refresh_from_db()
        self.assertEqual(response.json()['status'], 'fail')
        self.assertEqual(in_stock.stock, 4)
        self.assertEqual(short_stock.stock, 1)
        self.assertEqual(order.status, 0)
        self.assertEqual(SaleHistory.objects.count(), 0)
