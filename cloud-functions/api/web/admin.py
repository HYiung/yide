from django.contrib import admin
from django.utils.safestring import mark_safe
from django.utils.html import format_html
from django.urls import reverse
from django.http import HttpResponseRedirect
from django.contrib import messages

from .catalog import auto_categorize_queryset
from .models import AdminUser, CartItem, Order, OrderItem, Product, SaleHistory
from .services import complete_order


# ===== 辅助函数 =====
CATEGORY_COLORS = {
    'books': '#667eea', 'pens': '#f5576c', 'papers': '#4facfe',
    'stationery': '#43e97b', 'correction': '#fa709a', 'others': '#a8edea',
}
CATEGORY_NAMES = dict(Product.CATEGORY_CHOICES)

def category_badge(cat):
    color = CATEGORY_COLORS.get(cat, '#999')
    name = CATEGORY_NAMES.get(cat, cat)
    return format_html('<span style="background:{};color:#fff;padding:2px 10px;border-radius:10px;font-size:12px;">{}</span>', color, name)

def stock_badge(stock):
    if stock <= 0:
        return format_html('<span style="color:#f5222d;font-weight:700;">售罄</span>')
    if stock <= 3:
        return format_html('<span style="color:#f5222d;font-weight:600;">⚠️ {}</span>', stock)
    if stock <= 10:
        return format_html('<span style="color:#fa8c16;font-weight:600;">{}</span>', stock)
    return format_html('<span style="color:#52c41a;">{}</span>', stock)

def status_badge(status):
    if status == 0:
        return format_html('<span style="background:#fa8c16;color:#fff;padding:2px 12px;border-radius:10px;font-size:12px;font-weight:600;">待取货</span>')
    return format_html('<span style="background:#52c41a;color:#fff;padding:2px 12px;border-radius:10px;font-size:12px;font-weight:600;">已完成</span>')


# ===== 1. 订单详情嵌入 =====
class OrderItemInline(admin.TabularInline):
    model = OrderItem
    extra = 0
    readonly_fields = ('product', 'count')
    verbose_name = "商品明细"
    verbose_name_plural = "商品明细"


# ===== 2. 商城订单管理 =====
@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ('order_sn_link', 'customer_name', 'total_price', 'colored_status', 'colored_create_time')
    list_editable = ()
    list_filter = ('status', 'create_time')
    search_fields = ('customer_name', 'order_sn')
    date_hierarchy = 'create_time'
    readonly_fields = ('order_sn', 'create_time')
    ordering = ('-create_time',)
    list_per_page = 20
    actions = ['mark_as_completed', 'mark_as_pending']
    inlines = [OrderItemInline]
    list_select_related = True

    fieldsets = (
        ('订单信息', {
            'fields': ('order_sn', 'customer_name', 'total_price', 'status', 'create_time')
        }),
    )

    # ---------- 自定义列表列 ----------

    def order_sn_link(self, obj):
        url = reverse('admin:web_order_change', args=[obj.pk])
        return format_html('<a href="{}" style="font-weight:600;text-decoration:none;">{}</a>', url, obj.order_sn)
    order_sn_link.short_description = '订单号'
    order_sn_link.admin_order_field = 'order_sn'

    def colored_status(self, obj):
        return status_badge(obj.status)
    colored_status.short_description = '状态'
    colored_status.admin_order_field = 'status'

    def colored_create_time(self, obj):
        return obj.create_time.strftime('%m-%d %H:%M')
    colored_create_time.short_description = '下单时间'
    colored_create_time.admin_order_field = 'create_time'

    # ---------- 批量操作 ----------

    def mark_as_completed(self, request, queryset):
        success = 0
        for order in queryset:
            if order.status == 1:
                continue
            try:
                complete_order(order)
                success += 1
            except Exception as exc:
                self.message_user(request, f'❌ {order.order_sn}: {exc}', messages.ERROR)
                break
        if success:
            self.message_user(request, f'✅ {success} 个订单已完成并扣库存', messages.SUCCESS)
    mark_as_completed.short_description = '✅ 标记为已完成（扣库存）'

    def mark_as_pending(self, request, queryset):
        count = queryset.exclude(status=0).update(status=0)
        self.message_user(request, f'已将 {count} 个订单恢复为待取货', messages.WARNING)
    mark_as_pending.short_description = '⏳ 恢复为待取货'

    def save_model(self, request, obj, form, change):
        should_complete = False
        if change and obj.status == 1:
            old_obj = Order.objects.get(pk=obj.pk)
            should_complete = old_obj.status == 0
            if should_complete:
                obj.status = 0
        super().save_model(request, obj, form, change)
        if should_complete:
            complete_order(obj)


