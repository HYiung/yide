import datetime
import json
import requests
from django.http import JsonResponse

from . import models
from .models import Product, CartItem, SaleHistory, AdminUser, OrderItem, Order
from django.shortcuts import render
from django.db.models import Sum, F
from django.db import transaction
from django.views.decorators.csrf import csrf_exempt
from django.utils import timezone

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
        res = requests.get(url).json()
        openid = res.get('openid')

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
    barcode = request.GET.get('barcode', None)
    try:
        product = Product.objects.filter(barcode=barcode).first()
        if product:
            return JsonResponse({
                'status': 'success',
                'name': product.name,
                'price': str(product.price),  # Decimal 需要转字符串
                'stock': product.stock
            })
    except Product.DoesNotExist:
        return JsonResponse({'status': 'error', 'message': '未找到商品'})


# 小程序获取当前清单的接口
def get_cart_status(request):
    items = CartItem.objects.all().order_by('-added_at')
    data = []
    total = 0
    for i in items:
        data.append({
            'name': i.product.name,
            'price': str(i.product.price),
            'quantity': i.quantity
        })
        total += i.product.price * i.quantity
    return JsonResponse({'items': data, 'total': str(total)})


# 扫码枪调用的接口：负责向购物车添加商品
def add_item(request):
    barcode = request.GET.get('barcode')
    if not barcode:
        return JsonResponse({'status': 'error', 'message': '条码不能为空'})

    try:
        product = Product.objects.get(barcode=barcode)

        # 1. 只负责加入购物车，不扣库存
        item, created = CartItem.objects.get_or_create(product=product)
        if not created:
            item.quantity += 1
            item.save()

        if product.stock < (item.quantity + 1):
            return JsonResponse({'status': 'error', 'message': '库存不足'})
        return JsonResponse({
            'status': 'success',
            'name': product.name,
            'price': str(product.price),
            'current_qty': item.quantity,
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
    cart_items = CartItem.objects.all()
    if not cart_items.exists():
        return JsonResponse({'status': 'error', 'message': '账单为空'})

    try:
        with transaction.atomic():
            for item in cart_items:
                # 1. 记录到销售历史 (这是统计的来源！)
                SaleHistory.objects.create(
                    product_name=item.product.name,
                    price=item.product.price,
                    quantity=item.quantity
                    # sale_date 会自动使用 auto_now_add 生成
                )

                # 2. 扣减库存
                product = item.product
                product.stock -= item.quantity
                product.save()

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
    stats = SaleHistory.objects.filter(
        sale_date__date=today
    ).aggregate(
        total_money=Sum('price'),
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
    stock = int(request.GET.get('stock', 0))

    # 获取或创建一个空的商品对象
    # update_or_create: 有就更新，没有就创建
    product, created = Product.objects.update_or_create(
        barcode=barcode,
        defaults={
            'name': name,
            'price': price,
            'stock': 0
        }
    )

    if not created:
        # 如果商品已存在，且传了新名字/价格，则更新（可选）
        if name: product.name = name
        if price: product.price = price

    # 增加库存
    product.stock += stock
    product.save()

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

    products = query.values('id', 'name', 'price', 'category')

    return JsonResponse({
        'status': 'success',
        'list': list(products)
    }, json_dumps_params={'ensure_ascii': False})


@csrf_exempt
def submit_order(request):
    if request.method != 'POST':
        return JsonResponse({'status': 'fail', 'msg': '请使用POST请求'})
    try:
        data = json.loads(request.body)
        name = data.get('name')
        cart = data.get('cart')
        total = data.get('total')

        with transaction.atomic():
            # 1. 只创建订单，不扣库存
            new_order = Order.objects.create(
                customer_name=name,
                total_price=total,
                status=0  # 0: 待取货
            )
            # 2. 记录明细
            for item in cart:
                product = Product.objects.get(id=item['id'])
                OrderItem.objects.create(
                    order=new_order,
                    product=product,
                    count=item['num']
                )
        return JsonResponse({'status': 'success', 'msg': '下单成功'})
    except Exception as e:
        return JsonResponse({'status': 'fail', 'msg': str(e)})

def get_new_order_count(request):
    # 查询状态为 0 (待取货) 的订单数量
    count = Order.objects.filter(status=0).count()
    return JsonResponse({'count': count})


# 1. 搜索订单接口
def search_order(request):
    key = request.GET.get('key', '')
    if not key:
        return JsonResponse({'status': 'fail', 'msg': '请输入搜索关键词'})

    # 模糊搜索：姓名包含关键字 OR 编号包含关键字
    # 且状态必须是 0 (待取货)
    from django.db.models import Q
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


# 2. 确认取货核销接口
@csrf_exempt
def verify_order(request):
    data = json.loads(request.body)
    order_id = data.get('id')
    try:
        with transaction.atomic():
            order = Order.objects.select_for_update().get(id=order_id, status=0)
            # 扣库存逻辑（和你 admin.py 里写的一样）
            for item in order.items.all():
                product = item.product
                product.stock -= item.count
                product.save()
                # 存入销售历史
                SaleHistory.objects.create(
                    product_name=product.name,
                    price=product.price,
                    quantity=item.count
                )
            # 修改订单状态
            order.status = 1
            order.save()
        return JsonResponse({'status': 'success'})
    except Exception as e:
        return JsonResponse({'status': 'fail', 'msg': str(e)})