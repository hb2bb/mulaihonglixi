<template>
  <div
    ref="listRef"
    class="message-list"
    @scroll="handleScroll"
  >
    <!-- 顶部加载更早历史 -->
    <div v-if="loadingHistory" class="message-list__loading">
      <span class="message-list__loading-spinner" />
      <span>加载更早的消息...</span>
    </div>

    <div v-else-if="messages.length === 0 && !loadingHistory" class="message-list__empty">
      <div class="message-list__empty-icon">夏</div>
      <div class="message-list__empty-text">和知夏聊点什么吧</div>
    </div>

    <MessageItem
      v-for="(msg, index) in messages"
      :key="index"
      :message="msg"
    />
  </div>
</template>

<script setup lang="ts">
/**
 * 消息列表组件：渲染所有消息。
 * - 进入时（有历史）停在最底部（最新消息）
 * - 向上滚动到顶部时触发 load-older 事件分页加载更早历史
 * - 加载更早历史后保持滚动位置（前插消息不跳动）
 */
import { ref, watch, nextTick, onMounted } from 'vue'
import type { ChatMessage } from '@/types/chat'
import MessageItem from './MessageItem.vue'

const props = withDefaults(
  defineProps<{
    /** 消息列表（时间正序，最旧在前，最新在后） */
    messages: ChatMessage[]
    /** 是否正在加载更早历史 */
    loadingHistory?: boolean
    /** 是否还有更早历史 */
    hasMore?: boolean
    /** 首次加载历史中（用于初始滚动定位） */
    initialLoading?: boolean
  }>(),
  {
    loadingHistory: false,
    hasMore: false,
    initialLoading: false,
  }
)

const emit = defineEmits<{
  /** 向上滚动到顶部，需要加载更早历史 */
  (e: 'load-older'): void
}>()

const listRef = ref<HTMLDivElement | null>(null)

/** 距顶部多少 px 内视为"触顶" */
const SCROLL_THRESHOLD = 8

/** 标记是否已完成初始加载（避免初始定位与用户滚动冲突） */
let hasInitialized = false

/** 滚动到底部（最新消息） */
function scrollToBottom(): void {
  if (listRef.value) {
    listRef.value.scrollTop = listRef.value.scrollHeight
  }
}

function handleScroll(): void {
  const el = listRef.value
  if (!el || props.loadingHistory || !props.hasMore) return
  // 触顶时加载更早历史
  if (el.scrollTop <= SCROLL_THRESHOLD) {
    emit('load-older')
  }
}

// 初始加载完成后（messages 由空变为有内容），定位到底部
watch(
  () => props.initialLoading,
  (loading) => {
    if (!loading && props.messages.length > 0 && !hasInitialized) {
      hasInitialized = true
      void nextTick(scrollToBottom)
    }
  }
)

// 历史前插后保持滚动位置：记录加载前 scrollHeight，加载后补偿 scrollTop
let prevScrollHeight = 0

watch(
  () => props.loadingHistory,
  (loading) => {
    if (loading) {
      // 记录加载前的总高度，用于加载后补偿滚动
      prevScrollHeight = listRef.value?.scrollHeight ?? 0
    } else if (prevScrollHeight > 0) {
      // 加载完成：scrollHeight 增加量即前插内容高度，补偿 scrollTop 以保持视口稳定
      void nextTick(() => {
        const el = listRef.value
        if (el) {
          el.scrollTop = el.scrollTop + (el.scrollHeight - prevScrollHeight)
        }
        prevScrollHeight = 0
      })
    }
  }
)

// 新消息（尾部追加）时滚动到底部；历史前插由上方 loadingHistory 逻辑处理
let prevLength = 0
watch(
  () => props.messages.length,
  (len) => {
    if (len > prevLength && !props.loadingHistory) {
      void nextTick(scrollToBottom)
    }
    prevLength = len
  }
)

onMounted(() => {
  // 无历史加载任务（例如空会话）时，直接定位底部
  if (!props.initialLoading && props.messages.length > 0) {
    hasInitialized = true
    void nextTick(scrollToBottom)
  }
})
</script>

<style scoped>
.message-list {
  flex: 1;
  overflow-y: auto;
  padding: 20px 16px;
  display: flex;
  flex-direction: column;
}

.message-list__loading {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  padding: 8px 0;
  font-size: 12px;
  color: var(--color-text-tertiary);
}

.message-list__loading-spinner {
  width: 14px;
  height: 14px;
  border: 2px solid var(--color-border);
  border-top-color: var(--color-primary);
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}

@keyframes spin {
  to {
    transform: rotate(360deg);
  }
}

.message-list__empty {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 12px;
  color: var(--color-text-tertiary);
}

.message-list__empty-icon {
  width: 56px;
  height: 56px;
  border-radius: 50%;
  background-color: var(--color-primary);
  color: #fff;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 22px;
  font-weight: 600;
}

.message-list__empty-text {
  font-size: 14px;
}
</style>
