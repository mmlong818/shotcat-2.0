type OverwriteReminder = {
  step: string
  replaces: string[]
  consequence: string
}

/** 在重做流程步骤前明确说明下一步会被覆盖的内容，避免误操作。 */
export function confirmOverwrite({ step, replaces, consequence }: OverwriteReminder) {
  const lines = [
    `覆盖提醒：重新执行「${step}」？`,
    '',
    '将覆盖下一步内容：',
    ...replaces.map((item) => `• ${item}`),
    '',
    consequence,
    '',
    '确认继续？',
  ]
  return window.confirm(lines.join('\n'))
}
