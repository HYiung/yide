const assert = require('assert');
const api = require('../utils/api.js');
const { formatMoney, normalizeSalesReport } = require('../utils/format.js');

async function testBuildUrl() {
  assert.strictEqual(api.buildUrl('/api/test/'), `${api.BASE_URL}/api/test/`);
  assert.strictEqual(api.buildUrl('api/test/'), `${api.BASE_URL}/api/test/`);
  assert.strictEqual(api.buildUrl('https://example.com/a'), 'https://example.com/a');
}

async function testRequestResolvesSuccessResponse() {
  global.wx = {
    request(options) {
      assert.strictEqual(options.url, `${api.BASE_URL}/ok/`);
      options.success({ statusCode: 200, data: { status: 'success' } });
    }
  };

  const data = await api.request({ url: '/ok/' });
  assert.deepStrictEqual(data, { status: 'success' });
}

async function testRequestRejectsHttpErrors() {
  global.wx = {
    request(options) {
      options.success({ statusCode: 500, data: { status: 'fail' } });
    }
  };

  await assert.rejects(() => api.request({ url: '/fail/' }), /服务器返回异常：500/);
}

function testFormatMoney() {
  assert.strictEqual(formatMoney('12'), '12.00');
  assert.strictEqual(formatMoney('12.345'), '12.35');
  assert.strictEqual(formatMoney('abc'), '0.00');
}

function testNormalizeSalesReport() {
  const report = normalizeSalesReport({
    status: 'success',
    start_date: '2026-06-01',
    end_date: '2026-06-02',
    total_amount: '9.5',
    total_count: 3,
    top_products: [{ product_name: '铅笔', quantity: '2', amount: '3' }],
    records: [{ product_name: '本子', price: '6', quantity: '1', sale_date: '2026-06-02 10:00' }]
  });

  assert.strictEqual(report.totalAmount, '9.50');
  assert.strictEqual(report.totalCount, 3);
  assert.deepStrictEqual(report.topProducts[0], { productName: '铅笔', quantity: 2, amount: '3.00' });
  assert.deepStrictEqual(report.records[0], { productName: '本子', price: '6.00', quantity: 1, saleDate: '2026-06-02 10:00' });
}

async function run() {
  await testBuildUrl();
  await testRequestResolvesSuccessResponse();
  await testRequestRejectsHttpErrors();
  testFormatMoney();
  testNormalizeSalesReport();
  delete global.wx;
  console.log('Mini program unit tests passed');
}

run().catch((err) => {
  console.error(err);
  process.exit(1);
});
