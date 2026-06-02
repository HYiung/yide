function formatMoney(value) {
  const numberValue = Number(value);
  if (!Number.isFinite(numberValue)) {
    return '0.00';
  }
  return numberValue.toFixed(2);
}

function normalizeSalesReport(data) {
  const report = data || {};
  const records = Array.isArray(report.records) ? report.records : [];
  const topProducts = Array.isArray(report.top_products) ? report.top_products : [];

  return {
    status: report.status || 'success',
    startDate: report.start_date || '',
    endDate: report.end_date || '',
    totalAmount: formatMoney(report.total_amount),
    totalCount: Number(report.total_count || 0),
    topProducts: topProducts.map((item) => ({
      productName: item.product_name || '',
      quantity: Number(item.quantity || 0),
      amount: formatMoney(item.amount)
    })),
    records: records.map((item) => ({
      productName: item.product_name || '',
      price: formatMoney(item.price),
      quantity: Number(item.quantity || 0),
      saleDate: item.sale_date || ''
    }))
  };
}

module.exports = {
  formatMoney,
  normalizeSalesReport
};
