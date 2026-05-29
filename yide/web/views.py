import json
from decimal import Decimal, InvalidOperation

import requests
from django.db import transaction
from django.db.models import DecimalField, ExpressionWrapper, F, Q, Sum
from django.http import JsonResponse
from django.shortcuts import render
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt

from .models import AdminUser, CartItem, Order, OrderItem, Product, SaleHistory


def check_role(request):
    code = request.GET.get('code')
    # 填入你小程序的真实信息
    appid = 'wxabca86f6f8d49d0b'
    secret = 'e8f8c1fea7ac16f8dc33b8257269ea36'

    if not code:
        return JsonResponse({'role': 'customer'})

    # 1. 换取 OpenID 的逻辑直接写在这里
    url = f"https://api.weixin.qq.com/sns/jscode2session?appid={appid}&secret={secret}&js_code={code}&grant_type=authorization_code"

    try:
        res = requests.get(url, timeout=5).json()
        openid = res.get('openid')
        if not openid:
            return JsonResponse({'role': 'customer'})

        # 调试用：在控制台打印出 openid，这就是长辈的“身份证号”
        print(f"--- 当前访问者的OpenID: {openid} ---")

        # 2. 检查数据库白名单
        # 如果你还没建表或没存数据，可以先手动判断自己的 ID 跑通逻辑
        is_admin = AdminUser.objects.filter(openid=openid).exists()

        if is_admin:
            return JsonResponse({'role': 'admin'})
        else:
            return JsonResponse({'role': 'customer'})

    except Exception as e:
        print(f"请求微信接口失败: {e}")
        return JsonResponse({'role': 'customer'})


# 页面渲染：显示收银台网页
def cash_register(request):
    return render(request, 'cashier.html')


# API 接口：根据条码查商品
def get_product_by_barcode(request):
    barcode = request.GET.get('barcode')
    if not barcode:
        return JsonResponse({'status': 'error', 'message': '条码不能为空'})

    product = Product.objects.filter(barcode=barcode).first()
    if not product:
        return JsonResponse({'status': 'error', 'message': '未找到商品'})

    return JsonResponse({
        'status': 'success',
        'name': product.name,
        'price': str(product.price),  # Decimal 需要转字符串
        'stock': product.stock
    })


# 小程序获取当前清单的接口
def get_cart_status(request):
    items = CartItem.objects.select_related('product').all().order_by('-added_at')
    data = []
    total = Decimal('0.00')
    for i in items:
        data.append({
            'id': i.product_id,
            'name': i.product.name,
            'price': str(i.product.price),
            'quantity': i.quantity,
            'remaining_stock': i.product.stock
        })
        total += i.product.price * i.quantity
    return JsonResponse({'items': data, 'total': str(total)})


# 扫码枪调用的接口：负责向购物车添加商品
def add_item(request):
    barcode = request.GET.get('barcode')
    if not barcode:
        return JsonResponse({'status': 'error', 'message': '条码不能为空'})

    try:
        with transaction.atomic():
            product = Product.objects.select_for_update().get(barcode=barcode)
            item, created = CartItem.objects.select_for_update().get_or_create(product=product)
            target_quantity = 1 if created else item.quantity + 1

            if product.stock < target_quantity:
                if created:
                    item.delete()
                return JsonResponse({'status': 'error', 'message': '库存不足'})

            if not created:
                item.quantity = target_quantity
                item.save(update_fields=['quantity'])

        return JsonResponse({
            'status': 'success',
            'name': product.name,
            'price': str(product.price),
            'current_qty': target_quantity,
            'remaining_stock': product.stock  # 这里显示的是当前的静态库存
        })
    except Product.DoesNotExist:
        return JsonResponse({'status': 'error', 'message': '未找到商品'})


# 按钮 A：单纯清空（网页端用，用于扫错重来）
def reset_cart(request):
    CartItem.objects.all().delete()
    return JsonResponse({'status': 'success', 'message': '账单已重置'})


