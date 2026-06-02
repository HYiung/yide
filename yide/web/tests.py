import json
from decimal import Decimal

from unittest.mock import Mock, patch

from django.test import TestCase, override_settings

from .models import AdminUser, CartItem, Order, OrderItem, Product, SaleHistory


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


class InventoryApiTests(TestCase):
    def test_low_stock_products_returns_threshold_matches(self):
        low = Product.objects.create(barcode='6900301', name='作业本', price=Decimal('2.50'), stock=2)
        Product.objects.create(barcode='6900302', name='笔芯', price=Decimal('1.00'), stock=8)

        response = self.client.get('/api/low_stock_products/', {'threshold': 5})

        data = response.json()
        self.assertEqual(data['status'], 'success')
        self.assertEqual(data['threshold'], 5)
        self.assertEqual([item['id'] for item in data['list']], [low.id])

    def test_pending_orders_includes_items_for_dashboard(self):
        product = Product.objects.create(barcode='6900303', name='便利贴', price=Decimal('3.00'), stock=5)
        order = Order.objects.create(customer_name='王五', total_price=Decimal('6.00'), status=0)
        OrderItem.objects.create(order=order, product=product, count=2)

        response = self.client.get('/api/pending_orders/')

        data = response.json()
        self.assertEqual(data['status'], 'success')
        self.assertEqual(data['list'][0]['customer_name'], '王五')
        self.assertEqual(data['list'][0]['items'][0]['name'], '便利贴')
        self.assertEqual(data['list'][0]['items'][0]['count'], 2)

    def test_submit_order_aggregates_duplicate_product_lines(self):
        product = Product.objects.create(barcode='6900304', name='铅笔', price=Decimal('1.00'), stock=2)

        response = self.client.post(
            '/api/submit_order/',
            data=json.dumps({
                'name': '赵六',
                'cart': [{'id': product.id, 'num': 2}, {'id': product.id, 'num': 1}],
                'total': '3.00',
            }),
            content_type='application/json',
        )

        self.assertEqual(response.json()['status'], 'fail')
        self.assertEqual(Order.objects.count(), 0)



class QuickAddProductTests(TestCase):
    def test_quick_add_rejects_missing_required_fields(self):
        response = self.client.get('/quick_add_product/', {'barcode': '', 'name': '本子', 'price': '2.00', 'stock': 1})

        self.assertEqual(response.json()['status'], 'fail')
        self.assertEqual(Product.objects.count(), 0)

    def test_quick_add_rejects_invalid_price_or_stock(self):
        bad_price = self.client.get('/quick_add_product/', {'barcode': '6900401', 'name': '本子', 'price': 'abc', 'stock': 1})
        bad_stock = self.client.get('/quick_add_product/', {'barcode': '6900401', 'name': '本子', 'price': '2.00', 'stock': 0})

        self.assertEqual(bad_price.json()['status'], 'fail')
        self.assertEqual(bad_stock.json()['status'], 'fail')
        self.assertEqual(Product.objects.count(), 0)

    def test_quick_add_creates_new_product(self):
        response = self.client.get('/quick_add_product/', {
            'barcode': '6900402',
            'name': '数学本',
            'price': '2.50',
            'stock': 3,
        })

        product = Product.objects.get(barcode='6900402')
        self.assertEqual(response.json()['status'], 'success')
        self.assertTrue(response.json()['is_new'])
        self.assertEqual(product.name, '数学本')
        self.assertEqual(product.price, Decimal('2.50'))
        self.assertEqual(product.stock, 3)

    def test_quick_add_updates_existing_product_and_increases_stock(self):
        product = Product.objects.create(barcode='6900403', name='旧名字', price=Decimal('1.00'), stock=2)

        response = self.client.get('/quick_add_product/', {
            'barcode': product.barcode,
            'name': '新名字',
            'price': '1.50',
            'stock': 4,
        })

        product.refresh_from_db()
        self.assertEqual(response.json()['status'], 'success')
        self.assertFalse(response.json()['is_new'])
        self.assertEqual(product.name, '新名字')
        self.assertEqual(product.price, Decimal('1.50'))
        self.assertEqual(product.stock, 6)


class MallProductsTests(TestCase):
    def test_mall_products_only_returns_in_stock_products(self):
        in_stock = Product.objects.create(barcode='6900501', name='钢笔', price=Decimal('5.00'), stock=2, category='pens')
        Product.objects.create(barcode='6900502', name='售罄笔', price=Decimal('3.00'), stock=0, category='pens')

        response = self.client.get('/api/mall_products/', {'category': 'all'})

        ids = [item['id'] for item in response.json()['list']]
        self.assertEqual(ids, [in_stock.id])

    def test_mall_products_filters_by_category(self):
        book = Product.objects.create(barcode='6900503', name='童话书', price=Decimal('8.00'), stock=3, category='books')
        Product.objects.create(barcode='6900504', name='圆珠笔', price=Decimal('2.00'), stock=3, category='pens')

        response = self.client.get('/api/mall_products/', {'category': 'books'})

        data = response.json()['list']
        self.assertEqual(len(data), 1)
        self.assertEqual(data[0]['id'], book.id)
        self.assertEqual(data[0]['category'], 'books')


