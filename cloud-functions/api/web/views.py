import json
import logging
from decimal import Decimal, InvalidOperation

import requests
from django.conf import settings
from django.db import transaction
from django.db.models import DecimalField, ExpressionWrapper, F, Q, Sum
from django.http import JsonResponse
from django.shortcuts import render
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt

from .models import AdminUser, CartItem, Order, OrderItem, Product, SaleHistory

logger = logging.getLogger(__name__)


def get_request_int(value, default=0):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def serialize_order(order):
    items = []
    for item in order.items.select_related('product').all():
        items.append({
            'product_id': item.product_id,
            'name': item.product.name,
            'count': item.count,
            'price': str(item.product.price),
        })

    return {
        'id': order.id,
        'customer_name': order.customer_name,
        'total_price': str(order.total_price),
        'order_sn': order.order_sn,
        'create_time': order.create_time.strftime('%Y-%m-%d %H:%M'),
        'items': items,
    }


def check_role(request):
    code = request.GET.get('code')
    if not code and request.method == 'POST':
        try:
            data = json.loads(request.body)
            code = data.get('code')
        except (json.JSONDecodeError, TypeError, AttributeError):
            code = request.POST.get('code')

    appid = getattr(settings, 'WECHAT_APPID', '')
    secret = getattr(settings, 'WECHAT_SECRET', '')

    if not code or not appid or not secret:
        logger.warning("微信登录参数缺失，缺省为普通顾客")
        return JsonResponse({'role': 'customer'})

    url = (f"https://api.weixin.qq.com/sns/jscode2session"
           f"?appid={appid}&secret={secret}&js_code={code}&grant_type=authorization_code")

    try:
        res = requests.get(url, timeout=5).json()
        openid = res.get('openid')
        if not openid:
            logger.warning("微信登录返回无 openid: %s", res)
            return JsonResponse({'role': 'customer'})

        is_admin = AdminUser.objects.filter(openid=openid).exists()
        role = 'admin' if is_admin else 'customer'
        logger.info("用户角色判定: openid=%s -> %s", openid[:8], role)
        return JsonResponse({'role': role})

    except Exception as e:
        logger.error("请求微信接口失败: %s", e)
        return JsonResponse({'role': 'customer'})


