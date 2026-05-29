from django.contrib import admin
from django.core.exceptions import ValidationError
from django.db import transaction

from .models import Product, SaleHistory, AdminUser, OrderItem, Order

# 1. 订单详情嵌入
class OrderItemInline(admin.TabularInline):
    model = OrderItem
    extra = 0
    readonly_fields = ('product', 'count')

# 2. 商城订单管理
# admin.py

@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    # 重点：把 order_sn 放在第一位，方便长辈核对编号
    list_display = ('order_sn', 'customer_name', 'total_price', 'status', 'create_time')

    # 只有 status 可以在列表页直接勾选修改
    list_editable = ('status',)

    # 侧边栏可以按状态和时间过滤
    list_filter = ('status', 'create_time')

    # 搜索框支持按姓名和订单号搜索
    search_fields = ('customer_name', 'order_sn')

    # 订单编号是自动生成的，设为只读，防止后台误改
    readonly_fields = ('order_sn', 'create_time')

    inlines = [OrderItemInline]

    def save_model(self, request, obj, form, change):
        # 如果是修改操作，且状态被改成了“已完成(1)”
        if change and obj.status == 1:
            old_obj = Order.objects.get(pk=obj.pk)
            # 只有从“待取货(0)”变成“已完成(1)”时才触发扣库存
            if old_obj.status == 0:
                with transaction.atomic():
                    order_items = obj.items.select_related('product').select_for_update()
                    for item in order_items:
                        product = item.product
                        if product.stock < item.count:
                            raise ValidationError(f'{product.name}库存不足，当前仅剩{product.stock}件')
                        product.stock -= item.count
                        product.save(update_fields=['stock'])

                        # 记录到销售历史，这样 get_today_stats 就能统计到这笔收入
                        SaleHistory.objects.create(
                            product_name=product.name,
                            price=product.price,
                            quantity=item.count
                        )
                    super().save_model(request, obj, form, change)
                return
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

# 5. 销售历史管理
@admin.register(SaleHistory)
class SaleHistoryAdmin(admin.ModelAdmin):
    list_display = ('product_name', 'quantity', 'price', 'get_sale_time')
    ordering = ('-sale_date',)
    list_filter = ('sale_date',)

    def get_sale_time(self, obj):
        return obj.sale_date.strftime('%Y-%m-%d %H:%M:%S')
    get_sale_time.short_description = '销售时间'