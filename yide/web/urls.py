from django.urls import path
from . import views

urlpatterns = [
    # 将原来的 'web/' 改为 ''
    # 这样：主路由的 "" + 子路由的 "" = 最终的根路径 "/"
    path('', views.cash_register, name='cashier'),  # 电脑端收银页面
    path('add_item/', views.add_item, name='add_item'),  # 电脑扫码枪调用
    path('get_cart_status/', views.get_cart_status, name='get_cart_status'),  # 小程序/网页同步显示
    path('reset_cart/', views.reset_cart, name='reset_cart'),  # 网页清空用
    path('checkout_cart/', views.checkout_cart, name='checkout_cart'),  # 小程序结账用
    path('get_product_by_barcode/', views.get_product_by_barcode, name='get_product_by_barcode'),  # 仅查价调用
    path('get_today_stats/', views.get_today_stats, name='get_today_stats'),  # 今日销售额调用
    path('api/check_role/', views.check_role, name='check_role'),  # 小程序openid白名单
    path('api/mall_products/', views.get_mall_products, name='mall_products'),  # 小程序线上商城商品
    path('api/submit_order/', views.submit_order, name='submit_order'),  # 小程序线上商城结算
    path('api/get_new_order_count/', views.get_new_order_count, name='get_new_order_count'),  # 查询状态为 0 (待取货) 的订单数量
    path('api/search_order/', views.search_order, name='search_order'),  # 查询状态为 0 (待取货) 的订单
    path('api/verify_order/', views.verify_order, name='verify_order'),  # 核销状态为 0 (待取货) 的订单
]
