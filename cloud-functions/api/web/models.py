import uuid

from django.db import models

class Product(models.Model):
    # 定义分类选项
    CATEGORY_CHOICES = [
        ('books', '名著书籍'),
        ('pens', '书写工具'),
        ('papers', '本册纸品'),
        ('stationery', '学生文具'),
        ('correction', '修正粘合'),
        ('others', '其他用品'),
    ]
    # barcode 是条码，设为唯一索引，方便扫码枪秒查
    barcode = models.CharField(max_length=50, unique=True, verbose_name="条形码")
    name = models.CharField(max_length=100, verbose_name="文具名称")
    # max_digits=10, decimal_places=2 表示最大千万级，保留两位小数
    price = models.DecimalField(max_digits=10, decimal_places=2, verbose_name="价格")
    stock = models.IntegerField(default=0, verbose_name="库存数量")
    category = models.CharField("分类", max_length=20, choices=CATEGORY_CHOICES, default='others')
    image_url = models.URLField("商品图片链接", max_length=500, blank=True, default='')
    create_time = models.DateTimeField(auto_now_add=True, verbose_name="录入时间")

    def __str__(self):
        return f"{self.name} ({self.barcode})"

    class Meta:
        verbose_name = "商品"
        verbose_name_plural = "商品管理"

class CartItem(models.Model):
    # 简单的购物车：这里假设店里只有一个收银台，所以直接存
    product = models.ForeignKey(Product, on_delete=models.CASCADE, verbose_name="商品")
    quantity = models.IntegerField(default=1, verbose_name="数量")
    added_at = models.DateTimeField(auto_now_add=True, verbose_name="添加时间")

    class Meta:
        verbose_name = "购物车"
        verbose_name_plural = "购物车管理"

class SaleHistory(models.Model):
    product_name = models.CharField(max_length=100, verbose_name="商品名称")
    price = models.DecimalField(max_digits=10, decimal_places=2, verbose_name="单价")
    quantity = models.IntegerField(verbose_name="数量")
    sale_date = models.DateTimeField(auto_now_add=True, verbose_name="销售时间") # 自动记录卖出的时间

    def __str__(self):
        return f"{self.sale_date.strftime('%Y-%m-%d %H:%M')} - {self.product_name}"

    class Meta:
        verbose_name = "销售记录"
        verbose_name_plural = "销售历史"

# 增加一个简单的白名单表
class AdminUser(models.Model):
    openid = models.CharField("微信OpenID", max_length=100, unique=True)
    name = models.CharField("备注名称", max_length=50)

    def __str__(self):
        return self.name


class Order(models.Model):
    # 生成一个唯一的短编号，比如：YD202310240001
    order_sn = models.CharField("订单编号", max_length=50, unique=True, editable=False, null=True)
    customer_name = models.CharField("取货人姓名", max_length=50)
    total_price = models.DecimalField("总价", max_digits=10, decimal_places=2)
    create_time = models.DateTimeField("下单时间", auto_now_add=True)
    status = models.IntegerField("状态", choices=[(0, '待取货'), (1, '已完成')], default=0)

    def save(self, *args, **kwargs):
        if not self.order_sn:
            import datetime
            now = datetime.datetime.now()
            self.order_sn = now.strftime('%Y%m%d%H%M%S') + uuid.uuid4().hex[:8].upper()
        super().save(*args, **kwargs)

    class Meta:
        verbose_name = "商城订单"
        verbose_name_plural = "商城订单管理"

class OrderItem(models.Model):
    order = models.ForeignKey(Order, related_name='items', on_delete=models.CASCADE, verbose_name="所属订单")
    product = models.ForeignKey(Product, on_delete=models.CASCADE, verbose_name="商品")
    count = models.IntegerField("数量")

    class Meta:
        verbose_name = "订单商品"
        verbose_name_plural = "订单商品明细"