# 页面渲染：显示收银台网页
# ⚠️ EdgeOne 不会部署 .html 模板文件，所以内联 HTML
CASHIER_HTML = """<!DOCTYPE html>
<html>
<head>
    <title>一得书苑收银台</title>
    <style>
        .container {
            text-align: center;
            margin-top: 50px;
            font-family: sans-serif;
        }

        #barcode-input {
            padding: 10px;
            width: 300px;
            font-size: 1.2rem;
        }

        .display {
            margin-top: 20px;
            font-size: 1.5rem;
            color: #333;
        }

        #log {
            margin-top: 30px;
            color: #666;
        }

        .action-bar {
            margin-top: 30px;
            padding: 20px 0;
            border-top: 2px dashed #eee;
            text-align: right;
        }

        .btn-reset {
            background-color: #ff4d4f;
            color: white;
            border: none;
            padding: 10px 25px;
            font-size: 18px;
            font-weight: bold;
            border-radius: 8px;
            cursor: pointer;
            margin-left: 50px;
            box-shadow: 0 4px 6px rgba(255, 77, 79, 0.2);
            transition: all 0.3s ease;
            display: inline-flex;
            align-items: center;
        }

        .btn-icon {
            margin-right: 8px;
            font-size: 20px;
        }

        .today-info {
            background: #fff5f5;
            border: 1px solid #ffccc7;
            padding: 15px;
            margin-right: 50px;
            margin-bottom: 20px;
            border-radius: 10px;
            display: inline-block;
            box-shadow: 0 2px 4px rgba(0, 0, 0, 0.05);
        }

        #web-today-total {
            font-family: 'Courier New', Courier, monospace;
            letter-spacing: 1px;
        }
    </style>
</head>
<body>
<div class="container">
    <h1>文具扫码查价</h1>
    <div class="today-info">
        今日实时营收：<span id="web-today-total" style="color: #e64340; font-size: 24px; font-weight: bold;">￥0.00</span>
    </div>
    <input type="text" id="barcode-input" autofocus placeholder="请扫码商品条码...">
    <button class="btn-reset" onclick="resetAll()">
        <span class="btn-icon">🗑️</span>清空重置(不扣库存)
    </button>
    <div class="mode-switch">
        <label>
            <input type="checkbox" id="checkOnly"> 🔍 仅查价（不计入账单）
        </label>
    </div>
    <div class="display">
        <div id="product-name">商品：等待扫码...</div>
        <div id="product-price">价格：-</div>
    </div>

    <div id="log">扫码历史记录...</div>
    <div class="action-bar">

    </div>
</div>

<script>
    const input = document.getElementById('barcode-input');
    const nameDiv = document.getElementById('product-name');
    const priceDiv = document.getElementById('product-price');
    const logDiv = document.getElementById('log');

    setInterval(() => {
        if (document.activeElement !== input) input.focus();
    }, 1000);

    function updateWebStats() {
        fetch('/get_today_stats/')
            .then(res => res.json())
            .then(data => {
                if (data.status === 'success') {
                    const total = parseFloat(data.total_amount) || 0;
                    document.getElementById('web-today-total').innerText = "￥" + total.toFixed(2);
                }
            })
            .catch(err => console.error("营收更新失败:", err));
    }

    updateWebStats();
    setInterval(updateWebStats, 2000);

    function resetAll() {
        if (confirm("确定要清空当前账单吗？(此操作不扣库存，仅用于扫错重来)")) {
            fetch('/reset_cart/')
                .then(res => res.json())
                .then(data => {
                    if (data.status === 'success') location.reload();
                });
        }
    }

    function handlePayment(payCode) {
        window.speechSynthesis.cancel();
        window.speechSynthesis.speak(new SpeechSynthesisUtterance("扫码成功，正在处理结账"));

        fetch('/checkout_cart/')
            .then(res => res.json())
            .then(data => {
                if (data.status === 'success') {
                    window.speechSynthesis.speak(new SpeechSynthesisUtterance("收款成功，今日营业额已更新"));
                    nameDiv.innerText = "✅ 结账完成";
                    priceDiv.innerText = "支付码：" + payCode.substring(0, 4) + "****" + payCode.substring(14);
                    updateWebStats();
                    setTimeout(() => {
                        nameDiv.innerText = "等待扫码...";
                        priceDiv.innerText = "-";
                        logDiv.innerHTML = "账单已结清，扫码开始新订单...";
                    }, 3000);
                } else {
                    alert(data.msg);
                }
            });
    }

    input.addEventListener('keyup', function (e) {
        if (e.key === 'Enter') {
            const code = input.value.trim();
            if (!code) return;

            const isPayCode = /^\d{18}$/.test(code) && (code.startsWith('13') || code.startsWith('28'));

            if (isPayCode) {
                handlePayment(code);
                input.value = '';
                return;
            }

            const isCheckOnly = document.getElementById('checkOnly').checked;
            const apiUrl = isCheckOnly ? '/get_product_by_barcode/?barcode=' + code : '/add_item/?barcode=' + code;

            fetch(apiUrl)
                .then(response => response.json())
                .then(data => {
                    if (data.status === 'success') {
                        const modeText = isCheckOnly ? "【仅查价】" : "当前录入：";
                        nameDiv.innerText = modeText + data.name;
                        priceDiv.innerText = "单价：￥" + data.price;

                        let voiceMsg = data.name + "，" + data.price + "元";
                        if (isCheckOnly) voiceMsg = "注意，查价模式：" + voiceMsg;

                        window.speechSynthesis.cancel();
                        window.speechSynthesis.speak(new SpeechSynthesisUtterance(voiceMsg));

                        if (!isCheckOnly) {
                            const newLog = document.createElement('p');
                            newLog.innerText = new Date().toLocaleTimeString() + ' - ' + data.name + ' (￥' + data.price + ')';
                            logDiv.prepend(newLog);
                        }
                    } else {
                        window.speechSynthesis.cancel();
                        window.speechSynthesis.speak(new SpeechSynthesisUtterance("没找到商品"));
                        nameDiv.innerText = "状态：未找到该商品";
                    }
                    input.value = '';
                })
                .catch(err => {
                    alert("连接失败，请确认后端已开启 get_today_stats 接口");
                    input.value = '';
                });
        }
    });
</script>
</body>
</html>"""

