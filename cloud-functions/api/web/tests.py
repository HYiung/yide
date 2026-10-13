import json
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings

from unittest.mock import patch

from . import views, webassets
from .models import CartItem, Order, OrderItem, Product, SaleHistory


class ShopkeeperSessionMixin:
    """收银台接口走 Django session 鉴权（is_shopkeeper_request 的
    request.user.is_staff 分支），这里用 force_login 复现浏览器端的真实调用方式。
    注意：必须登录，否则接口返回 403/503，断言 'status' == 'fail' 会因为
    鉴权失败而"假通过"，把真正的库存逻辑测试变成空测。
    """

    @classmethod
    def setUpTestData(cls):
        cls.shopkeeper = get_user_model().objects.create_user(
            username='shopkeeper', password='test-password',
            is_staff=True, is_superuser=True,
        )

    def setUp(self):
        self.client.force_login(self.shopkeeper)


class CashierApiAuthTests(TestCase):
    """收银台接口不能再裸奔：购物车、结账、营收、查价、AI 识别都要求鉴权。"""

    PROTECTED_ENDPOINTS = [
        '/get_cart_status/',
        '/add_item/?barcode=6900001',
        '/reset_cart/',
        '/remove_cart_item/?product_id=1',
        '/update_cart_item/?product_id=1&quantity=1',
        '/checkout_cart/',
        '/get_product_by_barcode/?barcode=6900001',
        '/get_today_stats/',
    ]

    def test_protected_endpoints_reject_anonymous_callers(self):
        for url in self.PROTECTED_ENDPOINTS:
            with self.subTest(url=url):
                self.assertIn(self.client.get(url).status_code, (401, 403, 503))

    def test_reset_cart_cannot_be_triggered_anonymously(self):
        """回归防护：/reset_cart/ 曾是公开 GET，任何人可清空店员的账单。"""
        product = Product.objects.create(barcode='6900001', name='铅笔', price=Decimal('2.00'), stock=5)
        CartItem.objects.create(product=product, quantity=3)

        self.client.get('/reset_cart/')

        self.assertEqual(CartItem.objects.count(), 1)

    def test_checkout_cannot_be_triggered_anonymously(self):
        """回归防护：/checkout_cart/ 曾是公开 GET，任何人都能凭空完成一笔交易。"""
        product = Product.objects.create(barcode='6900002', name='橡皮', price=Decimal('1.50'), stock=5)
        CartItem.objects.create(product=product, quantity=2)

        self.client.get('/checkout_cart/')

        product.refresh_from_db()
        self.assertEqual(product.stock, 5)
        self.assertEqual(SaleHistory.objects.count(), 0)

    def test_shopkeeper_token_header_grants_access(self):
        """小程序没有 session，靠 X-Shopkeeper-Token 访问。"""
        with override_settings(SHOPKEEPER_API_TOKEN='test-token'):
            response = self.client.get('/get_today_stats/', HTTP_X_SHOPKEEPER_TOKEN='test-token')

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['status'], 'success')

    def test_ai_recognize_requires_auth(self):
        response = self.client.post('/api/ai_recognize/')

        self.assertIn(response.status_code, (401, 403, 503))


class CashierLoginTests(TestCase):
    """收银台登录：密码来自环境变量，未配置时必须 fail closed。

    背景：settings.py 曾硬编码默认密码 'yide888'，而仓库是公开的，等于后台密码公开。
    移除默认值后，若环境变量缺失，绝不能让空密码通过。
    """

    LOGIN_URL = '/cashier/login/'

    def _is_logged_in(self):
        return '_auth_user_id' in self.client.session

    @override_settings(SHOPKEEPER_PASSWORD='correct-horse')
    def test_login_succeeds_with_configured_password(self):
        response = self.client.post(self.LOGIN_URL, {'password': 'correct-horse'})

        self.assertEqual(response.status_code, 302)
        self.assertTrue(self._is_logged_in())

    @override_settings(SHOPKEEPER_PASSWORD='correct-horse')
    def test_login_rejects_wrong_password(self):
        response = self.client.post(self.LOGIN_URL, {'password': 'yide888'})

        self.assertEqual(response.status_code, 302)
        self.assertFalse(self._is_logged_in())

    @override_settings(SHOPKEEPER_PASSWORD='correct-horse')
    def test_login_rejects_empty_password_when_configured(self):
        response = self.client.post(self.LOGIN_URL, {'password': ''})

        self.assertEqual(response.status_code, 302)
        self.assertFalse(self._is_logged_in())

    @override_settings(SHOPKEEPER_PASSWORD='')
    def test_login_fails_closed_when_password_unset(self):
        """环境变量没配时，空密码不能登录（否则比默认密码还危险）。"""
        response = self.client.post(self.LOGIN_URL, {'password': ''})

        self.assertEqual(response.status_code, 302)
        self.assertFalse(self._is_logged_in())


