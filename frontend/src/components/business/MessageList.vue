<template>
  <div ref="listRef" class="message-list">
    <div v-if="messages.length === 0" class="message-list__empty">
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
 * 消息列表组件：渲染所有消息，自动滚动到底部。
 */
import { ref, watch, nextTick, onMounted } from 'vue'
import type { ChatMessage } from '@/types/chat'
import MessageItem from './MessageItem.vue'

const props = defineProps<{
  /** 消息列表 */
  messages: ChatMessage[]
}>()

const listRef = ref<HTMLDivElement | null>(null)

/** 滚动到底部 */
async function scrollToBottom(): Promise<void> {
  await nextTick()
  if (listRef.value) {
    listRef.value.scrollTop = listRef.value.scrollHeight
  }
}

// 消息变化时自动滚动
watch(
  () => props.messages,
  () => {
    void scrollToBottom()
  },
  { deep: true }
)

// 挂载后滚动到底部
onMounted(() => {
  void scrollToBottom()
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
