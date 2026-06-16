import os
import django
import random

# 1. 设置 Django 环境
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'yide.settings')  # 确保这里是你项目文件夹的名字
django.setup()

from web.models import Product, CartItem


def run():
    names = ["晨光中性笔", "得力A4纸", "英雄墨水", "米家铅笔", "修正带", "订书机", "2B铅笔", "水彩笔", "笔记本", "直尺"]

    # 清空旧数据（可选）
    Product.objects.all().delete()
    CartItem.objects.all().delete()

    for i in range(10):
        barcode = f"69012345678{i}"
        name = random.choice(names) + str(i)
        price = round(random.uniform(1.5, 45.0), 2)
        stock = random.randint(10, 100)

        Product.objects.create(barcode=barcode, name=name, price=price, stock=stock)
        print(f"成功生成商品: {name} [条码: {barcode}]")


if __name__ == '__main__':
    run()