class ProductLookupTests(ShopkeeperSessionMixin, TestCase):
    def test_missing_barcode_returns_json_error(self):
        # 本地无此条码时会去查 Open Library / Google Books / Bing 等外部源，
        # 不 mock 的话结果随网络变化（曾因此偶发地返回 success 而挂掉）。
        with patch.object(views, '_lookup_barcode_external', return_value=None):
            response = self.client.get('/get_product_by_barcode/', {'barcode': 'missing'})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['status'], 'fail')


class CartFlowTests(ShopkeeperSessionMixin, TestCase):
    def test_add_item_allows_last_stock_item_and_does_not_overfill_cart(self):
        Product.objects.create(barcode='6900001', name='铅笔', price=Decimal('2.00'), stock=1)

        first_response = self.client.get('/add_item/', {'barcode': '6900001'})
        self.assertEqual(first_response.json()['status'], 'success')
        self.assertEqual(first_response.json()['current_qty'], 1)

        second_response = self.client.get('/add_item/', {'barcode': '6900001'})
        self.assertEqual(second_response.json()['status'], 'fail')
        self.assertEqual(CartItem.objects.get(product__barcode='6900001').quantity, 1)

    def test_checkout_refuses_to_create_negative_stock(self):
        product = Product.objects.create(barcode='6900002', name='橡皮', price=Decimal('1.50'), stock=1)
        CartItem.objects.create(product=product, quantity=2)

        response = self.client.get('/checkout_cart/')

        # 先确认真的走到了业务逻辑，否则 403/503 的响应体也是 {'status':'fail'}，
        # 下面的断言会在鉴权失败时"假通过"。
        self.assertEqual(response.status_code, 200)
        product.refresh_from_db()
        self.assertEqual(response.json()['status'], 'fail')
        self.assertEqual(product.stock, 1)
        self.assertEqual(SaleHistory.objects.count(), 0)

    def test_checkout_short_later_item_does_not_partially_commit(self):
        in_stock = Product.objects.create(barcode='6900101', name='中性笔', price=Decimal('3.00'), stock=5)
        short_stock = Product.objects.create(barcode='6900102', name='便签', price=Decimal('2.00'), stock=1)
        CartItem.objects.create(product=in_stock, quantity=2)
        CartItem.objects.create(product=short_stock, quantity=2)

        response = self.client.get('/checkout_cart/')

        self.assertEqual(response.status_code, 200)
        in_stock.refresh_from_db()
        short_stock.refresh_from_db()
        self.assertEqual(response.json()['status'], 'fail')
        self.assertEqual(in_stock.stock, 5)
        self.assertEqual(short_stock.stock, 1)
        self.assertEqual(SaleHistory.objects.count(), 0)
        self.assertEqual(CartItem.objects.count(), 2)


class SalesStatsTests(ShopkeeperSessionMixin, TestCase):
    def test_today_stats_multiplies_price_by_quantity(self):
        SaleHistory.objects.create(product_name='笔记本', price=Decimal('3.50'), quantity=2)
        SaleHistory.objects.create(product_name='钢笔', price=Decimal('5.00'), quantity=3)

        response = self.client.get('/get_today_stats/')

        self.assertEqual(response.json()['total_amount'], 22.0)
        self.assertEqual(response.json()['today_count'], 5)


@override_settings(SHOPKEEPER_API_TOKEN='test-token')
class OrderFlowTests(TestCase):
    def test_verify_order_requires_shopkeeper_token(self):
        order = Order.objects.create(customer_name='未授权', total_price=Decimal('0.00'), status=0)

        response = self.client.post(
            '/api/verify_order/',
            data=json.dumps({'id': order.id}),
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()['status'], 'fail')

        query_token_response = self.client.post(
            '/api/verify_order/?token=test-token',
            data=json.dumps({'id': order.id}),
            content_type='application/json',
        )
        self.assertEqual(query_token_response.status_code, 403)

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
            HTTP_X_SHOPKEEPER_TOKEN='test-token',
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
            HTTP_X_SHOPKEEPER_TOKEN='test-token',
        )

        in_stock.refresh_from_db()
        short_stock.refresh_from_db()
        order.refresh_from_db()
        self.assertEqual(response.json()['status'], 'fail')
        self.assertEqual(in_stock.stock, 4)
        self.assertEqual(short_stock.stock, 1)
        self.assertEqual(order.status, 0)
        self.assertEqual(SaleHistory.objects.count(), 0)


