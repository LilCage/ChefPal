/**
 * 多智能体协作（原型 05 屏5）：营养师 + 大厨 + 采购 三 Agent 并行输出
 * 数据源 POST /agents/collaborate
 */
import { Input, Text, View } from '@tarojs/components'
import Taro from '@tarojs/taro'
import { useState } from 'react'
import NavBar from '../../components/NavBar'
import { collaborateAgents, type CollaborateData } from '../../services/api'
import './index.scss'

type TabKey = 'nutritionist' | 'chef' | 'shopper'
const TABS: { key: TabKey; label: string; sub: string; icon: string }[] = [
  { key: 'nutritionist', label: '营养师', sub: '平衡搭配', icon: 'ic-spark' },
  { key: 'chef', label: '大厨', sub: '烹饪技法', icon: 'ic-kitchen' },
  { key: 'shopper', label: '采购', sub: '省钱清单', icon: 'ic-cart' },
]

export default function MultiAgent() {
  const [tab, setTab] = useState<TabKey>('nutritionist')
  const [ingredients, setIngredients] = useState<string[]>([])
  const [input, setInput] = useState('')
  const [data, setData] = useState<CollaborateData | null>(null)
  const [loading, setLoading] = useState(false)

  const addIngredient = () => {
    const v = input.trim()
    if (!v) return
    if (ingredients.includes(v)) {
      Taro.showToast({ title: '已添加', icon: 'none' })
      return
    }
    setIngredients([...ingredients, v])
    setInput('')
  }

  const run = async () => {
    if (ingredients.length === 0) {
      Taro.showToast({ title: '先告诉我冰箱里有什么', icon: 'none' })
      return
    }
    if (loading) return
    setLoading(true)
    try {
      const d = await collaborateAgents(ingredients)
      setData(d)
    } catch (e: any) {
      Taro.showToast({ title: e.message || '协作失败', icon: 'none' })
    } finally {
      setLoading(false)
    }
  }

  return (
    <View className='page-content multi-agent'>
      <NavBar title='小伴主厨团' showBack />

      <View className='field'>
        <View className='field-label'>✨ 冰箱里有什么</View>
        <View className='chips'>
          {ingredients.map((i) => (
            <View key={i} className='chip chip--on'>
              <Text userSelect>{i}</Text>
              <Text userSelect className='x' onClick={() => setIngredients(ingredients.filter((x) => x !== i))}>×</Text>
            </View>
          ))}
          <View className='chip chip-add'>
            <Input
              className='chip-input'
              value={input}
              placeholder='＋ 添加食材'
              confirmType='done'
              onInput={(e) => setInput(e.detail.value)}
              onConfirm={addIngredient}
            />
          </View>
        </View>
      </View>

      <View className='agent-tabs'>
        {TABS.map((t) => (
          <View
            key={t.key}
            className={`ag ${tab === t.key ? 'on' : ''}`}
            onClick={() => setTab(t.key)}
          >
            <Text userSelect className='ag-label'>{t.label}</Text>
            <Text userSelect className='ag-sub'>{t.sub}</Text>
          </View>
        ))}
      </View>

      {!data ? (
        <View className='agent-placeholder'>
          <View className='agent-card dashed'>
            <View className='agent-head'>
              <View className='a-ic soft'>
                <View className={`ic ${TABS.find((t) => t.key === tab)?.icon} ic-sm`} />
              </View>
              <View className='agent-info'>
                <Text userSelect className='a-name'>{TABS.find((t) => t.key === tab)?.label} Agent</Text>
                <Text userSelect className='a-desc'>三个 Agent 并行 · 输出交叉校验</Text>
              </View>
              <View className='a-lv'><Text userSelect>待命</Text></View>
            </View>
            <View className='agent-out'>
              <Text userSelect className='agent-hint'>输入食材，点下方按钮让小伴主厨团同时开工</Text>
            </View>
          </View>
        </View>
      ) : (
        <View className='agent-stack'>
          <View className='agent-card'>
            <View className='agent-head'>
              <View className='a-ic green'>
                <View className='ic ic-spark ic-sm' />
              </View>
              <View className='agent-info'>
                <Text userSelect className='a-name'>营养师 Agent</Text>
                <Text userSelect className='a-desc'>基于你的健康目标</Text>
              </View>
              <View className='a-lv'><Text userSelect>协同中</Text></View>
            </View>
            <View className='agent-out'>
              <Text userSelect className='tag'>热量</Text>
              <Text userSelect className='out-line'>今日建议 <Text userSelect className='out-strong'>{data.nutritionist.calories_kcal} 千卡</Text>，蛋白质 {data.nutritionist.protein_g}g 优先</Text>
              <Text userSelect className='tag'>搭配</Text>
              <Text userSelect className='out-line'>{data.nutritionist.advice}</Text>
              <Text userSelect className='tag'>忌口</Text>
              <Text userSelect className='out-line'>已避开 <Text userSelect className='out-strong'>{data.nutritionist.avoided_allergens.join('、') || '无'}</Text></Text>
            </View>
          </View>

          <View className='agent-card'>
            <View className='agent-head'>
              <View className='a-ic soft'>
                <View className='ic ic-kitchen ic-sm' />
              </View>
              <View className='agent-info'>
                <Text userSelect className='a-name'>大厨 Agent</Text>
                <Text userSelect className='a-desc'>推荐：{data.chef.dish_name}</Text>
              </View>
              <View className='a-lv gold'><Text userSelect>协同中</Text></View>
            </View>
            <View className='agent-out'>
              <Text userSelect className='tag'>技法</Text>
              <Text userSelect className='out-line'>{data.chef.technique}</Text>
              {data.chef.plating && (
                <>
                  <Text userSelect className='tag'>摆盘</Text>
                  <Text userSelect className='out-line'>{data.chef.plating}</Text>
                </>
              )}
            </View>
          </View>

          <View className='agent-card'>
            <View className='agent-head'>
              <View className='a-ic green'>
                <View className='ic ic-cart ic-sm' />
              </View>
              <View className='agent-info'>
                <Text userSelect className='a-name'>采购 Agent</Text>
                <Text userSelect className='a-desc'>省钱的补买清单</Text>
              </View>
              <View className='a-lv gold'><Text userSelect>协同中</Text></View>
            </View>
            <View className='agent-out'>
              {data.shopper.categories.map((c, ci) => (
                <View key={ci} className='shop-cat'>
                  <Text userSelect className='cat-name'>{c.name}</Text>
                  <Text userSelect className='out-line'>
                    {c.items.map((it) => `${it.name}${it.quantity ? ` ${it.quantity}` : ''}`).join(' · ')}
                  </Text>
                </View>
              ))}
              {data.shopper.tips && (
                <>
                  <Text userSelect className='tag'>省钱</Text>
                  <Text userSelect className='out-line'>{data.shopper.tips}</Text>
                </>
              )}
            </View>
          </View>
        </View>
      )}

      <View className='sec'>
        <View className={`btn btn--red btn--block ${loading ? 'btn--disabled' : ''}`} onClick={run}>
          <Text userSelect>{loading ? '三个 Agent 并行中…' : '🤝 三个 Agent 同时输出'}</Text>
        </View>
      </View>
      <Text userSelect className='note agent-note'>多智能体并行 · 输出交叉校验 · 更可靠</Text>
    </View>
  )
}