def cash_register(request):
    from django.http import HttpResponse
    return HttpResponse(CASHIER_HTML)


# API 接口：根据条码查商品
def get_product_by_barcode(request):
    barcode = request.GET.get('barcode')
    if not barcode:
        return JsonResponse({'status': 'fail', 'msg': '条码不能为空'})

    product = Product.objects.filter(barcode=barcode).first()
    if not product:
        return JsonResponse({'status': 'fail', 'msg': '未找到商品'})

    return JsonResponse({
        'status': 'success',
        'name': product.name,
        'price': str(product.price),  # Decimal 需要转字符串
        'stock': product.stock,
        'category': product.category  # 返回分类，让前端能回显
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
            'remaining_stock': i.product.stock,
            'category': i.product.category
        })
        total += i.product.price * i.quantity
    return JsonResponse({'items': data, 'total': str(total)})


# 扫码枪调用的接口：负责向购物车添加商品
def add_item(request):
    barcode = request.GET.get('barcode')
    if not barcode:
        return JsonResponse({'status': 'fail', 'msg': '条码不能为空'})

    try:
        with transaction.atomic():
            product = Product.objects.select_for_update().get(barcode=barcode)
            item, created = CartItem.objects.select_for_update().get_or_create(product=product)
            target_quantity = 1 if created else item.quantity + 1

            if product.stock < target_quantity:
                if created:
                    item.delete()
                return JsonResponse({'status': 'fail', 'msg': '库存不足'})

            if not created:
                item.quantity = target_quantity
                item.save(update_fields=['quantity'])

        return JsonResponse({
            'status': 'success',
            'name': product.name,
            'price': str(product.price),
            'current_qty': target_quantity,
            'remaining_stock': product.stock
        })
    except Product.DoesNotExist:
        return JsonResponse({'status': 'fail', 'msg': '未找到商品'})


# 按钮 A：单纯清空（网页端用，用于扫错重来）
def reset_cart(request):
    CartItem.objects.all().delete()
    return JsonResponse({'status': 'success', 'msg': '账单已重置'})


# 删除购物车中的单个商品（按条码或商品ID）
def remove_cart_item(request):
    barcode = request.GET.get('barcode')
    product_id = request.GET.get('product_id')
    if barcode:
        deleted, _ = CartItem.objects.filter(product__barcode=barcode).delete()
    elif product_id:
        deleted, _ = CartItem.objects.filter(product_id=product_id).delete()
    else:
        return JsonResponse({'status': 'fail', 'msg': '请提供 barcode 或 product_id'})
    return JsonResponse({'status': 'success', 'msg': '已移除', 'deleted': deleted})


