"""
批量从 Excel 导入商品数据

用法：
    python yide/lots_data_load.py <excel_path>

Excel 必须包含以下列：
    条码, 名称, 价格, 库存

示例：
    python yide/lots_data_load.py products.xlsx
"""

import os
import sys

# 设置 Django 环境
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'yide.settings')

import django
django.setup()

import pandas as pd
from web.models import Product


def import_products(excel_path):
    try:
        df = pd.read_excel(excel_path)
    except FileNotFoundError:
        print(f"❌ 文件不存在: {excel_path}")
        return 1
    except Exception as e:
        print(f"❌ 读取 Excel 失败: {e}")
        return 1

    required_cols = {'条码', '名称', '价格', '库存'}
    missing = required_cols - set(df.columns)
    if missing:
        print(f"❌ Excel 缺少必要列: {', '.join(missing)}")
        return 1

    success = 0
    for idx, row in df.iterrows():
        try:
            barcode = str(row.get('条码', '')).strip()
            if not barcode:
                print(f"  ❌ 第 {idx+2} 行条码为空，跳过")
                continue

            price_val = float(row['价格']) if pd.notna(row.get('价格')) else 0.0
            stock_val = int(row['库存']) if pd.notna(row.get('库存')) else 0

            product, created = Product.objects.update_or_create(
                barcode=barcode,
                defaults={
                    'name': str(row.get('名称', '')),
                    'price': price_val,
                    'stock': stock_val,
                }
            )
            action = "新建" if created else "更新"
            print(f"  {action}: {product.name} ({product.barcode})")
            success += 1
        except Exception as e:
            print(f"  ❌ 导入失败: {row.get('条码', '?')} - {e}")

    print(f"\n✅ 导入完成，共处理 {success} 条记录")
    return 0


if __name__ == '__main__':
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    sys.exit(import_products(sys.argv[1]))
