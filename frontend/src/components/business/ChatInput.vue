<template>
  <div class="chat-input">
    <textarea
      ref="textareaRef"
      v-model="text"
      class="chat-input__textarea"
      :placeholder="placeholder"
      :disabled="disabled"
      rows="1"
      @keydown.enter.exact.prevent="handleSend"
      @keydown.shift.enter="handleShiftEnter"
      @input="autoResize"
    ></textarea>
    <button
      class="chat-input__send"
      :disabled="!canSend"
      @click="handleSend"
    >
      发送
    </button>
  </div>
</template>

<script setup lang="ts">
/**
 * 输入框组件：自适应高度 textarea + 发送按钮。
 * Enter 发送，Shift+Enter 换行。
 */
import { ref, computed, nextTick } from 'vue'

const props = withDefaults(
  defineProps<{
    /** 是否禁用（发送中） */
    disabled?: boolean
    /** 占位提示 */
    placeholder?: string
  }>(),
  {
    disabled: false,
    placeholder: '输入消息，Enter 发送，Shift+Enter 换行',
  }
)

const emit = defineEmits<{
  /** 发送消息 */
  (e: 'send', text: string): void
}>()

const text = ref('')
const textareaRef = ref<HTMLTextAreaElement | null>(null)

const canSend = computed(() => {
  return text.value.trim().length > 0 && !props.disabled
})

function handleSend(): void {
  if (!canSend.value) return
  const trimmed = text.value.trim()
  emit('send', trimmed)
  text.value = ''
  void nextTick(() => autoResize())
}

function handleShiftEnter(): void {
  // Shift+Enter 默认换行，无需额外处理，保留函数以便未来扩展
}

/** 自适应高度 */
function autoResize(): void {
  const el = textareaRef.value
  if (!el) return
  el.style.height = 'auto'
  el.style.height = `${Math.min(el.scrollHeight, 120)}px`
}
</script>

<style scoped>
.chat-input {
  display: flex;
  gap: 10px;
  align-items: flex-end;
  padding: 12px 16px;
  border-top: 1px solid var(--color-border);
  background-color: var(--color-bg-secondary);
}

.chat-input__textarea {
  flex: 1;
  resize: none;
  border: 1px solid var(--color-border);
  border-radius: 8px;
  padding: 10px 12px;
  font-size: 15px;
  line-height: 1.5;
  font-family: inherit;
  background-color: var(--color-bg);
  color: var(--color-text-primary);
  outline: none;
  transition: border-color 0.2s;
  max-height: 120px;
  overflow-y: auto;
}

.chat-input__textarea:focus {
  border-color: var(--color-primary);
}

.chat-input__textarea:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.chat-input__send {
  flex-shrink: 0;
  height: 40px;
  padding: 0 20px;
  border: none;
  border-radius: 8px;
  background-color: var(--color-primary);
  color: #fff;
  font-size: 14px;
  font-weight: 500;
  cursor: pointer;
  transition: opacity 0.2s, background-color 0.2s;
}

.chat-input__send:hover:not(:disabled) {
  opacity: 0.9;
}

.chat-input__send:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}
</style>
