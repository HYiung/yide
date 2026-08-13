"""Catalog helpers shared by views and admin actions."""

from .models import Product

LOW_STOCK_THRESHOLD = 5

CATEGORY_KEYWORDS = {
    'books': ['名著', '阅读', '作文', '语文', '英语', '数学', '教材', '练习册', '字典', '词典', '字帖', '绘本', '古诗词', '唐诗', '百科', '知识'],
    'pens': ['中性笔', '圆珠笔', '签字笔', '马克笔', '荧光笔', '水彩笔', '蜡笔', '彩笔', '画笔', '白板笔', '铅笔', '钢笔', '笔芯', '替芯', '墨水', '钢笔水'],
    'papers': ['笔记本', '作业本', '本子', '便签', '方格本', '稿纸', '纸', '打印纸', '复印纸', '活页', '线圈本', '胶套本', '文件袋', '档案袋', '资料册'],
    'stationery': ['橡皮', '擦', '尺', '圆规', '剪刀', '订书', '打孔', '笔袋', '文具盒', '书包', '削笔', '卷笔', '垫板', '美工刀', '切纸', '回形针', '长尾夹', '图钉'],
    'correction': ['修正', '涂改', '改正', '修正带', '修正液', '改正带', '固体胶', '胶水', '胶棒', '胶带', '胶擦', '双面胶'],
}

CATEGORY_EXCLUDE = {
    'books': ['订', '装订', '封'],
}


def classify_product_name(name):
    """Return the best category key for a product name."""
    name = name or ''
    for category, keywords in CATEGORY_KEYWORDS.items():
        if any(word in name for word in CATEGORY_EXCLUDE.get(category, [])):
            continue
        if any(word in name for word in keywords):
            return category
    return 'others'


def auto_categorize_queryset(queryset):
    """Apply keyword categorization to a queryset and return changed count."""
    updated = 0
    for product in queryset:
        category = classify_product_name(product.name)
        if product.category != category:
            product.category = category
            product.save(update_fields=['category'])
            updated += 1
    return updated


def low_stock_queryset(threshold=LOW_STOCK_THRESHOLD):
    return Product.objects.filter(stock__lte=threshold)
