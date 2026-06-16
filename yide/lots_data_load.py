import pandas as pd
from django.http import HttpResponse
from web.models import Product

def import_products_excel(request):
    # 假设你把 excel 放在项目根目录叫 products.xlsx
    excel_file = 'products.xlsx'
    try:
        df = pd.read_excel(excel_file)
        for _, row in df.iterrows():
            # update_or_create: 如果条码存在就更新，不存在就新建
            Product.objects.update_or_create(
                barcode=str(row['条码']).strip(),
                defaults={
                    'name': row['名称'],
                    'price': row['价格'],
                    'stock': row['库存']
                }
            )
        return HttpResponse("✅ 批量导入成功！")
    except Exception as e:
        return HttpResponse(f"❌ 导入失败: {str(e)}")