const api = require('../../utils/api.js');
const { normalizeSalesReport } = require('../../utils/format.js');

Page({
  data: {
    days: 7,
    loading: false,
    totalAmount: '0.00',
    totalCount: 0,
    startDate: '',
    endDate: '',
    topProducts: [],
    records: []
  },

  onLoad() {
    this.fetchReport();
  },

  onPullDownRefresh() {
    this.fetchReport().finally(() => wx.stopPullDownRefresh());
  },

  switchDays(e) {
    const days = Number(e.currentTarget.dataset.days || 7);
    this.setData({ days });
    this.fetchReport();
  },

  fetchReport() {
    this.setData({ loading: true });
    return api.request({
      url: '/api/sales_report/',
      data: { days: this.data.days }
    }).then((data) => {
      const report = normalizeSalesReport(data);
      this.setData({
        loading: false,
        totalAmount: report.totalAmount,
        totalCount: report.totalCount,
        startDate: report.startDate,
        endDate: report.endDate,
        topProducts: report.topProducts,
        records: report.records
      });
    }).catch((err) => {
      console.error('获取销售报表失败', err);
      this.setData({ loading: false });
      wx.showToast({ title: '报表加载失败', icon: 'none' });
    });
  }
});
