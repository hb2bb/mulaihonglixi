/**
 * Vue Router 配置：单路由指向聊天页。
 */
import { createRouter, createWebHistory, type RouteRecordRaw } from 'vue-router'

const routes: RouteRecordRaw[] = [
  {
    path: '/',
    name: 'Chat',
    component: () => import('@/views/Chat/index.vue'),
    meta: {
      title: '知夏 - AI 女友 Demo',
    },
  },
  // 兜底重定向到首页
  {
    path: '/:pathMatch(.*)*',
    redirect: '/',
  },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
})

export default router