# 按钮 B：正式结账（小程序端用，扣库存+记账）
def checkout_cart(request):
    cart_items = CartItem.objects.select_related('product').all()
    if not cart_items.exists():
        return JsonResponse({'status': 'error', 'message': '账单为空'})

    try:
        with transaction.atomic():
            for item in cart_items.select_for_update():
                product = Product.objects.select_for_update().get(pk=item.product_id)
                if product.stock < item.quantity:
                    return JsonResponse({
                        'status': 'error',
                        'message': f'{product.name} 库存不足，当前库存 {product.stock}，需要 {item.quantity}'
                    })

                # 1. 记录到销售历史 (这是统计的来源！)
                SaleHistory.objects.create(
                    product_name=product.name,
                    price=product.price,
                    quantity=item.quantity
                    # sale_date 会自动使用 auto_now_add 生成
                )

                # 2. 扣减库存
                product.stock -= item.quantity
                product.save(update_fields=['stock'])

            # 3. 最后清空购物车
            cart_items.delete()

        return JsonResponse({'status': 'success'})
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)})


# 今日营业额
def get_today_stats(request):
    # 使用 Django 提供的 timezone.now()，它会自动处理 settings.py 里的时区
    now = timezone.now()
    today = now.date()

    # 只统计 SaleHistory 即可。
    # 因为你的 verify_order 逻辑已经很棒了：它核销后会自动把商城订单拆解并存入 SaleHistory。
    line_total = ExpressionWrapper(
        F('price') * F('quantity'),
        output_field=DecimalField(max_digits=12, decimal_places=2)
    )
    stats = SaleHistory.objects.filter(
        sale_date__date=today
    ).aggregate(
        total_money=Sum(line_total),
        total_num=Sum('quantity')  # 注意：这里用 Sum(quantity) 比 count() 更准
    )

    total_amount = float(stats['total_money'] or 0)
    # 如果统计的是卖出多少件货，用 Sum('quantity')；
    # 如果统计的是成交了多少笔单，用 .count()
    today_count = stats['total_num'] or 0

    return JsonResponse({
        'status': 'success',
        'total_amount': round(total_amount, 2),
        'today_count': int(today_count)
    })


# 小程序扫码入库（适合日常补货/新书上架）
def quick_add_product(request):
    barcode = request.GET.get('barcode')
    name = request.GET.get('name')
    price = request.GET.get('price')

    try:
        stock = int(request.GET.get('stock', 0))
        price_value = Decimal(str(price))
    except (TypeError, ValueError, InvalidOperation):
        return JsonResponse({'status': 'fail', 'msg': '价格或库存格式不正确'})

    if not barcode or not name:
        return JsonResponse({'status': 'fail', 'msg': '条码和名称不能为空'})
    if stock <= 0:
        return JsonResponse({'status': 'fail', 'msg': '入库数量必须大于0'})
    if price_value < 0:
        return JsonResponse({'status': 'fail', 'msg': '价格不能为负数'})

    with transaction.atomic():
        product, created = Product.objects.select_for_update().get_or_create(
            barcode=barcode,
            defaults={
                'name': name,
                'price': price_value,
                'stock': 0
            }
        )

        if not created:
            product.name = name
            product.price = price_value

        # 增加库存
        product.stock += stock
        product.save(update_fields=['name', 'price', 'stock'])

    return JsonResponse({
        'status': 'success',
        'is_new': created,
        'current_stock': product.stock
    })


def get_mall_products(request):
    cat = request.GET.get('category', 'all')

    # 基础查询：必须有库存
    query = Product.objects.filter(stock__gt=0)

    # 如果不是“全部”，则增加分类过滤条件
    if cat != 'all':
        query = query.filter(category=cat)

    products = query.values('id', 'name', 'price', 'category', 'stock')

    return JsonResponse({
        'status': 'success',
        'list': list(products)
    }, json_dumps_params={'ensure_ascii': False})