# 修改购物车中某个商品的数量（按条码或商品ID）
def update_cart_item(request):
    barcode = request.GET.get('barcode')
    product_id = request.GET.get('product_id')
    qty = request.GET.get('quantity')
    try:
        quantity = int(qty)
    except (TypeError, ValueError):
        return JsonResponse({'status': 'fail', 'msg': 'quantity 必须是整数'})

    if quantity <= 0:
        # 数量 <= 0 视为删除
        if barcode:
            CartItem.objects.filter(product__barcode=barcode).delete()
        elif product_id:
            CartItem.objects.filter(product_id=product_id).delete()
        else:
            return JsonResponse({'status': 'fail', 'msg': '请提供 barcode 或 product_id'})
        return JsonResponse({'status': 'success', 'msg': '已移除'})

    try:
        with transaction.atomic():
            if barcode:
                product = Product.objects.select_for_update().get(barcode=barcode)
            else:
                product = Product.objects.select_for_update().get(pk=product_id)

            if product.stock < quantity:
                return JsonResponse({'status': 'fail', 'msg': f'{product.name} 库存不足，仅剩 {product.stock}'})

            item, created = CartItem.objects.select_for_update().get_or_create(product=product)
            item.quantity = quantity
            item.save(update_fields=['quantity'])

        return JsonResponse({
            'status': 'success',
            'name': product.name,
            'price': str(product.price),
            'quantity': quantity,
            'remaining_stock': product.stock
        })
    except Product.DoesNotExist:
        return JsonResponse({'status': 'fail', 'msg': '未找到商品'})


# 按钮 B：正式结账（小程序端用，扣库存+记账）
def checkout_cart(request):
    cart_items = CartItem.objects.select_related('product').all()
    if not cart_items.exists():
        return JsonResponse({'status': 'fail', 'msg': '账单为空'})

    try:
        with transaction.atomic():
            locked_cart_items = []
            for item in cart_items.select_for_update():
                product = Product.objects.select_for_update().get(pk=item.product_id)
                if product.stock < item.quantity:
                    return JsonResponse({
                        'status': 'fail',
                        'msg': f'{product.name} 库存不足，当前库存 {product.stock}，需要 {item.quantity}'
                    })
                locked_cart_items.append((item, product))

            for item, product in locked_cart_items:
                SaleHistory.objects.create(
                    product_name=product.name,
                    price=product.price,
                    quantity=item.quantity
                )

                product.stock -= item.quantity
                product.save(update_fields=['stock'])

            cart_items.delete()

        return JsonResponse({'status': 'success'})
    except Exception as e:
        return JsonResponse({'status': 'fail', 'msg': str(e)})


# 今日营业额
def get_today_stats(request):
    # 使用 Django 提供的 timezone.now()，它会自动处理 settings.py 里的时区
    now = timezone.now()
    today = now.date()

    # 只统计 SaleHistory 即可。
    # 它核销后会自动把商城订单拆解并存入 SaleHistory。
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
    category = request.GET.get('category', 'others')  # 新增：分类参数，默认其他

    try:
        stock = int(request.GET.get('stock', 0))
        price_value = Decimal(str(price)).quantize(Decimal('0.01'))
    except (TypeError, ValueError, InvalidOperation):
        return JsonResponse({'status': 'fail', 'msg': '价格或库存格式不正确'})

    if not barcode or not name:
        return JsonResponse({'status': 'fail', 'msg': '条码和名称不能为空'})
    if stock <= 0:
        return JsonResponse({'status': 'fail', 'msg': '入库数量必须大于0'})
    if price_value < 0:
        return JsonResponse({'status': 'fail', 'msg': '价格不能为负数'})

    # 校验分类有效性
    valid_categories = ['books', 'pens', 'papers', 'stationery', 'correction', 'others']
    if category not in valid_categories:
        category = 'others'

    with transaction.atomic():
        product, created = Product.objects.select_for_update().get_or_create(
            barcode=barcode,
            defaults={
                'name': name,
                'price': price_value,
                'stock': 0,
                'category': category
            }
        )

        if not created:
            product.name = name
            product.price = price_value
            product.category = category  # 允许更新分类

        # 增加库存
        product.stock += stock
        product.save(update_fields=['name', 'price', 'stock', 'category'])

    return JsonResponse({
        'status': 'success',
        'is_new': created,
        'current_stock': product.stock
    })


