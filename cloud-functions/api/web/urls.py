from django.urls import path
from . import views

urlpatterns = [
    # 根路径 → 线上商城 H5（顾客线上下单）
    path('', views.mall_home, name='mall'),
    path('cashier/', views.cash_register, name='cashier'),  # 店长收银台 + 看板（需登录）
    path('cashier/login/', views.cashier_login, name='cashier_login'),  # 店长登录
    path('cashier/logout/', views.cashier_logout, name='cashier_logout'),  # 退出登录
    path('add_item/', views.add_item, name='add_item'),  # 电脑扫码枪调用
    path('get_cart_status/', views.get_cart_status, name='get_cart_status'),  # 小程序/网页同步显示
    path('reset_cart/', views.reset_cart, name='reset_cart'),  # 网页清空用
    path('remove_cart_item/', views.remove_cart_item, name='remove_cart_item'),  # 删除单个购物车商品
    path('update_cart_item/', views.update_cart_item, name='update_cart_item'),  # 修改购物车商品数量
    path('checkout_cart/', views.checkout_cart, name='checkout_cart'),  # 小程序结账用
    path('get_product_by_barcode/', views.get_product_by_barcode, name='get_product_by_barcode'),  # 仅查价调用
    path('get_today_stats/', views.get_today_stats, name='get_today_stats'),  # 今日销售额调用
    path('quick_add_product/', views.quick_add_product, name='quick_add_product'),  # 小程序扫码入库
    path('api/check_role/', views.check_role, name='check_role'),  # 小程序openid白名单
    path('api/mall_products/', views.get_mall_products, name='mall_products'),  # 小程序线上商城商品
    path('api/submit_order/', views.submit_order, name='submit_order'),  # 小程序线上商城结算
    path('api/get_new_order_count/', views.get_new_order_count, name='get_new_order_count'),  # 查询状态为 0 (待取货) 的订单数量
    path('api/pending_orders/', views.get_pending_orders, name='pending_orders'),  # 待取货订单列表
    path('api/low_stock_products/', views.get_low_stock_products, name='low_stock_products'),  # 低库存提醒
    path('api/search_order/', views.search_order, name='search_order'),  # 查询状态为 0 (待取货) 的订单
    path('api/verify_order/', views.verify_order, name='verify_order'),  # 核销状态为 0 (待取货) 的订单
    path('api/health/', views.health_check, name='health_check'),  # 健康检查
    path('api/dashboard_stats/', views.dashboard_stats, name='dashboard_stats'),  # 仪表盘统计数据
    path('api/dashboard_all/', views.dashboard_all, name='dashboard_all'),  # 综合看板数据（合并5个请求为1）
    path('api/today_detail/', views.today_detail, name='today_detail'),  # 今日销售明细（弹窗用）
    path('api/auto_categorize/', views.auto_categorize_products, name='auto_categorize'),  # 一键自动分类
    path('api/seed_products/', views.seed_sample_products, name='seed_products'),  # 一键部署示例商品
]
