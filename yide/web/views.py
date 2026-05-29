import json
from decimal import Decimal, InvalidOperation

import requests
from django.conf import settings
from django.db import transaction
from django.db.models import DecimalField, ExpressionWrapper, F, Sum
from django.http import JsonResponse
from django.shortcuts import render
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt

from .models import AdminUser, CartItem, Order, OrderItem, Product, SaleHistory


WECHAT_SESSION_URL = "https://api.weixin.qq.com/sns/jscode2session"


def _error(message, status="error"):
    return JsonResponse({"status": status, "message": message, "msg": message})


def _parse_positive_int(value, field_name):
    try:
        number = int(value)
    except (TypeError, ValueError):
        raise ValueError(f"{field_name}必须是正整数")
    if number <= 0:
        raise ValueError(f"{field_name}必须大于0")
    return number


def _parse_price(value, field_name="价格"):
    try:
        price = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        raise ValueError(f"{field_name}格式不正确")
    if price < 0:
        raise ValueError(f"{field_name}不能小于0")
    return price


def _load_json_body(request):
    try:
        return json.loads(request.body or b"{}")
    except json.JSONDecodeError:
        raise ValueError("请求数据不是有效的JSON")


def _record_sale(product, quantity):
    SaleHistory.objects.create(
        product_name=product.name,
        price=product.price,
        quantity=quantity,
    )


def _deduct_stock(product, quantity):
    if product.stock < quantity:
        raise ValueError(f"{product.name}库存不足，当前仅剩{product.stock}件")
    product.stock -= quantity
    product.save(update_fields=["stock"])


def check_role(request):
    code = request.GET.get("code")
    appid = getattr(settings, "WECHAT_APPID", "wxabca86f6f8d49d0b")
    secret = getattr(settings, "WECHAT_SECRET", "e8f8c1fea7ac16f8dc33b8257269ea36")

    if not code:
        return JsonResponse({"role": "customer"})

    try:
        res = requests.get(
            WECHAT_SESSION_URL,
            params={
                "appid": appid,
                "secret": secret,
                "js_code": code,
                "grant_type": "authorization_code",
            },
            timeout=5,
        ).json()
        openid = res.get("openid")
        is_admin = bool(openid) and AdminUser.objects.filter(openid=openid).exists()
        return JsonResponse({"role": "admin" if is_admin else "customer"})
    except (requests.RequestException, ValueError) as e:
        print(f"请求微信接口失败: {e}")
        return JsonResponse({"role": "customer"})


# 页面渲染：显示收银台网页
def cash_register(request):
    return render(request, "cashier.html")


# API 接口：根据条码查商品
def get_product_by_barcode(request):
    barcode = request.GET.get("barcode")
    if not barcode:
        return _error("条码不能为空")

    product = Product.objects.filter(barcode=barcode).first()
    if not product:
        return _error("未找到商品")

    return JsonResponse({
        "status": "success",
        "name": product.name,
        "price": str(product.price),
        "stock": product.stock,
    })


# 小程序获取当前清单的接口
def get_cart_status(request):
    items = CartItem.objects.select_related("product").all().order_by("-added_at")
    data = []
    total = Decimal("0")
    for item in items:
        line_total = item.product.price * item.quantity
        data.append({
            "name": item.product.name,
            "price": str(item.product.price),
            "quantity": item.quantity,
            "subtotal": str(line_total),
        })
        total += line_total
    return JsonResponse({"items": data, "total": str(total)})


# 扫码枪调用的接口：负责向购物车添加商品
def add_item(request):
    barcode = request.GET.get("barcode")
    if not barcode:
        return _error("条码不能为空")

    try:
        with transaction.atomic():
            product = Product.objects.select_for_update().get(barcode=barcode)
            item = CartItem.objects.select_for_update().filter(product=product).first()
            current_quantity = item.quantity if item else 0
            new_quantity = current_quantity + 1
            if product.stock < new_quantity:
                return _error("库存不足")
            if item:
                item.quantity = new_quantity
                item.save(update_fields=["quantity"])
            else:
                item = CartItem.objects.create(product=product, quantity=new_quantity)

        return JsonResponse({
            "status": "success",
            "name": product.name,
            "price": str(product.price),
            "current_qty": item.quantity,
            "remaining_stock": product.stock,
        })
    except Product.DoesNotExist:
        return _error("未找到商品")


# 按钮 A：单纯清空（网页端用，用于扫错重来）
def reset_cart(request):
    CartItem.objects.all().delete()
    return JsonResponse({"status": "success", "message": "账单已重置"})


# 按钮 B：正式结账（小程序端用，扣库存+记账）
def checkout_cart(request):
    if not CartItem.objects.exists():
        return _error("账单为空")

    try:
        with transaction.atomic():
            cart_items = list(
                CartItem.objects.select_for_update().select_related("product").order_by("id")
            )
            product_ids = [item.product_id for item in cart_items]
            products = {
                product.id: product
                for product in Product.objects.select_for_update().filter(id__in=product_ids)
            }
            for item in cart_items:
                product = products[item.product_id]
                _deduct_stock(product, item.quantity)
                _record_sale(product, item.quantity)
            CartItem.objects.filter(id__in=[item.id for item in cart_items]).delete()
        return JsonResponse({"status": "success"})
    except ValueError as e:
        return _error(str(e))