def get_mall_products(request):
    cat = request.GET.get('category', 'all')
    search = request.GET.get('search', '').strip()

    # 基础查询：必须有库存
    query = Product.objects.filter(stock__gt=0)

    # 如果不是“全部”，则增加分类过滤条件
    if cat != 'all':
        query = query.filter(category=cat)

    # 名称搜索
    if search:
        query = query.filter(name__icontains=search)

    products = query.values('id', 'name', 'price', 'category', 'stock', 'create_time')
    # 按录入时间倒序（新品在前）
    products = products.order_by('-create_time')

    return JsonResponse({
        'status': 'success',
        'list': list(products)
    }, json_dumps_params={'ensure_ascii': False})


# 根据商品名称关键词自动分类（供管理员一键整理用）
# 参考文具行业标准分类体系：书写工具/本册纸品/学生文具/修正粘合/书籍/其他
CATEGORY_KEYWORDS = {
    'books': ['名著', '阅读', '作文', '语文', '英语', '数学', '教材', '练习册', '字典', '词典', '字帖', '绘本', '古诗词', '唐诗', '百科', '知识'],
    'pens': ['中性笔', '圆珠笔', '签字笔', '马克笔', '荧光笔', '水彩笔', '蜡笔', '彩笔', '画笔', '白板笔', '铅笔', '钢笔', '笔芯', '替芯', '墨水', '钢笔水'],
    'papers': ['笔记本', '作业本', '本子', '便签', '方格本', '稿纸', '纸', '打印纸', '复印纸', '活页', '线圈本', '胶套本', '文件袋', '档案袋', '资料册'],
    'stationery': ['橡皮', '擦', '尺', '圆规', '剪刀', '订书', '打孔', '笔袋', '文具盒', '书包', '削笔', '卷笔', '垫板', '美工刀', '切纸', '回形针', '长尾夹', '图钉'],
    'correction': ['修正', '涂改', '改正', '修正带', '修正液', '改正带', '固体胶', '胶水', '胶棒', '胶带', '胶擦', '双面胶'],
}

# 排除关键词：商品名称含这些词则跳过该分类（解决"订书机"含"书"误归名著）
CATEGORY_EXCLUDE = {
    'books': ['订', '装订', '封'],
}

@csrf_exempt
def auto_categorize_products(request):
    """一键自动分类：根据商品名称关键词分配分类"""
    from .models import Product

    count = 0
    for product in Product.objects.all():
        old_cat = product.category
        assigned = False
        for cat, keywords in CATEGORY_KEYWORDS.items():
            # 排除检查：如果商品名包含该分类的排除词，跳过
            exclude_words = CATEGORY_EXCLUDE.get(cat, [])
            if any(kw in product.name for kw in exclude_words):
                continue
            # 关键词匹配
            for kw in keywords:
                if kw in product.name:
                    if product.category != cat:
                        product.category = cat
                        product.save(update_fields=['category'])
                        count += 1
                    assigned = True
                    break
            if assigned:
                break

        # 如果所有分类都没匹配上，且原来的分类也不是 others，归入 others
        if not assigned and old_cat != 'others':
            product.category = 'others'
            product.save(update_fields=['category'])
            count += 1

    return JsonResponse({'status': 'success', 'updated': count})


