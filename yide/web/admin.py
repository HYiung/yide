from django.contrib import admin
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils.safestring import mark_safe

from .models import AdminUser, CartItem, Order, OrderItem, Product, SaleHistory


# 1. 订单详情嵌入
class OrderItemInline(admin.TabularInline):
    model = OrderItem
    extra = 0
    readonly_fields = ('product', 'count')
    verbose_name = "商品明细"
    verbose_name_plural = "商品明细"


# 2. 商城订单管理
@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    # 重点：把 order_sn 放在第一位，方便长辈核对编号
    list_display = ('order_sn_link', 'customer_name', 'total_price', 'status', 'status_colored', 'create_time')

    # 只有 status 可以在列表页直接勾选修改
    list_editable = ('status',)

    # 侧边栏可以按状态和时间过滤
    list_filter = ('status', 'create_time')

    # 搜索框支持按姓名和订单号搜索
    search_fields = ('customer_name', 'order_sn')

    # 日期快速导航
    date_hierarchy = 'create_time'

    # 订单编号是自动生成的，设为只读，防止后台误改
    readonly_fields = ('order_sn', 'create_time')

    # 列表页每页显示条数
    list_per_page = 20

    inlines = [OrderItemInline]

    # ---------- 自定义显示 ----------

    def order_sn_link(self, obj):
        """订单号可点击跳转详情"""
        from django.urls import reverse
        url = reverse('admin:web_order_change', args=[obj.pk])
        return mark_safe(f'<a href="{url}" style="font-family:monospace;">{obj.order_sn}</a>')
    order_sn_link.short_description = "订单编号"
    order_sn_link.admin_order_field = 'order_sn'

    def status_colored(self, obj):
        """状态显示为彩色标签"""
        if obj.status == 1:
            return mark_safe('<span style="color:#07c160;font-weight:bold;">✅ 已完成</span>')
        return mark_safe('<span style="color:#faad14;font-weight:bold;">⏳ 待取货</span>')
    status_colored.short_description = "状态"
    status_colored.admin_order_field = 'status'

    def save_model(self, request, obj, form, change):
        # 如果是修改操作，且状态被改成了“已完成(1)”
        if change and obj.status == 1:
            # 这里的 pk 是主键，用来获取修改前的原始数据
            old_obj = Order.objects.get(pk=obj.pk)
            # 只有从“待取货(0)”变成“已完成(1)”时才触发扣库存
            if old_obj.status == 0:
                with transaction.atomic():
                    # 通过 related_name='items' 获取所有商品明细
                    for item in obj.items.select_related('product').all():
                        product = Product.objects.select_for_update().get(pk=item.product_id)
                        if product.stock < item.count:
                            raise ValidationError(
                                f'{product.name} 库存不足，当前库存 {product.stock}，需要 {item.count}'
                            )

                        product.stock -= item.count
                        product.save(update_fields=['stock'])

                        # 记录到销售历史，这样 get_today_stats 就能统计到这笔收入
                        SaleHistory.objects.create(
                            product_name=product.name,
                            price=product.price,
                            quantity=item.count
                        )
        super().save_model(request, obj, form, change)


# 3. 店主身份确认
@admin.register(AdminUser)
class AdminUserAdmin(admin.ModelAdmin):
    list_display = ('name', 'openid')
    search_fields = ('name', 'openid')


# 4. 商品库管理
@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ('barcode', 'name', 'category', 'price', 'stock', 'create_time')
    list_editable = ('price', 'stock')
    list_filter = ('category', 'create_time') # 增加分类筛选
    search_fields = ('barcode', 'name')
    ordering = ('-create_time',)
    actions = ['auto_categorize']

    def auto_categorize(self, request, queryset):
        """根据商品名称关键词自动分类"""
        CATEGORY_KEYWORDS = {
            'books': ['书', '本', '名著', '阅读', '作文', '语文', '英语', '数学', '教材', '练习册', '字典', '词典', '字帖', '绘本'],
            'pens': ['笔', '铅笔', '钢笔', '圆珠笔', '签字笔', '马克笔', '荧光笔', '水彩笔', '蜡笔', '中性笔', '彩笔', '画笔', '白板笔'],
            'erasers': ['橡皮', '擦', '胶擦'],
            'correction': ['修正', '涂改', '改正', '胶带', '修正带', '修正液', '改正带'],
        }
        count = 0
        for product in queryset:
            for cat, keywords in CATEGORY_KEYWORDS.items():
                for kw in keywords:
                    if kw in product.name:
                        if product.category != cat:
                            product.category = cat
                            product.save(update_fields=['category'])
                            count += 1
                        break
                else:
                    continue
                break
        self.message_user(request, f'已自动分类 {count} 个商品')
    auto_categorize.short_description = '🤖 按名称关键词自动分类'


# 5. 购物车管理（方便查看当前购物车状态）
@admin.register(CartItem)
class CartItemAdmin(admin.ModelAdmin):
    list_display = ('product', 'quantity', 'added_at')
    list_display_links = ('product',)
    ordering = ('-added_at',)


# 6. 销售历史管理
@admin.register(SaleHistory)
class SaleHistoryAdmin(admin.ModelAdmin):
    list_display = ('product_name', 'quantity', 'price', 'get_sale_time')
    ordering = ('-sale_date',)
    list_filter = ('sale_date',)

    def get_sale_time(self, obj):
        return obj.sale_date.strftime('%Y-%m-%d %H:%M:%S')
    get_sale_time.short_description = '销售时间'