@override_settings(SHOPKEEPER_API_TOKEN='test-token')
class InventoryApiTests(TestCase):
    shopkeeper_headers = {'HTTP_X_SHOPKEEPER_TOKEN': 'test-token'}

    def test_low_stock_products_returns_threshold_matches(self):
        low = Product.objects.create(barcode='6900301', name='作业本', price=Decimal('2.50'), stock=2)
        Product.objects.create(barcode='6900302', name='笔芯', price=Decimal('1.00'), stock=8)

        response = self.client.get('/api/low_stock_products/', {'threshold': 5}, **self.shopkeeper_headers)

        data = response.json()
        self.assertEqual(data['status'], 'success')
        self.assertEqual(data['threshold'], 5)
        self.assertEqual([item['id'] for item in data['list']], [low.id])

    def test_pending_orders_includes_items_for_dashboard(self):
        product = Product.objects.create(barcode='6900303', name='便利贴', price=Decimal('3.00'), stock=5)
        order = Order.objects.create(customer_name='王五', total_price=Decimal('6.00'), status=0)
        OrderItem.objects.create(order=order, product=product, count=2)

        response = self.client.get('/api/pending_orders/', **self.shopkeeper_headers)

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


class CashierAssetsTests(TestCase):
    def test_cashier_uses_cacheable_static_assets(self):
        user = get_user_model().objects.create_user(
            username='cashier', password='test-password', is_staff=True,
        )
        self.client.force_login(user)

        response = self.client.get('/cashier/')
        html = response.content.decode()

        self.assertContains(response, '/assets/web/css/cashier.css')
        self.assertContains(response, '/assets/web/js/cashier.js')
        self.assertNotIn('<style>', html)
        self.assertNotIn('<script>', html)

    def test_web_assets_are_served_from_the_embedded_module(self):
        """资源由 Django 视图直接输出，不依赖 staticfiles finder。

        EdgeOne 只部署 .py 文件，web/static/ 下的 css/js 会被剥离，
        finders.find() 在线上返回 None，所以真正要保证的是视图能把内容吐出来。
        """
        response = self.client.get(webassets.url('web/css/cashier.css'))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'text/css; charset=utf-8')
        self.assertEqual(
            response.content.decode(),
            webassets.ASSETS['web/css/cashier.css'][0],
        )
        self.assertIn('immutable', response['Cache-Control'])

    def test_asset_url_carries_the_version(self):
        self.assertIn(f'?v={webassets.VERSION}', webassets.url('web/js/mall.js'))

    def test_unknown_web_asset_is_not_found(self):
        self.assertEqual(self.client.get('/assets/web/css/nope.css').status_code, 404)

    def test_admin_static_files_still_use_the_staticfiles_route(self):
        """只截获 web/css、web/js，不能把 /assets/admin/** 也一起吃掉。"""
        response = self.client.get('/assets/admin/css/base.css')

        self.assertEqual(response.status_code, 200)

    def test_login_error_is_exposed_without_inline_javascript(self):
        self.client.post('/cashier/login/', {'password': 'wrong'})

        response = self.client.get('/cashier/login/')

        self.assertContains(response, 'data-login-error="true"')
        self.assertContains(response, '/assets/web/js/cashier-login.js')
        self.assertNotIn('__LOGIN_ERROR__', response.content.decode())


class AdminLogoutTests(TestCase):
    """后台退出后回店长入口，不再落到 Django 默认的 admin 登录页。"""

    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username='shopkeeper', password='test-password',
            is_staff=True, is_superuser=True,
        )

    def test_admin_logout_redirects_to_shopkeeper_login(self):
        self.client.force_login(self.user)

        response = self.client.post('/admin/logout/')

        self.assertRedirects(response, '/cashier/login/')

    def test_admin_logout_ends_the_session(self):
        self.client.force_login(self.user)
        self.client.post('/admin/logout/')

        response = self.client.get('/cashier/')

        self.assertRedirects(response, '/cashier/login/')

    def test_admin_logout_does_not_render_the_admin_logged_out_page(self):
        self.client.force_login(self.user)

        body = self.client.post('/admin/logout/', follow=True).content.decode()

        self.assertIn('店长入口', body)
        self.assertNotIn('Django administration', body)
