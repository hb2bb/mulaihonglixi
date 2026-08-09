/**
 * 时间格式化工具。
 */

/**
 * 返回当前时间的 ISO8601 字符串（用于前端乐观展示消息时间）。
 * @returns ISO8601 格式字符串
 */
export function nowIso(): string {
  return new Date().toISOString()
}

/**
 * 将 ISO8601 时间字符串格式化为简短显示（HH:mm）。
 * @param iso ISO8601 时间字符串
 * @returns HH:mm 格式
 */
export function formatTime(iso: string): string {
  if (!iso) return ''
  const dt = new Date(iso)
  if (Number.isNaN(dt.getTime())) return ''
  const hh = String(dt.getHours()).padStart(2, '0')
  const mm = String(dt.getMinutes()).padStart(2, '0')
  return `${hh}:${mm}`
}

/**
 * 将 ISO8601 时间字符串格式化为完整显示（YYYY-MM-DD HH:mm）。
 * @param iso ISO8601 时间字符串
 * @returns YYYY-MM-DD HH:mm 格式
 */
export function formatDateTime(iso: string): string {
  if (!iso) return ''
  const dt = new Date(iso)
  if (Number.isNaN(dt.getTime())) return ''
  const yyyy = dt.getFullYear()
  const mm = String(dt.getMonth() + 1).padStart(2, '0')
  const dd = String(dt.getDate()).padStart(2, '0')
  const hh = String(dt.getHours()).padStart(2, '0')
  const min = String(dt.getMinutes()).padStart(2, '0')
  return `${yyyy}-${mm}-${dd} ${hh}:${min}`
}
