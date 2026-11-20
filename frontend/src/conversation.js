// A saved check is created in the same request as the assistant's answer.
// Use user-turn boundaries: database inserts may timestamp the check just before
// the assistant message. Pairing checks by array index breaks on clarifications.
export function checksForMessage(messages, checks, messageId) {
  const index = messages.findIndex((message) => message.id === messageId)
  if (index < 0 || messages[index].role !== 'assistant') return []
  const previousUser = messages.slice(0, index).findLast((message) => message.role === 'user')
  const nextUser = messages.slice(index + 1).find((message) => message.role === 'user')
  if (!previousUser) return []
  const from = new Date(previousUser.created_at).getTime()
  const until = nextUser ? new Date(nextUser.created_at).getTime() : Infinity
  return checks.filter((run) => {
    const time = new Date(run.created_at).getTime()
    return time >= from && time < until
  })
}

export function messagePreview(content) {
  return content.replace(/```[\s\S]*?```/g, ' [Фрагмент кода] ')
    .replace(/^\s{0,3}#{1,6}\s+/gm, '').replace(/[*_`>]/g, '')
    .replace(/\s+/g, ' ').trim().slice(0, 240)
}