# ===== 3. 店主身份确认 =====
@admin.register(AdminUser)
class AdminUserAdmin(admin.ModelAdmin):
    list_display = ('name', 'openid')
    search_fields = ('name', 'openid')
    list_per_page = 50


# ===== 4. 商品库管理 =====
@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ('barcode', 'name', 'price', 'stock', 'image_url', 'colored_category', 'colored_stock', 'has_image', 'short_time')
    list_editable = ('name', 'price', 'stock', 'image_url')
    list_filter = ('category', 'create_time')
    search_fields = ('barcode', 'name')
    ordering = ('-create_time',)
    list_per_page = 25
    actions = ['auto_categorize']

    fieldsets = (

        ('基本信息', {
            'fields': ('barcode', 'name', 'category')
        }),
        ('价格与库存', {
            'fields': ('price', 'stock')
        }),
        ('商品图片', {
            'fields': ('image_url',),
            'description': '输入商品图片链接（URL），支持任意图床链接。留空则使用 Emoji 占位。'
        }),
    )

    def colored_category(self, obj):
        return category_badge(obj.category)
    colored_category.short_description = '分类'
    colored_category.admin_order_field = 'category'

    def price_display(self, obj):
        return format_html('￥<strong>{}</strong>', obj.price)
    price_display.short_description = '价格'
    price_display.admin_order_field = 'price'

    def colored_stock(self, obj):
        return stock_badge(obj.stock)
    colored_stock.short_description = '库存'
    colored_stock.admin_order_field = 'stock'

    def short_time(self, obj):
        return obj.create_time.strftime('%m-%d')
    short_time.short_description = '录入'
    short_time.admin_order_field = 'create_time'

    def has_image(self, obj):
        if obj.image_url:
            return format_html(
                '<a href="{}" target="_blank" style="display:inline-block;width:36px;height:36px;">'
                '<img src="{}" style="width:36px;height:36px;object-fit:cover;border-radius:4px;" '
                'onerror="this.style.display=\'none\'"></a>',
                obj.image_url, obj.image_url
            ) + format_html(
                '<span style="color:#07c160;font-size:11px;"> ✅</span>'
            )
        return format_html('<span style="color:#ccc;">无图</span>')
    has_image.short_description = '图片'
    has_image.admin_order_field = 'image_url'

    def formfield_for_dbfield(self, db_field, request, **kwargs):
        """Keep editable product-list inputs compact without injecting <style> tags into rows."""
        formfield = super().formfield_for_dbfield(db_field, request, **kwargs)
        if db_field.name in ('name', 'image_url') and formfield is not None:
            formfield.widget.attrs.update({
                'style': 'max-width:160px;overflow:hidden;text-overflow:ellipsis;',
            })
        return formfield

    def auto_categorize(self, request, queryset):
        count = auto_categorize_queryset(queryset)
        self.message_user(request, f'已自动分类 {count} 个商品')
    auto_categorize.short_description = '🤖 按名称关键词自动分类'


# ===== 5. 购物车管理 =====
@admin.register(CartItem)
class CartItemAdmin(admin.ModelAdmin):
    list_display = ('product', 'quantity', 'added_at')
    list_display_links = ('product',)
    ordering = ('-added_at',)
    list_per_page = 30


# ===== 6. 销售历史管理 =====
@admin.register(SaleHistory)
class SaleHistoryAdmin(admin.ModelAdmin):
    list_display = ('product_name', 'quantity', 'subtotal', 'sale_time')
    ordering = ('-sale_date',)
    list_filter = ('sale_date',)
    list_per_page = 30
    date_hierarchy = 'sale_date'

    def subtotal(self, obj):
        return format_html('￥<strong>{}</strong>', (obj.price * obj.quantity))
    subtotal.short_description = '小计'
    subtotal.admin_order_field = 'price'

    def sale_time(self, obj):
        return obj.sale_date.strftime('%m-%d %H:%M')
    sale_time.short_description = '销售时间'
    sale_time.admin_order_field = 'sale_date'
