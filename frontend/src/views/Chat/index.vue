<template>
  <div class="chat-view">
    <header class="chat-view__header">
      <div class="chat-view__title">
        <span class="chat-view__avatar">夏</span>
        <span class="chat-view__name">宁知夏</span>
      </div>
      <div class="chat-view__actions">
        <button
          class="chat-view__btn"
          :class="{ 'chat-view__btn--active': chatStore.useStream }"
          title="切换流式/非流式"
          @click="chatStore.toggleStream"
        >
          {{ chatStore.useStream ? '流式' : '普通' }}
        </button>
        <button class="chat-view__btn" title="重置会话" @click="chatStore.resetSession">
          新会话
        </button>
      </div>
    </header>

    <MessageList :messages="chatStore.messages" />

    <div v-if="chatStore.errorMessage" class="chat-view__error">
      {{ chatStore.errorMessage }}
    </div>

    <ChatInput :disabled="chatStore.isSending" @send="handleSend" />
  </div>
</template>

<script setup lang="ts">
/**
 * 聊天页面：单列居中布局，header + 消息列表 + 输入框。
 */
import { useChatStore } from '@/store/chat'
import MessageList from '@/components/business/MessageList.vue'
import ChatInput from '@/components/business/ChatInput.vue'

const chatStore = useChatStore()

async function handleSend(text: string): Promise<void> {
  await chatStore.sendMessage(text)
}
</script>

<style scoped>
.chat-view {
  display: flex;
  flex-direction: column;
  height: 100%;
  max-width: var(--chat-max-width);
  margin: 0 auto;
  background-color: var(--color-bg);
}
.chat-view__header {
  flex-shrink: 0;
  height: var(--header-height);
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 16px;
  border-bottom: 1px solid var(--color-border);
  background-color: var(--color-bg-secondary);
}
.chat-view__title {
  display: flex;
  align-items: center;
  gap: 10px;
}
.chat-view__avatar {
  width: 32px;
  height: 32px;
  border-radius: 50%;
  background-color: var(--color-primary);
  color: #fff;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 14px;
  font-weight: 600;
}
.chat-view__name {
  font-size: 16px;
  font-weight: 500;
}
.chat-view__actions {
  display: flex;
  gap: 8px;
}
.chat-view__btn {
  height: 28px;
  padding: 0 12px;
  border: 1px solid var(--color-border);
  border-radius: 6px;
  background-color: transparent;
  color: var(--color-text-secondary);
  font-size: 12px;
  cursor: pointer;
  transition: all 0.2s;
}
.chat-view__btn:hover {
  border-color: var(--color-primary);
  color: var(--color-primary);
}
.chat-view__btn--active {
  border-color: var(--color-primary);
  color: var(--color-primary);
  background-color: var(--color-primary-light);
}
.chat-view__error {
  padding: 6px 16px;
  font-size: 12px;
  color: #e54d42;
  background-color: #fff1f0;
}
</style>
