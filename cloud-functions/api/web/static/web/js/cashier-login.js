if (document.body.dataset.loginError === 'true') {
  document.getElementById('errorMsg').textContent = '密码错误，请重试';
  document.getElementById('errorMsg').className = 'login-error show';
}
document.getElementById('passwordInput').focus();