# 推荐样品商品数据（供店主一键部署到云端）
# 按6大分类体系组织：名著书籍/书写工具/本册纸品/学生文具/修正粘合/其他用品
SEED_PRODUCTS = [
    # ========== 📚 名著书籍 ==========
    ('9787012345671', '新华字典', 25.00, 20, 'books'),
    ('9787012345672', '小学生作文精选', 18.00, 15, 'books'),
    ('9787012345673', '英语四六级词汇', 35.00, 10, 'books'),
    ('9787012345674', '描红字帖', 8.00, 30, 'books'),
    ('9787012345675', '古诗词名篇', 22.00, 12, 'books'),
    ('9787012345676', '成语故事大全', 28.00, 10, 'books'),
    ('9787012345677', '儿童绘本（动物世界）', 15.00, 15, 'books'),

    # ========== 🖊️ 书写工具 ==========
    ('6923456700011', '晨光中性笔 0.5mm 黑', 3.00, 100, 'pens'),
    ('6923456700012', '晨光中性笔 0.5mm 红', 3.00, 50, 'pens'),
    ('6923456700013', '2B铅笔（含橡皮头）', 2.00, 80, 'pens'),
    ('6923456700014', '荧光笔（黄色）', 4.50, 30, 'pens'),
    ('6923456700015', '马克笔12色套装', 18.00, 15, 'pens'),
    ('6923456700016', '英雄钢笔', 25.00, 10, 'pens'),
    ('6923456700017', '中性笔芯 0.5mm 黑（20支装）', 10.00, 40, 'pens'),
    ('6923456700018', '圆珠笔 蓝', 2.00, 50, 'pens'),
    ('6923456700019', '自动铅笔 0.5mm', 5.00, 30, 'pens'),

    # ========== 📓 本册纸品 ==========
    ('6923456700041', 'A5笔记本 横线', 6.00, 50, 'papers'),
    ('6923456700042', 'A4文件袋（透明）', 3.00, 40, 'papers'),
    ('6923456700101', '英语练习本', 2.00, 60, 'papers'),
    ('6923456700102', '方格算术本', 2.00, 60, 'papers'),
    ('6923456700103', '便利贴（彩色）', 3.50, 30, 'papers'),
    ('6923456700109', 'A4复印纸（500张）', 25.00, 10, 'papers'),
    ('6923456700110', '草稿本', 3.00, 30, 'papers'),

    # ========== 📐 学生文具 ==========
    ('6923456700021', '4B绘图橡皮', 2.50, 40, 'stationery'),
    ('6923456700022', '美术橡皮擦（可塑）', 3.50, 25, 'stationery'),
    ('6923456700023', '磨砂橡皮擦', 3.00, 30, 'stationery'),
    ('6923456700045', '尺子 15cm', 2.00, 30, 'stationery'),
    ('6923456700043', '学生剪刀', 5.00, 20, 'stationery'),
    ('6923456700104', '圆规套装', 8.00, 15, 'stationery'),
    ('6923456700105', '卷笔刀', 3.00, 25, 'stationery'),
    ('6923456700106', '订书机（小号）', 8.00, 10, 'stationery'),
    ('6923456700107', '订书钉（小盒）', 2.00, 20, 'stationery'),
    ('6923456700111', '长尾夹（彩色混合）', 4.00, 15, 'stationery'),
    ('6923456700112', '回形针（100枚）', 2.00, 20, 'stationery'),

    # ========== 📦 修正粘合 ==========
    ('6923456700031', '修正带 标准款', 3.50, 40, 'correction'),
    ('6923456700032', '修正带 迷你款', 2.00, 50, 'correction'),
    ('6923456700033', '修正液', 3.00, 20, 'correction'),
    ('6923456700034', '透明胶带', 2.00, 30, 'correction'),
    ('6923456700044', '固体胶棒', 2.50, 35, 'correction'),
    ('6923456700108', '双面胶', 2.00, 25, 'correction'),

    # ========== 📎 其他 ==========
    ('6923456700113', '计算器（8位）', 15.00, 5, 'others'),
    ('6923456700114', '桌面台历', 8.00, 10, 'others'),
]


