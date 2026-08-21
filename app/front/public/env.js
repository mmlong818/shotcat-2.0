// 本地开发默认直连本机后端；容器部署时由 Nginx/入口脚本覆盖。
window.__ENV = window.__ENV || {
  BACKEND_URL: 'http://localhost:8000',
}