# 今日营业额
def get_today_stats(request):
    today = timezone.now().date()
    amount_expression = ExpressionWrapper(
        F("price") * F("quantity"),
        output_field=DecimalField(max_digits=12, decimal_places=2),
    )
    stats = SaleHistory.objects.filter(sale_date__date=today).aggregate(
        total_money=Sum(amount_expression),
        total_num=Sum("quantity"),
    )

    total_amount = stats["total_money"] or Decimal("0")
    today_count = stats["total_num"] or 0

    return JsonResponse({
        "status": "success",
        "total_amount": round(float(total_amount), 2),
        "today_count": int(today_count),
    })


# 小程序扫码入库（适合日常补货/新书上架）
def quick_add_product(request):
    barcode = request.GET.get("barcode")
    name = request.GET.get("name")
    price = request.GET.get("price")

    if not barcode:
        return _error("条码不能为空")
    if not name:
        return _error("商品名称不能为空")

    try:
        stock = _parse_positive_int(request.GET.get("stock", 0), "入库数量")
        parsed_price = _parse_price(price)
    except ValueError as e:
        return _error(str(e))

    product, created = Product.objects.update_or_create(
        barcode=barcode,
        defaults={"name": name, "price": parsed_price},
    )
    product.stock += stock
    product.save(update_fields=["stock"])

    return JsonResponse({
        "status": "success",
        "is_new": created,
        "current_stock": product.stock,
    })


def get_mall_products(request):
    cat = request.GET.get("category", "all")
    query = Product.objects.filter(stock__gt=0)
    valid_categories = {choice[0] for choice in Product.CATEGORY_CHOICES}
    if cat != "all":
        if cat not in valid_categories:
            return JsonResponse({"status": "success", "list": []}, json_dumps_params={"ensure_ascii": False})
        query = query.filter(category=cat)

    products = query.values("id", "name", "price", "category", "stock")
    return JsonResponse({
        "status": "success",
        "list": list(products),
    }, json_dumps_params={"ensure_ascii": False})


@csrf_exempt
def submit_order(request):
    if request.method != "POST":
        return JsonResponse({"status": "fail", "msg": "请使用POST请求"})
    try:
        data = _load_json_body(request)
        name = (data.get("name") or "").strip()
        cart = data.get("cart") or []
        if not name:
            raise ValueError("取货人姓名不能为空")
        if not isinstance(cart, list) or not cart:
            raise ValueError("购物车不能为空")

        with transaction.atomic():
            product_ids = [item.get("id") for item in cart]
            products = {
                product.id: product
                for product in Product.objects.select_for_update().filter(id__in=product_ids)
            }
            order_items = []
            calculated_total = Decimal("0")
            for item in cart:
                product_id = item.get("id")
                product = products.get(product_id)
                if not product:
                    raise ValueError("商品不存在")
                count = _parse_positive_int(item.get("num"), "购买数量")
                if product.stock < count:
                    raise ValueError(f"{product.name}库存不足，当前仅剩{product.stock}件")
                calculated_total += product.price * count
                order_items.append((product, count))

            new_order = Order.objects.create(
                customer_name=name,
                total_price=calculated_total,
                status=0,
            )
            for product, count in order_items:
                OrderItem.objects.create(order=new_order, product=product, count=count)
        return JsonResponse({"status": "success", "msg": "下单成功", "order_sn": new_order.order_sn})
    except ValueError as e:
        return JsonResponse({"status": "fail", "msg": str(e)})
    except Exception as e:
        return JsonResponse({"status": "fail", "msg": str(e)})


def get_new_order_count(request):
    count = Order.objects.filter(status=0).count()
    return JsonResponse({"count": count})


# 1. 搜索订单接口
def search_order(request):
    key = request.GET.get("key", "").strip()
    if not key:
        return JsonResponse({"status": "fail", "msg": "请输入搜索关键词"})

    from django.db.models import Q
    order = Order.objects.filter(
        Q(customer_name__icontains=key) | Q(order_sn__icontains=key),
        status=0,
    ).first()

    if not order:
        return JsonResponse({"status": "fail", "msg": "未找到匹配订单"})

    return JsonResponse({
        "status": "success",
        "order": {
            "id": order.id,
            "customer_name": order.customer_name,
            "total_price": str(order.total_price),
            "order_sn": order.order_sn,
        },
    }, json_dumps_params={"ensure_ascii": False})


# 2. 确认取货核销接口
@csrf_exempt
def verify_order(request):
    if request.method != "POST":
        return JsonResponse({"status": "fail", "msg": "请使用POST请求"})
    try:
        data = _load_json_body(request)
        order_id = data.get("id")
        with transaction.atomic():
            order = Order.objects.select_for_update().get(id=order_id, status=0)
            product_ids = list(order.items.values_list("product_id", flat=True))
            products = {
                product.id: product
                for product in Product.objects.select_for_update().filter(id__in=product_ids)
            }
            for item in order.items.select_related("product"):
                product = products[item.product_id]
                _deduct_stock(product, item.count)
                _record_sale(product, item.count)
            order.status = 1
            order.save(update_fields=["status"])
        return JsonResponse({"status": "success"})
    except Order.DoesNotExist:
        return JsonResponse({"status": "fail", "msg": "订单不存在或已核销"})
    except ValueError as e:
        return JsonResponse({"status": "fail", "msg": str(e)})
    except Exception as e:
        return JsonResponse({"status": "fail", "msg": str(e)})