class SearchOrderTests(TestCase):
    def test_search_order_rejects_blank_keyword(self):
        response = self.client.get('/api/search_order/', {'key': '   '})

        self.assertEqual(response.json()['status'], 'fail')

    def test_search_order_finds_pending_order_by_name_and_includes_items(self):
        product = Product.objects.create(barcode='6900601', name='笔袋', price=Decimal('9.00'), stock=4)
        order = Order.objects.create(customer_name='孙七', total_price=Decimal('18.00'), status=0)
        OrderItem.objects.create(order=order, product=product, count=2)

        response = self.client.get('/api/search_order/', {'key': '孙'})

        data = response.json()
        self.assertEqual(data['status'], 'success')
        self.assertEqual(data['order']['id'], order.id)
        self.assertEqual(data['order']['items'][0]['name'], '笔袋')

    def test_search_order_finds_by_order_sn_suffix_and_excludes_completed(self):
        pending = Order.objects.create(customer_name='周八', total_price=Decimal('1.00'), status=0)
        Order.objects.create(customer_name='周八', total_price=Decimal('1.00'), status=1)

        response = self.client.get('/api/search_order/', {'key': pending.order_sn[-4:]})

        self.assertEqual(response.json()['status'], 'success')
        self.assertEqual(response.json()['order']['id'], pending.id)


class VerifyOrderMoreTests(TestCase):
    def test_verify_order_requires_post(self):
        response = self.client.get('/api/verify_order/')

        self.assertEqual(response.json()['status'], 'fail')

    def test_verify_order_rejects_invalid_json(self):
        response = self.client.post('/api/verify_order/', data='{bad-json', content_type='application/json')

        self.assertEqual(response.json()['status'], 'fail')

    def test_verify_order_rejects_missing_or_completed_order(self):
        completed = Order.objects.create(customer_name='吴九', total_price=Decimal('1.00'), status=1)

        missing_response = self.client.post('/api/verify_order/', data=json.dumps({'id': 99999}), content_type='application/json')
        completed_response = self.client.post('/api/verify_order/', data=json.dumps({'id': completed.id}), content_type='application/json')

        self.assertEqual(missing_response.json()['status'], 'fail')
        self.assertEqual(completed_response.json()['status'], 'fail')

    def test_verify_order_success_deducts_stock_records_sale_and_updates_stats(self):
        product = Product.objects.create(barcode='6900701', name='书签', price=Decimal('2.00'), stock=5)
        order = Order.objects.create(customer_name='郑十', total_price=Decimal('6.00'), status=0)
        OrderItem.objects.create(order=order, product=product, count=3)

        response = self.client.post('/api/verify_order/', data=json.dumps({'id': order.id}), content_type='application/json')

        product.refresh_from_db()
        order.refresh_from_db()
        stats = self.client.get('/get_today_stats/').json()
        self.assertEqual(response.json()['status'], 'success')
        self.assertEqual(product.stock, 2)
        self.assertEqual(order.status, 1)
        self.assertEqual(SaleHistory.objects.get().quantity, 3)
        self.assertEqual(stats['total_amount'], 6.0)
        self.assertEqual(stats['today_count'], 3)


class CheckRoleTests(TestCase):
    def test_check_role_without_code_or_wechat_config_returns_customer(self):
        response = self.client.get('/api/check_role/')

        self.assertEqual(response.json()['role'], 'customer')

    @override_settings(WECHAT_APPID='appid', WECHAT_SECRET='secret')
    @patch('web.views.requests.get')
    def test_check_role_returns_admin_for_whitelisted_openid(self, mocked_get):
        AdminUser.objects.create(openid='openid-1', name='店主')
        mocked_get.return_value = Mock(json=lambda: {'openid': 'openid-1'})

        response = self.client.get('/api/check_role/', {'code': 'wx-code'})

        self.assertEqual(response.json()['role'], 'admin')

    @override_settings(WECHAT_APPID='appid', WECHAT_SECRET='secret')
    @patch('web.views.requests.get')
    def test_check_role_returns_customer_when_wechat_fails(self, mocked_get):
        mocked_get.side_effect = RuntimeError('network error')

        response = self.client.get('/api/check_role/', {'code': 'wx-code'})

        self.assertEqual(response.json()['role'], 'customer')


class SalesReportTests(TestCase):
    def test_sales_report_returns_totals_top_products_and_records(self):
        SaleHistory.objects.create(product_name='铅笔', price=Decimal('1.50'), quantity=4)
        SaleHistory.objects.create(product_name='本子', price=Decimal('3.00'), quantity=2)
        SaleHistory.objects.create(product_name='铅笔', price=Decimal('1.50'), quantity=1)

        response = self.client.get('/api/sales_report/', {'days': 7})

        data = response.json()
        self.assertEqual(data['status'], 'success')
        self.assertEqual(Decimal(data['total_amount']), Decimal('13.00'))
        self.assertEqual(data['total_count'], 7)
        self.assertEqual(data['top_products'][0]['product_name'], '铅笔')
        self.assertEqual(data['top_products'][0]['quantity'], 5)
        self.assertEqual(len(data['records']), 3)