@csrf_exempt
def seed_sample_products(request):
    """一键部署示例商品数据到云端数据库（覆盖更新，确保分类正确）"""
    from .models import Product
    from decimal import Decimal

    added = 0
    updated = 0
    for barcode, name, price, stock, category in SEED_PRODUCTS:
        product, created = Product.objects.get_or_create(
            barcode=barcode,
            defaults={
                'name': name,
                'price': Decimal(str(price)),
                'stock': stock,
                'category': category,
            }
        )
        if created:
            added += 1
        else:
            # 条码已存在 → 全覆盖更新（名称/价格/库存/分类全部刷新）
            product.name = name
            product.price = Decimal(str(price))
            product.stock = stock
            product.category = category
            product.save(update_fields=['name', 'price', 'stock', 'category'])
            updated += 1

    return JsonResponse({
        'status': 'success',
        'added': added,
        'updated': updated,
        'total': len(SEED_PRODUCTS),
        'msg': f'新增 {added} 个商品，补充 {updated} 个商品库存',
    })


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
            requested_items = {}
            for item in cart:
                product_id = int(item.get('id'))
                count = int(item.get('num', 0))
                if count <= 0:
                    return JsonResponse({'status': 'fail', 'msg': '商品数量必须大于0'})
                requested_items[product_id] = requested_items.get(product_id, 0) + count

            order_items = []
            total = Decimal('0.00')
            products = Product.objects.select_for_update().filter(id__in=requested_items.keys())
            product_map = {product.id: product for product in products}
            if len(product_map) != len(requested_items):
                return JsonResponse({'status': 'fail', 'msg': '订单商品数据不正确'})

            for product_id, count in requested_items.items():
                product = product_map[product_id]
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
    low_stock_count = Product.objects.filter(stock__lte=5).count()
    return JsonResponse({'count': count, 'low_stock_count': low_stock_count})


def get_pending_orders(request):
    limit = min(max(get_request_int(request.GET.get('limit'), 10), 1), 50)
    orders = Order.objects.filter(status=0).prefetch_related('items__product').order_by('create_time')[:limit]
    return JsonResponse({
        'status': 'success',
        'list': [serialize_order(order) for order in orders]
    }, json_dumps_params={'ensure_ascii': False})


def get_low_stock_products(request):
    threshold = min(max(get_request_int(request.GET.get('threshold'), 5), 0), 9999)
    limit = min(max(get_request_int(request.GET.get('limit'), 10), 1), 100)
    base_query = Product.objects.filter(stock__lte=threshold)
    total_count = base_query.count()
    products = list(
        base_query.order_by('stock', 'name')[:limit]
        .values('id', 'barcode', 'name', 'stock', 'price', 'category')
    )
    return JsonResponse({
        'status': 'success',
        'threshold': threshold,
        'total_count': total_count,
        'list': products
    }, json_dumps_params={'ensure_ascii': False})


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
            'order': serialize_order(order)
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
            locked_order_items = []
            # 扣库存逻辑（和你 admin.py 里写的一样）
            for item in order.items.select_related('product').all():
                product = Product.objects.select_for_update().get(pk=item.product_id)
                if product.stock < item.count:
                    return JsonResponse({
                        'status': 'fail',
                        'msg': f'{product.name} 库存不足，当前库存 {product.stock}，需要 {item.count}'
                    })
                locked_order_items.append((item, product))

            for item, product in locked_order_items:
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


# 健康检查接口（用于部署后快速诊断）
def health_check(request):
    diagnostics = {
        'status': 'ok',
        'debug': settings.DEBUG,
        'database': 'unknown',
        'tables': {},
        'allowed_hosts': settings.ALLOWED_HOSTS,
    }

    try:
        from django.db import connection
        with connection.cursor() as cursor:
            cursor.execute("SELECT table_name FROM information_schema.tables WHERE table_schema = 'public' ORDER BY table_name")
            tables = [row[0] for row in cursor.fetchall()]
            diagnostics['tables']['all'] = tables

            # Check if auth_user table exists (required for admin login)
            has_auth_user = 'auth_user' in tables
            diagnostics['tables']['has_auth_user'] = has_auth_user
            if has_auth_user:
                cursor.execute("SELECT count(*) FROM auth_user")
                diagnostics['tables']['user_count'] = cursor.fetchone()[0]

        diagnostics['database'] = 'connected'
    except Exception as e:
        diagnostics['database'] = f'error: {e}'

    return JsonResponse(diagnostics)
