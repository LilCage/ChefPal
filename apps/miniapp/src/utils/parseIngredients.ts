/**
 * 语音文本 → 食材数组切分（语音输入页专用）。
 *
 * 输入形如"冰箱里有西红柿、鸡蛋，还有一把挂面"：
 * - 按标点与连接词（、，。；和还有以及跟加及）切分
 * - 去除句首语气/位置词（冰箱里有 / 家里 / 有…）
 * - 去除数量词前缀（一把 / 两个 / 一些…）
 * - 去重保序
 * 结果仅供参考，用户可在页面上手动删改补充。
 */

const SPLIT_RE = /[、，,。;；!！?？和还有以及跟加及\s]+/

const NOISE_PREFIXES = [
  '冰箱里面', '冰箱里有', '冰箱里', '冰箱',
  '厨房里面', '厨房里', '厨房',
  '家里有', '家里', '还有一些', '还有', '以及',
  '需要', '有', '加',
]

const QUANTIFIER_RE = /^(一?几?把|一?几?些|一?两?三?个|一?几?颗|一?几?根|一?几?包|一?几?袋|一?几?盒|一?几?罐|一?几?瓶|一?几?份|一?点|一丢丢|不少|很多|大约|大概|差不多)/

export function parseIngredients(text: string): string[] {
  const raw = text.replace(/[「」"'“”‘’()（）]/g, ' ').trim()
  if (!raw) return []

  const segments = raw.split(SPLIT_RE).map((s) => s.trim()).filter(Boolean)
  const result: string[] = []
  const seen = new Set<string>()

  for (let seg of segments) {
    // 循环剥离开头噪声（如"还有冰箱里有"）
    let prev = ''
    while (seg !== prev) {
      prev = seg
      for (const p of NOISE_PREFIXES) {
        if (seg.startsWith(p)) {
          seg = seg.slice(p.length).trim()
          break
        }
      }
    }
    // 剥离数量词前缀
    seg = seg.replace(QUANTIFIER_RE, '').trim()
    if (seg && !seen.has(seg)) {
      seen.add(seg)
      result.push(seg)
    }
  }
  return result
}
