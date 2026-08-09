<template>
  <div class="message-item" :class="`message-item--${message.role}`">
    <div class="message-item__avatar">
      {{ avatarText }}
    </div>
    <div class="message-item__main">
      <div class="message-item__bubble" :class="`message-item__bubble--${message.role}`">
        <span v-if="message.streaming && !message.content" class="message-item__typing">
          知夏正在输入...
        </span>
        <template v-else>{{ message.content }}</template>
        <span v-if="message.streaming && message.content" class="message-item__cursor">|</span>
      </div>
      <div class="message-item__time">{{ formattedTime }}</div>
    </div>
  </div>
</template>

<script setup lang="ts">
/**
 * 单条消息气泡组件。
 * 用户消息靠右，知夏消息靠左。
 */
import { computed } from 'vue'
import type { ChatMessage } from '@/types/chat'
import { formatTime } from '@/utils/datetime'

const props = defineProps<{
  /** 消息对象 */
  message: ChatMessage
}>()

const avatarText = computed(() => {
  return props.message.role === 'user' ? '我' : '夏'
})

const formattedTime = computed(() => {
  return formatTime(props.message.datetime)
})
</script>

<style scoped>
.message-item {
  display: flex;
  gap: 10px;
  margin-bottom: 16px;
  width: 100%;
}

.message-item--user {
  flex-direction: row-reverse;
}

.message-item__avatar {
  flex-shrink: 0;
  width: 36px;
  height: 36px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 14px;
  font-weight: 600;
  color: #fff;
  background-color: var(--color-text-tertiary);
}

.message-item--user .message-item__avatar {
  background-color: var(--color-user-bubble);
}

.message-item--assistant .message-item__avatar {
  background-color: var(--color-primary);
}

.message-item__main {
  display: flex;
  flex-direction: column;
  max-width: var(--bubble-max-width);
}

.message-item--user .message-item__main {
  align-items: flex-end;
}

.message-item--assistant .message-item__main {
  align-items: flex-start;
}

.message-item__bubble {
  padding: 10px 14px;
  border-radius: var(--bubble-radius);
  font-size: 15px;
  line-height: 1.5;
  word-break: break-word;
  box-shadow: 0 1px 2px var(--color-shadow);
}

.message-item__bubble--user {
  background-color: var(--color-user-bubble);
  color: var(--color-user-text);
  border-bottom-right-radius: 4px;
}

.message-item__bubble--assistant {
  background-color: var(--color-assistant-bubble);
  color: var(--color-assistant-text);
  border-bottom-left-radius: 4px;
}

.message-item__typing {
  color: var(--color-text-tertiary);
  font-size: 14px;
}

.message-item__cursor {
  display: inline-block;
  animation: blink 1s infinite;
  color: var(--color-primary);
  font-weight: bold;
}

@keyframes blink {
  0%,
  50% {
    opacity: 1;
  }
  51%,
  100% {
    opacity: 0;
  }
}

.message-item__time {
  font-size: 11px;
  color: var(--color-text-tertiary);
  margin-top: 4px;
}
</style>