@csrf_exempt
def submit_order(request):
    if request.method != 'POST':
        return JsonResponse({'status': 'fail', 'msg': '请使用POST请求'})
    try:
        data = json.loads(request.body or '{}')
        name = (data.get('name') or '').strip()
        cart = data.get('cart') or []

        if not name:
            return JsonResponse({'status': 'fail', 'msg': '请输入取货人姓名'})
        if not cart:
            return JsonResponse({'status': 'fail', 'msg': '购物车不能为空'})

        with transaction.atomic():
            order_items = []
            total = Decimal('0.00')
            for item in cart:
                product_id = item.get('id')
                count = int(item.get('num', 0))
                if count <= 0:
                    return JsonResponse({'status': 'fail', 'msg': '商品数量必须大于0'})

                product = Product.objects.select_for_update().get(id=product_id)
                if product.stock < count:
                    return JsonResponse({
                        'status': 'fail',
                        'msg': f'{product.name} 库存不足，当前库存 {product.stock}，需要 {count}'
                    })

                order_items.append((product, count))
                total += product.price * count

            # 1. 只创建订单，不扣库存
            new_order = Order.objects.create(
                customer_name=name,
                total_price=total,
                status=0  # 0: 待取货
            )
            # 2. 记录明细
            for product, count in order_items:
                OrderItem.objects.create(
                    order=new_order,
                    product=product,
                    count=count
                )
        return JsonResponse({
            'status': 'success',
            'msg': '下单成功',
            'order_sn': new_order.order_sn,
            'total': str(total)
        })
    except (Product.DoesNotExist, TypeError, ValueError, KeyError):
        return JsonResponse({'status': 'fail', 'msg': '订单商品数据不正确'})
    except Exception as e:
        return JsonResponse({'status': 'fail', 'msg': str(e)})


def get_new_order_count(request):
    # 查询状态为 0 (待取货) 的订单数量
    count = Order.objects.filter(status=0).count()
    return JsonResponse({'count': count})


# 1. 搜索订单接口
def search_order(request):
    key = request.GET.get('key', '').strip()
    if not key:
        return JsonResponse({'status': 'fail', 'msg': '请输入搜索关键词'})

    # 模糊搜索：姓名包含关键字 OR 编号包含关键字
    # 且状态必须是 0 (待取货)
    order = Order.objects.filter(
        Q(customer_name__icontains=key) | Q(order_sn__icontains=key),
        status=0
    ).first()

    if order:
        return JsonResponse({
            'status': 'success',
            'order': {
                'id': order.id,
                'customer_name': order.customer_name,
                'total_price': str(order.total_price),
                'order_sn': order.order_sn
            }
        }, json_dumps_params={'ensure_ascii': False})  # 关键：禁止转义中文

    return JsonResponse({'status': 'fail', 'msg': '未找到匹配订单'})


# 2. 确认取货核销接口
@csrf_exempt
def verify_order(request):
    if request.method != 'POST':
        return JsonResponse({'status': 'fail', 'msg': '请使用POST请求'})

    try:
        data = json.loads(request.body or '{}')
    except json.JSONDecodeError:
        return JsonResponse({'status': 'fail', 'msg': '请求数据格式不正确'})

    order_id = data.get('id')
    try:
        with transaction.atomic():
            order = Order.objects.select_for_update().get(id=order_id, status=0)
            # 扣库存逻辑（和你 admin.py 里写的一样）
            for item in order.items.select_related('product').all():
                product = Product.objects.select_for_update().get(pk=item.product_id)
                if product.stock < item.count:
                    return JsonResponse({
                        'status': 'fail',
                        'msg': f'{product.name} 库存不足，当前库存 {product.stock}，需要 {item.count}'
                    })

                product.stock -= item.count
                product.save(update_fields=['stock'])
                # 存入销售历史
                SaleHistory.objects.create(
                    product_name=product.name,
                    price=product.price,
                    quantity=item.count
                )
            # 修改订单状态
            order.status = 1
            order.save(update_fields=['status'])
        return JsonResponse({'status': 'success'})
    except Order.DoesNotExist:
        return JsonResponse({'status': 'fail', 'msg': '未找到待取货订单'})
    except Exception as e:
        return JsonResponse({'status': 'fail', 'msg': str(e)})
